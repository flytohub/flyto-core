"""
Workflow Engine - Execute YAML workflows with flow control support

Supports:
- Variable resolution (${params.x}, ${step.result}, ${env.VAR})
- Flow control (when, retry, parallel, branch, switch, goto)
- Error handling (on_error: stop/continue/retry)
- Timeout per step
- Foreach iteration with result aggregation
- Workflow-level output definition
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from .variable_resolver import VariableResolver
from ..constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY_MS,
    DEFAULT_TIMEOUT_SECONDS,
    EXPONENTIAL_BACKOFF_BASE,
    WorkflowStatus,
)


logger = logging.getLogger(__name__)


class StepTimeoutError(Exception):
    """Raised when a step execution times out"""
    def __init__(self, step_id: str, timeout: int):
        self.step_id = step_id
        self.timeout = timeout
        super().__init__(f"Step '{step_id}' timed out after {timeout} seconds")


class WorkflowExecutionError(Exception):
    """Raised when workflow execution fails"""
    pass


class StepExecutionError(Exception):
    """Raised when a step execution fails"""
    def __init__(self, step_id: str, message: str, original_error: Exception = None):
        self.step_id = step_id
        self.original_error = original_error
        super().__init__(message)


class WorkflowEngine:
    """
    Execute YAML workflows with full support for:
    - Variable resolution
    - Flow control (when, retry, parallel, branch, switch, goto)
    - Error handling
    - Context management
    """

    FLOW_CONTROL_MODULES = frozenset([
        'flow.branch',
        'flow.switch',
        'flow.goto',
        'flow.loop',
        'loop',
        'foreach',
        'core.flow.branch',
        'core.flow.switch',
        'core.flow.goto',
        'core.flow.loop',
    ])

    def __init__(
        self,
        workflow: Dict[str, Any],
        params: Dict[str, Any] = None,
        start_step: Optional[int] = None,
        end_step: Optional[int] = None
    ):
        """
        Initialize workflow engine

        Args:
            workflow: Parsed workflow YAML
            params: Workflow input parameters
            start_step: Start from this step index (0-based, inclusive)
            end_step: End at this step index (0-based, inclusive)
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

        # Current step index for progress tracking (exposed for external monitoring)
        self.current_step: int = 0

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

    async def execute(self) -> Dict[str, Any]:
        """
        Execute the workflow
        """
        self.start_time = time.time()
        self.status = WorkflowStatus.RUNNING

        logger.info(f"Starting workflow: {self.workflow_name} (ID: {self.workflow_id})")

        try:
            steps = self.workflow.get('steps', [])
            if not steps:
                raise WorkflowExecutionError("No steps defined in workflow")

            self._build_step_index(steps)
            await self._execute_steps(steps)

            self.status = WorkflowStatus.COMPLETED
            self.end_time = time.time()

            logger.info(
                f"Workflow completed successfully in {self.end_time - self.start_time:.2f}s"
            )

            return self._collect_output()

        except Exception as e:
            self.status = WorkflowStatus.FAILURE
            self.end_time = time.time()

            logger.error(f"Workflow failed: {str(e)}")
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

    async def _execute_steps(self, steps: List[Dict[str, Any]]):
        """
        Execute workflow steps with flow control support

        Supports partial execution via start_step and end_step parameters.
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
            step = steps[current_idx]

            # Update current_step for external monitoring
            self.current_step = current_idx

            if step.get('parallel', False):
                parallel_batch.append((current_idx, step))
                current_idx += 1
                continue

            if parallel_batch:
                await self._execute_parallel_steps([s for _, s in parallel_batch])
                parallel_batch = []

            next_idx = await self._execute_step_with_flow_control(step, current_idx, steps)

            # If flow control jumps beyond end_idx, stop execution
            if next_idx > end_idx + 1:
                logger.info(f"Flow control jumped to step {next_idx + 1}, stopping at end_step {end_idx + 1}")
                break

            current_idx = next_idx

        if parallel_batch:
            await self._execute_parallel_steps([s for _, s in parallel_batch])

    async def _execute_parallel_steps(self, steps: List[Dict[str, Any]]):
        """
        Execute multiple steps in parallel with error handling

        If any step with on_error: stop fails, cancel remaining steps
        """
        logger.info(f"Executing {len(steps)} steps in parallel")

        tasks = [asyncio.create_task(self._execute_step(step)) for step in steps]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        errors = []
        should_stop = False

        for i, result in enumerate(results):
            step_id = steps[i].get('id', f'step_{i}')
            on_error = steps[i].get('on_error', 'stop')

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

        Returns the next step index to execute
        """
        result = await self._execute_step(step_config)

        if result is None:
            return current_idx + 1

        module_id = step_config.get('module', '')
        if not self._is_flow_control_module(module_id):
            return current_idx + 1

        next_step_id = None
        if isinstance(result, dict):
            next_step_id = result.get('next_step')

            set_context = result.get('__set_context')
            if isinstance(set_context, dict):
                self.context.update(set_context)

        if next_step_id and next_step_id in self._step_index:
            return self._step_index[next_step_id]

        return current_idx + 1

    def _is_flow_control_module(self, module_id: str) -> bool:
        """
        Check if module is a flow control module
        """
        return module_id in self.FLOW_CONTROL_MODULES

    async def _execute_step(self, step_config: Dict[str, Any]) -> Any:
        """
        Execute a single step with timeout and foreach support
        """
        step_id = step_config.get('id', f'step_{id(step_config)}')
        module_id = step_config.get('module')
        description = step_config.get('description', '')
        timeout = step_config.get('timeout', 0)
        foreach_array = step_config.get('foreach')
        foreach_var = step_config.get('as', 'item')

        if not module_id:
            raise StepExecutionError(step_id, "Step missing 'module' field")

        if not await self._should_execute_step(step_config):
            logger.info(f"Skipping step '{step_id}' (condition not met)")
            return None

        log_message = f"Executing step '{step_id}': {module_id}"
        if description:
            log_message += f" - {description}"
        logger.info(log_message)

        resolver = self._get_resolver()

        if foreach_array:
            result = await self._execute_foreach_step(
                step_config, resolver, foreach_array, foreach_var
            )
        else:
            result = await self._execute_single_step(
                step_config, resolver, timeout
            )

        self.context[step_id] = result

        output_var = step_config.get('output')
        if output_var:
            self.context[output_var] = result

        self.execution_log.append({
            'step_id': step_id,
            'module_id': module_id,
            'description': description,
            'status': 'success',
            'timestamp': datetime.now().isoformat()
        })

        logger.info(f"Step '{step_id}' completed successfully")

        return result

    async def _execute_single_step(
        self,
        step_config: Dict[str, Any],
        resolver: VariableResolver,
        timeout: int
    ) -> Any:
        """
        Execute a single step with optional timeout
        """
        step_id = step_config.get('id', f'step_{id(step_config)}')
        module_id = step_config.get('module')
        step_params = step_config.get('params', {})
        resolved_params = resolver.resolve(step_params)
        on_error = step_config.get('on_error', 'stop')

        retry_config = step_config.get('retry', {})

        try:
            if retry_config:
                coro = self._execute_with_retry(
                    step_id, module_id, resolved_params, retry_config, timeout
                )
            else:
                coro = self._execute_module_with_timeout(
                    step_id, module_id, resolved_params, timeout
                )

            return await coro

        except StepTimeoutError as e:
            return self._handle_step_error(step_id, e, on_error)
        except StepExecutionError as e:
            return self._handle_step_error(step_id, e, on_error)

    def _handle_step_error(
        self,
        step_id: str,
        error: Exception,
        on_error: str
    ) -> Any:
        """
        Handle step execution error based on on_error strategy
        """
        if on_error == 'continue':
            logger.warning(f"Step '{step_id}' failed but continuing: {str(error)}")
            return {'ok': False, 'error': str(error)}
        else:
            raise error

    async def _execute_foreach_step(
        self,
        step_config: Dict[str, Any],
        resolver: VariableResolver,
        foreach_array: Any,
        foreach_var: str
    ) -> List[Any]:
        """
        Execute a step for each item in an array

        Returns array of results matching input array order
        """
        step_id = step_config.get('id', f'step_{id(step_config)}')
        on_error = step_config.get('on_error', 'stop')
        timeout = step_config.get('timeout', 0)

        resolved_array = resolver.resolve(foreach_array)

        if not isinstance(resolved_array, list):
            raise StepExecutionError(
                step_id,
                f"foreach expects array, got {type(resolved_array).__name__}"
            )

        logger.info(f"Executing foreach step '{step_id}' with {len(resolved_array)} items")

        results = []
        for index, item in enumerate(resolved_array):
            self.context[foreach_var] = item
            self.context['__foreach_index__'] = index

            try:
                result = await self._execute_single_step(
                    step_config, resolver, timeout
                )
                results.append(result)
            except Exception as e:
                if on_error == 'continue':
                    logger.warning(
                        f"Foreach iteration {index} failed, continuing: {str(e)}"
                    )
                    results.append({'ok': False, 'error': str(e), 'index': index})
                else:
                    raise StepExecutionError(
                        step_id,
                        f"Foreach iteration {index} failed: {str(e)}",
                        e
                    )

        if foreach_var in self.context:
            del self.context[foreach_var]
        if '__foreach_index__' in self.context:
            del self.context['__foreach_index__']

        return results

    async def _execute_module_with_timeout(
        self,
        step_id: str,
        module_id: str,
        params: Dict[str, Any],
        timeout: int
    ) -> Any:
        """
        Execute a module with optional timeout
        """
        if timeout <= 0:
            return await self._execute_module(step_id, module_id, params)

        try:
            return await asyncio.wait_for(
                self._execute_module(step_id, module_id, params),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            raise StepTimeoutError(step_id, timeout)

    async def _should_execute_step(self, step_config: Dict[str, Any]) -> bool:
        """
        Check if step should be executed based on 'when' condition
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

    async def _execute_with_retry(
        self,
        step_id: str,
        module_id: str,
        params: Dict[str, Any],
        retry_config: Dict[str, Any],
        timeout: int = 0
    ) -> Any:
        """
        Execute step with retry logic and optional timeout per attempt
        """
        max_retries = retry_config.get('count', DEFAULT_MAX_RETRIES)
        delay_ms = retry_config.get('delay_ms', DEFAULT_RETRY_DELAY_MS)
        backoff = retry_config.get('backoff', 'linear')

        last_error: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                return await self._execute_module_with_timeout(
                    step_id, module_id, params, timeout
                )
            except (StepTimeoutError, StepExecutionError, Exception) as e:
                last_error = e

                if attempt < max_retries:
                    if backoff == 'exponential':
                        wait_time = (delay_ms / 1000) * (EXPONENTIAL_BACKOFF_BASE ** attempt)
                    elif backoff == 'linear':
                        wait_time = (delay_ms / 1000) * (attempt + 1)
                    else:
                        wait_time = delay_ms / 1000

                    logger.warning(
                        f"Step '{step_id}' failed (attempt {attempt + 1}/{max_retries + 1}). "
                        f"Retrying in {wait_time:.1f}s..."
                    )

                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Step '{step_id}' failed after {max_retries + 1} attempts")

        raise StepExecutionError(
            step_id,
            f"Step failed after {max_retries + 1} attempts",
            last_error
        )

    async def _execute_module(
        self,
        step_id: str,
        module_id: str,
        params: Dict[str, Any]
    ) -> Any:
        """
        Execute a module and return result
        """
        from ..modules.registry import ModuleRegistry

        module_class = ModuleRegistry.get(module_id)

        if not module_class:
            raise StepExecutionError(step_id, f"Module not found: {module_id}")

        module_instance = module_class(params, self.context)

        try:
            return await module_instance.run()
        except Exception as e:
            raise StepExecutionError(step_id, f"Step failed: {str(e)}", e)

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
