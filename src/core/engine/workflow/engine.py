"""
Workflow Engine

Execute YAML workflows with flow control support.

Supports:
- Variable resolution (${params.x}, ${step.result}, ${env.VAR})
- Flow control (when, retry, parallel, branch, switch, goto)
- Error handling (on_error: stop/continue/retry)
- Timeout per step
- Foreach iteration with result aggregation
- Workflow-level output definition
- Executor hooks for lifecycle events
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from ..variable_resolver import VariableResolver
from ..hooks import ExecutorHooks, NullHooks, HookContext, HookAction
from ..exceptions import StepTimeoutError, WorkflowExecutionError, StepExecutionError
from ..flow_control import is_flow_control_module
from ..step_executor import StepExecutor, create_step_executor
from ..trace import ExecutionTrace, TraceCollector
from ...constants import WorkflowStatus

from .routing import WorkflowRouter
from .debug import DebugController
from .output import OutputCollector

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """
    Execute YAML workflows with full support for:
    - Variable resolution
    - Flow control (when, retry, parallel, branch, switch, goto)
    - Error handling
    - Context management
    """

    def __init__(
        self,
        workflow: Dict[str, Any],
        params: Dict[str, Any] = None,
        start_step: Optional[int] = None,
        end_step: Optional[int] = None,
        hooks: Optional[ExecutorHooks] = None,
        pause_callback: Optional[Any] = None,
        checkpoint_callback: Optional[Any] = None,
        breakpoints: Optional[Set[str]] = None,
        step_mode: bool = False,
        initial_context: Optional[Dict[str, Any]] = None,
        enable_trace: bool = False,
    ):
        """
        Initialize workflow engine.

        Args:
            workflow: Parsed workflow YAML
            params: Workflow input parameters
            start_step: Start from this step index (0-based, inclusive)
            end_step: End at this step index (0-based, inclusive)
            hooks: Optional executor hooks for lifecycle events
            pause_callback: Optional async callback for pause/resume control
            checkpoint_callback: Optional async callback for state snapshots
            breakpoints: Optional set of step IDs where execution should pause
            step_mode: If True, pause after each step
            initial_context: Optional initial context to inject
            enable_trace: If True, collect detailed execution trace
        """
        self.workflow = workflow
        self.params = self._parse_params(workflow.get('params', []), params or {})
        self.context = {}
        self.execution_log = []

        self.workflow_id = workflow.get('id', 'unknown')
        self.workflow_name = workflow.get('name', 'Unnamed Workflow')
        self.workflow_description = workflow.get('description', '')
        self.workflow_version = workflow.get('version', '1.0.0')

        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.status: str = WorkflowStatus.PENDING
        self.current_step: int = 0

        # Step range for partial execution
        self._start_step = start_step
        self._end_step = end_step

        # Hooks and executor
        self._hooks: ExecutorHooks = hooks or NullHooks()
        self._total_steps: int = 0
        self._step_executor: Optional[StepExecutor] = None

        # Callbacks
        self._pause_callback = pause_callback
        self._checkpoint_callback = checkpoint_callback

        # Component classes
        self._router = WorkflowRouter()
        self._debug = DebugController(breakpoints=breakpoints, step_mode=step_mode)
        self._output = OutputCollector(
            self.workflow_id, self.workflow_name, self.workflow_version
        )

        # Edges for routing
        self._edges = workflow.get('edges', [])

        # Goto tracking
        self._visited_gotos: Dict[str, int] = {}

        # Inject initial context
        if initial_context:
            self.context.update(initial_context)

        # Execution tracing (ITEM_PIPELINE_SPEC.md Section 8)
        self._enable_trace = enable_trace
        self._trace_collector: Optional[TraceCollector] = None
        self._execution_trace: Optional[ExecutionTrace] = None

    def _parse_params(
        self,
        param_schema: List[Dict[str, Any]],
        provided_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse parameter schema and merge with provided values."""
        result = {}

        if isinstance(param_schema, dict):
            result = param_schema.copy()
            result.update(provided_params)
            return result

        for param_def in param_schema:
            param_name = param_def.get('name')
            if not param_name:
                continue
            if param_name in provided_params:
                result[param_name] = provided_params[param_name]
            elif 'default' in param_def:
                result[param_name] = param_def['default']

        for key, value in provided_params.items():
            if key not in result:
                result[key] = value

        return result

    def _create_workflow_context(
        self,
        error: Optional[Exception] = None,
    ) -> HookContext:
        """Create hook context for workflow-level events."""
        elapsed_ms = 0.0
        if self.start_time:
            elapsed_ms = (time.time() - self.start_time) * 1000

        context = HookContext(
            workflow_id=self.workflow_id,
            workflow_name=self.workflow_name,
            total_steps=self._total_steps,
            variables=self.context.copy(),
            started_at=datetime.fromtimestamp(self.start_time) if self.start_time else None,
            elapsed_ms=elapsed_ms,
        )

        if error:
            context.error = error
            context.error_type = type(error).__name__
            context.error_message = str(error)

        return context

    async def execute(self) -> Dict[str, Any]:
        """Execute the workflow."""
        self.start_time = time.time()
        self.status = WorkflowStatus.RUNNING

        logger.info(f"Starting workflow: {self.workflow_name} (ID: {self.workflow_id})")

        steps = self.workflow.get('steps', [])
        self._total_steps = len(steps)

        self._step_executor = create_step_executor(
            hooks=self._hooks,
            workflow_id=self.workflow_id,
            workflow_name=self.workflow_name,
            total_steps=self._total_steps,
        )

        # Initialize trace collector if tracing enabled
        if self._enable_trace:
            self._trace_collector = TraceCollector(
                workflow_id=self.workflow_id,
                workflow_name=self.workflow_name,
                input_params=self.params,
            )
            self._trace_collector.start()

        start_context = self._create_workflow_context()
        start_result = self._hooks.on_workflow_start(start_context)
        if start_result.action == HookAction.ABORT:
            raise WorkflowExecutionError(
                f"Workflow aborted by hook: {start_result.abort_reason}"
            )

        try:
            if not steps:
                raise WorkflowExecutionError("No steps defined in workflow")

            self._router.build_step_index(steps)
            self._router.build_edge_index(self._edges, steps)
            await self._execute_steps(steps)

            self.status = WorkflowStatus.COMPLETED
            self.end_time = time.time()

            logger.info(
                f"Workflow completed successfully in {self.end_time - self.start_time:.2f}s"
            )

            complete_context = self._create_workflow_context()
            self._hooks.on_workflow_complete(complete_context)

            output = self._collect_output()

            # Complete trace if enabled
            if self._trace_collector:
                self._execution_trace = self._trace_collector.complete(output)

            return output

        except Exception as e:
            self.status = WorkflowStatus.FAILURE
            self.end_time = time.time()

            logger.error(f"Workflow failed: {str(e)}")

            # Fail trace if enabled
            if self._trace_collector:
                self._execution_trace = self._trace_collector.fail(e)

            failed_context = self._create_workflow_context(error=e)
            self._hooks.on_workflow_failed(failed_context)

            await self._handle_workflow_error(e)

            raise WorkflowExecutionError(f"Workflow execution failed: {str(e)}") from e

    async def _execute_steps(self, steps: List[Dict[str, Any]]):
        """Execute workflow steps with flow control support."""
        start_idx = self._start_step if self._start_step is not None else 0
        end_idx = self._end_step if self._end_step is not None else len(steps) - 1

        start_idx = max(0, min(start_idx, len(steps) - 1))
        end_idx = max(start_idx, min(end_idx, len(steps) - 1))

        if self._start_step is not None or self._end_step is not None:
            logger.info(f"Partial execution: steps {start_idx + 1} to {end_idx + 1}")

        current_idx = start_idx
        parallel_batch = []

        while current_idx <= end_idx:
            if self._debug.is_cancelled:
                logger.info("Workflow cancelled, stopping execution")
                break

            step = steps[current_idx]
            step_id = step.get('id', f'step_{current_idx}')
            self.current_step = current_idx

            # Handle pause
            await self._handle_pause_check(current_idx, step_id)

            if step.get('parallel', False):
                parallel_batch.append((current_idx, step))
                current_idx += 1
                continue

            if parallel_batch:
                await self._execute_parallel_steps(parallel_batch)
                parallel_batch = []

            step_status = 'success'
            step_error = None
            try:
                next_idx = await self._execute_step_with_flow_control(step, current_idx, steps)
            except Exception as e:
                step_status = 'failed'
                step_error = e
                next_idx = current_idx + 1
                raise
            finally:
                await self._save_checkpoint(current_idx, step_id, step_status, step_error)

            if next_idx > end_idx + 1:
                logger.info(f"Flow control jumped beyond end_step, stopping")
                break

            current_idx = next_idx

        if parallel_batch:
            await self._execute_parallel_steps(parallel_batch)

    async def _handle_pause_check(self, current_idx: int, step_id: str) -> None:
        """Handle pause check before step execution."""
        if self._pause_callback:
            try:
                internal_should_pause = await self._debug.should_pause_at_step(
                    step_id, current_idx, self._start_step
                )
                was_paused = await self._pause_callback(
                    current_idx,
                    step_id,
                    self.context.copy(),
                    {},
                    internal_should_pause
                )
                if was_paused:
                    logger.info(f"Execution resumed after pause at step {current_idx}")
                    self._debug.clear_step_request()
                    if self._debug.is_cancelled:
                        logger.info("Workflow cancelled during pause")
            except Exception as e:
                logger.warning(f"Pause callback error: {e}")
        else:
            should_pause = await self._debug.should_pause_at_step(
                step_id, current_idx, self._start_step
            )
            if should_pause:
                logger.warning(f"Pause requested but no pause_callback configured")

    async def _save_checkpoint(
        self,
        step_index: int,
        step_id: str,
        status: str,
        error: Optional[Exception] = None
    ) -> None:
        """Save checkpoint after step execution."""
        if not self._checkpoint_callback:
            return

        try:
            checkpoint_data = {
                'step_index': step_index,
                'step_id': step_id,
                'status': status,
                'context': self.context.copy(),
                'params': self.params.copy(),
                'error': str(error) if error else None,
                'error_type': type(error).__name__ if error else None,
            }
            await self._checkpoint_callback(step_index, step_id, checkpoint_data, status)
            logger.debug(f"Checkpoint saved for step {step_index}")
        except Exception as e:
            logger.warning(f"Checkpoint callback error: {e}")

    async def _execute_parallel_steps(
        self,
        step_tuples: List[Tuple[int, Dict[str, Any]]],
    ):
        """Execute multiple steps in parallel."""
        logger.info(f"Executing {len(step_tuples)} steps in parallel")

        tasks = [
            asyncio.create_task(self._execute_step(step, idx))
            for idx, step in step_tuples
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        errors = []
        should_stop = False

        for i, result in enumerate(results):
            _, step = step_tuples[i]
            step_id = step.get('id', f'step_{i}')
            on_error = step.get('on_error', 'stop')

            if isinstance(result, Exception):
                if on_error == 'stop':
                    should_stop = True
                    errors.append((step_id, result))
                else:
                    logger.warning(f"Parallel step '{step_id}' failed but continuing")
                    self.context[step_id] = {'ok': False, 'error': str(result)}

        if should_stop and errors:
            step_id, error = errors[0]
            raise StepExecutionError(step_id, f"Parallel step failed: {str(error)}", error)

    async def _execute_step_with_flow_control(
        self,
        step_config: Dict[str, Any],
        current_idx: int,
        steps: List[Dict[str, Any]]
    ) -> int:
        """Execute a step and handle flow control directives."""
        step_id = step_config.get('id', f'step_{current_idx}')
        result = await self._execute_step(step_config, current_idx)

        if result is None:
            return current_idx + 1

        # Handle __set_context for any module that returns it
        if isinstance(result, dict):
            set_context = result.get('__set_context')
            if isinstance(set_context, dict):
                self.context.update(set_context)

        module_id = step_config.get('module', '')
        has_connections = bool(step_config.get('connections'))

        # Use router for flow control modules OR steps with explicit connections
        if is_flow_control_module(module_id) or has_connections:
            return self._router.get_next_step_index(step_id, result, current_idx)

        return current_idx + 1

    async def _execute_step(
        self,
        step_config: Dict[str, Any],
        step_index: int = 0,
    ) -> Any:
        """Execute a single step."""
        step_id = step_config.get('id', f'step_{id(step_config)}')
        module_id = step_config.get('module')
        description = step_config.get('description', '')

        # Inject upstream step IDs from edges (ITEM_PIPELINE_SPEC.md)
        # Only if not already specified in step config
        if '$upstream_steps' not in step_config and 'inputs' not in step_config:
            upstream_ids = self._router.get_upstream_step_ids(step_id, data_edges_only=True)
            if upstream_ids:
                step_config['$upstream_steps'] = upstream_ids

        # Inject upstream steps by port for multi-input support
        if '$upstream_by_port' not in step_config:
            upstream_by_port = self._router.get_upstream_steps(step_id, data_edges_only=True)
            if upstream_by_port:
                step_config['$upstream_by_port'] = upstream_by_port

        should_execute = await self._should_execute_step(step_config)
        resolver = self._get_resolver()

        result = await self._step_executor.execute_step(
            step_config=step_config,
            step_index=step_index,
            context=self.context,
            resolver=resolver,
            should_execute=should_execute,
            trace_collector=self._trace_collector,
        )

        if result is not None:
            self.execution_log.append({
                'step_id': step_id,
                'module_id': module_id,
                'description': description,
                'status': 'success',
                'timestamp': datetime.now().isoformat()
            })

        return result

    async def _should_execute_step(self, step_config: Dict[str, Any]) -> bool:
        """Check if step should be executed based on 'when' condition."""
        when_condition = step_config.get('when')
        if when_condition is None:
            return True

        resolver = self._get_resolver()
        try:
            return resolver.evaluate_condition(when_condition)
        except Exception as e:
            logger.warning(f"Error evaluating condition: {str(e)}")
            return False

    def _get_resolver(self) -> VariableResolver:
        """Get variable resolver with current context."""
        workflow_metadata = {
            'id': self.workflow_id,
            'name': self.workflow_name,
            'version': self.workflow_version,
            'description': self.workflow_description
        }
        return VariableResolver(self.params, self.context, workflow_metadata)

    def _collect_output(self) -> Dict[str, Any]:
        """Collect workflow output."""
        output_template = self.workflow.get('output', {})
        resolver = self._get_resolver()
        workflow_metadata = {
            'id': self.workflow_id,
            'name': self.workflow_name,
            'version': self.workflow_version,
            'description': self.workflow_description
        }
        return self._output.collect(
            output_template=output_template,
            context=self.context,
            params=self.params,
            workflow_metadata=workflow_metadata,
            status=self.status,
            start_time=self.start_time,
            end_time=self.end_time,
            execution_log=self.execution_log,
            resolver=resolver,
        )

    async def _handle_workflow_error(self, error: Exception):
        """Handle workflow-level errors."""
        on_error_config = self.workflow.get('on_error', {})
        if not on_error_config:
            return

        rollback_steps = on_error_config.get('rollback_steps', [])
        if rollback_steps:
            logger.info("Executing rollback steps...")
            try:
                await self._execute_steps(rollback_steps)
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {str(rollback_error)}")

        notify_config = on_error_config.get('notify')
        if notify_config:
            logger.info(f"Error notification: {notify_config}")

    def get_execution_summary(self) -> Dict[str, Any]:
        """Get execution summary."""
        return self._output.get_execution_summary(
            workflow_description=self.workflow_description,
            status=self.status,
            start_time=self.start_time,
            end_time=self.end_time,
            execution_log=self.execution_log,
        )

    # Debug control delegation
    def cancel(self):
        """Cancel workflow execution."""
        self._debug.cancel()
        self.status = WorkflowStatus.CANCELLED
        logger.info(f"Workflow '{self.workflow_id}' cancelled")

    def pause(self):
        """Request workflow to pause at next step."""
        self._debug.pause()
        logger.info(f"Workflow '{self.workflow_id}' pause requested")

    def resume(self):
        """Clear pause flag."""
        self._debug.resume()
        logger.info(f"Workflow '{self.workflow_id}' resume requested")

    @property
    def is_paused(self) -> bool:
        return self._debug.is_paused

    @property
    def is_cancelled(self) -> bool:
        return self._debug.is_cancelled

    @property
    def step_mode(self) -> bool:
        return self._debug.step_mode

    @step_mode.setter
    def step_mode(self, value: bool) -> None:
        self._debug.step_mode = value

    def step_over(self) -> None:
        self._debug.step_over()

    def add_breakpoint(self, step_id: str) -> None:
        self._debug.add_breakpoint(step_id)

    def remove_breakpoint(self, step_id: str) -> bool:
        return self._debug.remove_breakpoint(step_id)

    def clear_breakpoints(self) -> None:
        self._debug.clear_breakpoints()

    def get_breakpoints(self) -> Set[str]:
        return self._debug.get_breakpoints()

    def inject_context(self, context: Dict[str, Any]) -> None:
        """Inject variables into execution context."""
        self.context.update(context)
        logger.info(f"Injected {len(context)} variables into context")

    def get_context(self) -> Dict[str, Any]:
        """Get a copy of the current execution context."""
        return self.context.copy()

    def get_state_snapshot(self) -> Dict[str, Any]:
        """Get a complete snapshot of the current execution state."""
        debug_state = self._debug.get_debug_state()
        return {
            'workflow_id': self.workflow_id,
            'workflow_name': self.workflow_name,
            'workflow_version': self.workflow_version,
            'status': self.status,
            'current_step': self.current_step,
            'total_steps': self._total_steps,
            'is_paused': debug_state['is_paused'],
            'is_cancelled': debug_state['is_cancelled'],
            'step_mode': debug_state['step_mode'],
            'breakpoints': debug_state['breakpoints'],
            'context': self.context.copy(),
            'params': self.params.copy(),
            'start_time': self.start_time,
            'execution_log': self.execution_log.copy(),
        }

    def get_execution_trace(self) -> Optional[ExecutionTrace]:
        """
        Get the execution trace (if tracing was enabled).

        Returns:
            ExecutionTrace object or None if tracing not enabled
        """
        return self._execution_trace

    def get_execution_trace_dict(self) -> Optional[Dict[str, Any]]:
        """
        Get the execution trace as dictionary (for API response).

        Returns:
            Trace dictionary or None if tracing not enabled
        """
        if self._execution_trace:
            return self._execution_trace.to_dict()
        return None
