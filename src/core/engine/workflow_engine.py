"""
Workflow Engine - Execute YAML workflows with flow control support

Supports:
- Variable resolution (${params.x}, ${step.result}, ${env.VAR})
- Flow control (when, retry, parallel, branch, switch, goto)
- Error handling (on_error: stop/continue/retry)
- Timeout per step
- Foreach iteration with result aggregation
- Workflow-level output definition
- Executor hooks for lifecycle events

Architecture:
- Exceptions: exceptions.py
- Flow control detection: flow_control.py
- Step execution: step_executor.py
- Variable resolution: variable_resolver.py
- Hooks: hooks.py
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from .variable_resolver import VariableResolver
from .hooks import (
    ExecutorHooks,
    NullHooks,
    HookContext,
    HookAction,
)
from ..constants import WorkflowStatus

logger = logging.getLogger(__name__)

# Import exceptions from dedicated module
from .exceptions import (
    StepTimeoutError,
    WorkflowExecutionError,
    StepExecutionError,
)

# Import flow control utilities
from .flow_control import (
    is_flow_control_module,
)

# Import step executor
from .step_executor import StepExecutor, create_step_executor


class WorkflowEngine:
    """
    Execute YAML workflows with full support for:
    - Variable resolution
    - Flow control (when, retry, parallel, branch, switch, goto)
    - Error handling
    - Context management

    Flow control modules are defined in flow_control.py for centralization.
    """

    # Use centralized flow control module detection from flow_control.py
    # FLOW_CONTROL_MODULES moved to flow_control.py

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
    ):
        """
        Initialize workflow engine

        Args:
            workflow: Parsed workflow YAML
            params: Workflow input parameters
            start_step: Start from this step index (0-based, inclusive)
            end_step: End at this step index (0-based, inclusive)
            hooks: Optional executor hooks for lifecycle events
            pause_callback: Optional async callback for pause/resume control.
                           Signature: async def callback(step_index, step_id, variables, node_outputs, internal_should_pause) -> bool
                           Called before each step. Should check for external pause requests (e.g., from controller).
                           internal_should_pause: True if engine's internal pause condition is met (breakpoint, step_mode).
                           Returns True if execution was paused and resumed.
            checkpoint_callback: Optional async callback for state snapshots.
                           Signature: async def callback(step_index, step_id, context, status) -> None
                           Called after each step completes (success or failure).
            breakpoints: Optional set of step IDs where execution should pause.
                        When execution reaches a breakpoint, it will pause before executing that step.
            step_mode: If True, pause after each step (single-step execution mode).
            initial_context: Optional initial context to inject (for resume from checkpoint).
                           Merged into self.context before execution starts.
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

        # Step range for partial execution (debug mode)
        self._start_step = start_step
        self._end_step = end_step

        self._step_index: Dict[str, int] = {}
        self._visited_gotos: Dict[str, int] = {}
        self._cancelled: bool = False
        self._paused: bool = False
        self._step_mode: bool = step_mode
        self._step_requested: bool = False  # For step-over functionality

        # Current step index for progress tracking (exposed for external monitoring)
        self.current_step: int = 0

        # Executor hooks for lifecycle events
        self._hooks: ExecutorHooks = hooks or NullHooks()
        self._total_steps: int = 0

        # Step executor for delegating step execution
        self._step_executor: Optional[StepExecutor] = None

        # Pause/resume callback for execution control
        self._pause_callback = pause_callback

        # Checkpoint callback for state snapshots
        self._checkpoint_callback = checkpoint_callback

        # Breakpoints for debugging (set of step_id strings)
        self._breakpoints: Set[str] = breakpoints or set()

        # Inject initial context (for resume from checkpoint)
        if initial_context:
            self.context.update(initial_context)

        # Workflow Spec v1.2: Edge-based routing + Connections
        # edges: [{source, sourceHandle, target, targetHandle, type}, ...]
        self._edges = workflow.get('edges', [])
        self._edge_index: Dict[str, List[Dict[str, Any]]] = {}  # source_id -> [edges]
        self._event_routes: Dict[str, str] = {}  # "source_id:event" -> target_id
        self._step_connections: Dict[str, Dict[str, List[str]]] = {}  # step_id -> {port: [targets]}

    def _parse_params(
        self,
        param_schema: List[Dict[str, Any]],
        provided_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Parse parameter schema and merge with provided values.

        If param_schema is empty or not defined, all provided_params are passed through.
        This supports runtime params like ui inputs (params.ui.xxx).
        """
        result = {}

        # If param_schema is a dict (legacy format), merge with provided
        if isinstance(param_schema, dict):
            result = param_schema.copy()
            result.update(provided_params)
            return result

        # Process schema-defined params
        for param_def in param_schema:
            param_name = param_def.get('name')
            if not param_name:
                continue

            if param_name in provided_params:
                result[param_name] = provided_params[param_name]
            elif 'default' in param_def:
                result[param_name] = param_def['default']

        # Always include all provided_params that aren't in schema
        # This allows runtime params (like ui.xxx) to pass through
        for key, value in provided_params.items():
            if key not in result:
                result[key] = value

        return result

    def _create_workflow_context(
        self,
        error: Optional[Exception] = None,
    ) -> HookContext:
        """
        Create hook context for workflow-level events
        """
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
        """
        Execute the workflow
        """
        self.start_time = time.time()
        self.status = WorkflowStatus.RUNNING

        logger.info(f"Starting workflow: {self.workflow_name} (ID: {self.workflow_id})")

        steps = self.workflow.get('steps', [])
        self._total_steps = len(steps)

        # Initialize step executor with workflow context
        self._step_executor = create_step_executor(
            hooks=self._hooks,
            workflow_id=self.workflow_id,
            workflow_name=self.workflow_name,
            total_steps=self._total_steps,
        )

        # Call workflow start hook
        start_context = self._create_workflow_context()
        start_result = self._hooks.on_workflow_start(start_context)
        if start_result.action == HookAction.ABORT:
            raise WorkflowExecutionError(
                f"Workflow aborted by hook: {start_result.abort_reason}"
            )

        try:
            if not steps:
                raise WorkflowExecutionError("No steps defined in workflow")

            self._build_step_index(steps)
            self._build_edge_index()  # Workflow Spec v1.1
            await self._execute_steps(steps)

            self.status = WorkflowStatus.COMPLETED
            self.end_time = time.time()

            logger.info(
                f"Workflow completed successfully in {self.end_time - self.start_time:.2f}s"
            )

            # Call workflow complete hook
            complete_context = self._create_workflow_context()
            self._hooks.on_workflow_complete(complete_context)

            return self._collect_output()

        except Exception as e:
            self.status = WorkflowStatus.FAILURE
            self.end_time = time.time()

            logger.error(f"Workflow failed: {str(e)}")

            # Call workflow failed hook
            failed_context = self._create_workflow_context(error=e)
            self._hooks.on_workflow_failed(failed_context)

            await self._handle_workflow_error(e)

            raise WorkflowExecutionError(f"Workflow execution failed: {str(e)}") from e

    def _build_step_index(self, steps: List[Dict[str, Any]]):
        """
        Build index mapping step IDs to their positions
        """
        self._step_index = {}
        for idx, step in enumerate(steps):
            step_id = step.get('id')
            if step_id:
                self._step_index[step_id] = idx

    def _build_edge_index(self):
        """
        Build edge index for event-based routing (Workflow Spec v1.2)

        Creates mappings:
        - _edge_index: source_id -> [edges from this source]
        - _event_routes: "source_id:event" -> target_id
        - _step_connections: step_id -> {port: [targets]} (from step.connections)

        Priority for routing (v1.2):
        1. step.connections (highest - semantic connections)
        2. _event_routes from edges (medium - canvas edges)
        3. next_step/params.target (lowest - legacy)
        """
        self._edge_index = {}
        self._event_routes = {}
        self._step_connections: Dict[str, Dict[str, List[str]]] = {}

        # Build routes from edges (v1.1 pattern)
        for edge in self._edges:
            source = edge.get('source', '')
            source_handle = edge.get('sourceHandle', 'success')
            target = edge.get('target', '')
            edge_type = edge.get('type', edge.get('edge_type', 'control'))

            # Only process control edges for flow routing
            if edge_type == 'resource':
                continue

            if not source or not target:
                continue

            # Build source -> edges index
            if source not in self._edge_index:
                self._edge_index[source] = []
            self._edge_index[source].append(edge)

            # Build event route: "source:handle" -> target
            route_key = f"{source}:{source_handle}"
            self._event_routes[route_key] = target

        # Build routes from step.connections (v1.2 pattern)
        steps = self.workflow.get('steps', [])
        for step in steps:
            step_id = step.get('id', '')
            connections = step.get('connections', {})

            if connections and step_id:
                self._step_connections[step_id] = {}
                for port_name, targets in connections.items():
                    # Handle both array and single value
                    if isinstance(targets, str):
                        targets = [targets]
                    if isinstance(targets, list) and targets:
                        self._step_connections[step_id][port_name] = targets
                        # Also add to _event_routes for backward compat
                        route_key = f"{step_id}:{port_name}"
                        if route_key not in self._event_routes:
                            self._event_routes[route_key] = targets[0]

        log_parts = []
        if self._edges:
            log_parts.append(f"{len(self._edge_index)} sources")
        if self._event_routes:
            log_parts.append(f"{len(self._event_routes)} routes")
        if self._step_connections:
            log_parts.append(f"{len(self._step_connections)} connection-based")
        if log_parts:
            logger.debug(f"Built edge index: {', '.join(log_parts)}")

    async def _execute_steps(self, steps: List[Dict[str, Any]]):
        """
        Execute workflow steps with flow control support

        Supports:
        - Partial execution via start_step and end_step parameters
        - Pause/resume via pause_callback
        - Breakpoints via breakpoints set
        - Single-step execution via step_mode
        - Checkpoint snapshots via checkpoint_callback
        """
        # Determine step range (0-based indices)
        start_idx = self._start_step if self._start_step is not None else 0
        end_idx = self._end_step if self._end_step is not None else len(steps) - 1

        # Clamp to valid range
        start_idx = max(0, min(start_idx, len(steps) - 1))
        end_idx = max(start_idx, min(end_idx, len(steps) - 1))

        if self._start_step is not None or self._end_step is not None:
            logger.info(f"Partial execution: steps {start_idx + 1} to {end_idx + 1} (of {len(steps)})")

        current_idx = start_idx
        parallel_batch = []

        while current_idx <= end_idx:
            # Check for cancellation
            if self._cancelled:
                logger.info("Workflow cancelled, stopping execution")
                break

            step = steps[current_idx]
            step_id = step.get('id', f'step_{current_idx}')

            # Update current_step for external monitoring
            self.current_step = current_idx

            # Check with pause_callback before each step
            # The callback handles both internal pause conditions AND external pause requests
            if self._pause_callback:
                try:
                    # Check if we should pause (breakpoint, step_mode, or explicit pause)
                    internal_should_pause = await self._should_pause_at_step(step_id, current_idx)

                    # Call pause callback - it checks with controller for external pause requests
                    was_paused = await self._pause_callback(
                        current_idx,
                        step_id,
                        self.context.copy(),
                        {},  # node_outputs - context contains previous outputs
                        internal_should_pause  # Pass internal pause state
                    )
                    if was_paused:
                        logger.info(f"Execution resumed after pause at step {current_idx}")
                        # Reset step_requested after stepping
                        self._step_requested = False
                        # Check if cancelled during pause
                        if self._cancelled:
                            logger.info("Workflow cancelled during pause")
                            break
                except Exception as e:
                    logger.warning(f"Pause callback error: {e}")
            else:
                # No callback - check internal pause conditions only
                should_pause = await self._should_pause_at_step(step_id, current_idx)
                if should_pause:
                    logger.warning(f"Pause requested at step {step_id} but no pause_callback configured")

            if step.get('parallel', False):
                parallel_batch.append((current_idx, step))
                current_idx += 1
                continue

            if parallel_batch:
                await self._execute_parallel_steps(parallel_batch)
                parallel_batch = []

            # Execute step and capture result for checkpoint
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
                # Call checkpoint callback after each step
                await self._save_checkpoint(current_idx, step_id, step_status, step_error)

            # If flow control jumps beyond end_idx, stop execution
            if next_idx > end_idx + 1:
                logger.info(f"Flow control jumped to step {next_idx + 1}, stopping at end_step {end_idx + 1}")
                break

            current_idx = next_idx

        if parallel_batch:
            await self._execute_parallel_steps(parallel_batch)

    async def _should_pause_at_step(self, step_id: str, step_index: int) -> bool:
        """
        Determine if execution should pause before this step.

        Pauses when:
        - Breakpoint is set on this step_id
        - Step mode is enabled (pause after each step)
        - Explicit pause was requested
        """
        # Check explicit pause flag
        if self._paused:
            return True

        # Check breakpoint
        if step_id in self._breakpoints:
            logger.info(f"Breakpoint hit at step '{step_id}'")
            self._paused = True
            return True

        # Check step mode (but allow first step to run, pause before second)
        if self._step_mode and step_index > (self._start_step or 0):
            logger.debug(f"Step mode: pausing before step {step_index}")
            self._paused = True
            return True

        return False

    async def _save_checkpoint(
        self,
        step_index: int,
        step_id: str,
        status: str,
        error: Optional[Exception] = None
    ) -> None:
        """
        Save checkpoint after step execution.

        Args:
            step_index: Index of the completed step
            step_id: ID of the completed step
            status: 'success' or 'failed'
            error: Exception if step failed
        """
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
            await self._checkpoint_callback(
                step_index,
                step_id,
                checkpoint_data,
                status
            )
            logger.debug(f"Checkpoint saved for step {step_index} ({step_id})")
        except Exception as e:
            logger.warning(f"Checkpoint callback error: {e}")

    async def _execute_parallel_steps(
        self,
        step_tuples: List[Tuple[int, Dict[str, Any]]],
    ):
        """
        Execute multiple steps in parallel with error handling

        Args:
            step_tuples: List of (step_index, step_config) tuples

        If any step with on_error: stop fails, cancel remaining steps
        """
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
                    logger.warning(f"Parallel step '{step_id}' failed but continuing: {str(result)}")
                    self.context[step_id] = {'ok': False, 'error': str(result)}

        if should_stop and errors:
            step_id, error = errors[0]
            raise StepExecutionError(
                step_id,
                f"Parallel step failed: {str(error)}",
                error
            )

    async def _execute_step_with_flow_control(
        self,
        step_config: Dict[str, Any],
        current_idx: int,
        steps: List[Dict[str, Any]]
    ) -> int:
        """
        Execute a step and handle flow control directives

        Supports both:
        - Legacy: next_step field in result
        - Spec v1.1: __event__ field with edge-based routing

        Returns the next step index to execute
        """
        step_id = step_config.get('id', f'step_{current_idx}')
        result = await self._execute_step(step_config, current_idx)

        if result is None:
            return current_idx + 1

        module_id = step_config.get('module', '')
        if not self._is_flow_control_module(module_id):
            return current_idx + 1

        next_step_id = None
        if isinstance(result, dict):
            # Handle __set_context
            set_context = result.get('__set_context')
            if isinstance(set_context, dict):
                self.context.update(set_context)

            event = result.get('__event__')

            # Priority 1 (Highest): step.connections (v1.2)
            if event and step_id in self._step_connections:
                step_conns = self._step_connections[step_id]
                if event in step_conns and step_conns[event]:
                    next_step_id = step_conns[event][0]
                    logger.debug(f"Connections routing: {step_id}.connections.{event} -> {next_step_id}")

            # Priority 2: Edge-based routing (v1.1)
            if not next_step_id and event and self._event_routes:
                route_key = f"{step_id}:{event}"
                if route_key in self._event_routes:
                    next_step_id = self._event_routes[route_key]
                    logger.debug(f"Edge routing: {route_key} -> {next_step_id}")

            # Priority 3 (Lowest): Legacy next_step field
            if not next_step_id:
                next_step_id = result.get('next_step')
                if next_step_id:
                    logger.debug(f"Legacy routing: next_step -> {next_step_id}")

        if next_step_id and next_step_id in self._step_index:
            return self._step_index[next_step_id]

        return current_idx + 1

    def _is_flow_control_module(self, module_id: str) -> bool:
        """
        Check if module is a flow control module.
        Uses centralized detection from flow_control.py
        """
        return is_flow_control_module(module_id)

    async def _execute_step(
        self,
        step_config: Dict[str, Any],
        step_index: int = 0,
    ) -> Any:
        """
        Execute a single step with timeout and foreach support.

        Delegates to StepExecutor for actual execution.
        """
        step_id = step_config.get('id', f'step_{id(step_config)}')
        module_id = step_config.get('module')
        description = step_config.get('description', '')

        # Check 'when' condition
        should_execute = await self._should_execute_step(step_config)

        # Get resolver for this step
        resolver = self._get_resolver()

        # Delegate to step executor
        result = await self._step_executor.execute_step(
            step_config=step_config,
            step_index=step_index,
            context=self.context,
            resolver=resolver,
            should_execute=should_execute,
        )

        # Log execution if step was executed
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
        """
        Check if step should be executed based on 'when' condition.
        """
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
        """
        Get variable resolver with current context
        """
        workflow_metadata = {
            'id': self.workflow_id,
            'name': self.workflow_name,
            'version': self.workflow_version,
            'description': self.workflow_description
        }

        return VariableResolver(self.params, self.context, workflow_metadata)

    def _collect_output(self) -> Dict[str, Any]:
        """
        Collect workflow output based on output template or default structure
        """
        output_template = self.workflow.get('output', {})
        execution_time_ms = int((self.end_time - self.start_time) * 1000) if self.end_time else None

        metadata = {
            'workflow_id': self.workflow_id,
            'workflow_name': self.workflow_name,
            'workflow_version': self.workflow_version,
            'status': self.status,
            'execution_time_ms': execution_time_ms,
            'steps_executed': len(self.execution_log),
            'timestamp': datetime.now().isoformat()
        }

        if not output_template:
            return {
                'status': self.status,
                'steps': self.context,
                'execution_time_ms': execution_time_ms,
                '__metadata__': metadata
            }

        resolver = self._get_resolver()
        resolved_output = resolver.resolve(output_template)

        if isinstance(resolved_output, dict):
            resolved_output['__metadata__'] = metadata
        else:
            resolved_output = {
                'result': resolved_output,
                '__metadata__': metadata
            }

        return resolved_output

    async def _handle_workflow_error(self, error: Exception):
        """
        Handle workflow-level errors
        """
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
        """
        Get execution summary with all workflow metadata
        """
        execution_time_ms = None
        if self.end_time and self.start_time:
            execution_time_ms = int((self.end_time - self.start_time) * 1000)

        return {
            'workflow_id': self.workflow_id,
            'workflow_name': self.workflow_name,
            'workflow_version': self.workflow_version,
            'workflow_description': self.workflow_description,
            'status': self.status,
            'start_time': datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else None,
            'end_time': datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            'execution_time_ms': execution_time_ms,
            'steps_executed': len(self.execution_log),
            'execution_log': self.execution_log
        }

    def cancel(self):
        """
        Cancel workflow execution
        """
        self._cancelled = True
        self.status = WorkflowStatus.CANCELLED
        logger.info(f"Workflow '{self.workflow_id}' cancelled")

    def pause(self):
        """
        Request workflow to pause at next step.

        Note: This only sets a flag. Actual pause behavior depends on
        the pause_callback provided during initialization.
        """
        self._paused = True
        logger.info(f"Workflow '{self.workflow_id}' pause requested")

    def resume(self):
        """
        Clear pause flag.

        Note: This only clears the flag. Actual resume behavior depends on
        the pause_callback provided during initialization.
        """
        self._paused = False
        logger.info(f"Workflow '{self.workflow_id}' resume requested")

    @property
    def is_paused(self) -> bool:
        """Check if workflow is paused."""
        return self._paused

    @property
    def is_cancelled(self) -> bool:
        """Check if workflow is cancelled."""
        return self._cancelled

    @property
    def step_mode(self) -> bool:
        """Check if step mode is enabled."""
        return self._step_mode

    @step_mode.setter
    def step_mode(self, value: bool) -> None:
        """Enable or disable step mode."""
        self._step_mode = value
        logger.info(f"Step mode {'enabled' if value else 'disabled'}")

    def step_over(self) -> None:
        """
        Execute one step and pause again (step-over debugging).

        Only works when paused. Resumes execution for one step,
        then pauses again before the next step.
        """
        if not self._paused:
            logger.warning("step_over called but workflow is not paused")
            return
        self._step_requested = True
        self._paused = False
        self._step_mode = True  # Enable step mode to pause after this step
        logger.info("Step-over requested")

    def add_breakpoint(self, step_id: str) -> None:
        """
        Add a breakpoint at the specified step.

        Args:
            step_id: The step ID to break at
        """
        self._breakpoints.add(step_id)
        logger.info(f"Breakpoint added at step '{step_id}'")

    def remove_breakpoint(self, step_id: str) -> bool:
        """
        Remove a breakpoint from the specified step.

        Args:
            step_id: The step ID to remove breakpoint from

        Returns:
            True if breakpoint was removed, False if it didn't exist
        """
        if step_id in self._breakpoints:
            self._breakpoints.discard(step_id)
            logger.info(f"Breakpoint removed from step '{step_id}'")
            return True
        return False

    def clear_breakpoints(self) -> None:
        """Remove all breakpoints."""
        count = len(self._breakpoints)
        self._breakpoints.clear()
        logger.info(f"Cleared {count} breakpoints")

    def get_breakpoints(self) -> Set[str]:
        """Get all current breakpoints."""
        return self._breakpoints.copy()

    def inject_context(self, context: Dict[str, Any]) -> None:
        """
        Inject variables into the execution context.

        Used for resuming from checkpoints or modifying state during debugging.

        Args:
            context: Dictionary of variables to inject
        """
        self.context.update(context)
        logger.info(f"Injected {len(context)} variables into context")

    def get_context(self) -> Dict[str, Any]:
        """
        Get a copy of the current execution context.

        Returns:
            Copy of the context dictionary
        """
        return self.context.copy()

    def get_state_snapshot(self) -> Dict[str, Any]:
        """
        Get a complete snapshot of the current execution state.

        Useful for checkpointing and debugging.

        Returns:
            Dictionary containing full execution state
        """
        return {
            'workflow_id': self.workflow_id,
            'workflow_name': self.workflow_name,
            'workflow_version': self.workflow_version,
            'status': self.status,
            'current_step': self.current_step,
            'total_steps': self._total_steps,
            'is_paused': self._paused,
            'is_cancelled': self._cancelled,
            'step_mode': self._step_mode,
            'breakpoints': list(self._breakpoints),
            'context': self.context.copy(),
            'params': self.params.copy(),
            'start_time': self.start_time,
            'execution_log': self.execution_log.copy(),
        }
