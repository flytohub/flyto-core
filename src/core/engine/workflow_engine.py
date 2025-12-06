"""
Workflow Engine - Execute YAML workflows with flow control support
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from .variable_resolver import VariableResolver
from ..constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY_MS,
    EXPONENTIAL_BACKOFF_BASE,
    WorkflowStatus,
)


logger = logging.getLogger(__name__)


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

    def __init__(self, workflow: Dict[str, Any], params: Dict[str, Any] = None):
        """
        Initialize workflow engine

        Args:
            workflow: Parsed workflow YAML
            params: Workflow input parameters
        """
        self.workflow = workflow
        self.params = self._parse_params(workflow.get('params', []), params or {})
        self.context = {}
        self.execution_log = []

        self.workflow_id = workflow.get('id', 'unknown')
        self.workflow_name = workflow.get('name', 'Unnamed Workflow')

        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.status: str = WorkflowStatus.PENDING

        self._step_index: Dict[str, int] = {}
        self._visited_gotos: Dict[str, int] = {}

    def _parse_params(
        self,
        param_schema: List[Dict[str, Any]],
        provided_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Parse parameter schema and merge with provided values
        """
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
        """
        current_idx = 0
        parallel_batch = []

        while current_idx < len(steps):
            step = steps[current_idx]

            if step.get('parallel', False):
                parallel_batch.append((current_idx, step))
                current_idx += 1
                continue

            if parallel_batch:
                await self._execute_parallel_steps([s for _, s in parallel_batch])
                parallel_batch = []

            next_idx = await self._execute_step_with_flow_control(step, current_idx, steps)
            current_idx = next_idx

        if parallel_batch:
            await self._execute_parallel_steps([s for _, s in parallel_batch])

    async def _execute_parallel_steps(self, steps: List[Dict[str, Any]]):
        """
        Execute multiple steps in parallel
        """
        logger.info(f"Executing {len(steps)} steps in parallel")

        tasks = [self._execute_step(step) for step in steps]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                step_id = steps[i].get('id', f'step_{i}')
                raise StepExecutionError(
                    step_id,
                    f"Parallel step failed: {str(result)}",
                    result
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
        Execute a single step
        """
        step_id = step_config.get('id', f'step_{id(step_config)}')
        module_id = step_config.get('module')

        if not module_id:
            raise StepExecutionError(step_id, "Step missing 'module' field")

        if not await self._should_execute_step(step_config):
            logger.info(f"Skipping step '{step_id}' (condition not met)")
            return None

        logger.info(f"Executing step '{step_id}': {module_id}")

        resolver = self._get_resolver()
        step_params = step_config.get('params', {})
        resolved_params = resolver.resolve(step_params)

        retry_config = step_config.get('retry', {})
        if retry_config:
            result = await self._execute_with_retry(
                step_id, module_id, resolved_params, retry_config
            )
        else:
            result = await self._execute_module(step_id, module_id, resolved_params)

        self.context[step_id] = result

        output_var = step_config.get('output')
        if output_var:
            self.context[output_var] = result

        self.execution_log.append({
            'step_id': step_id,
            'module_id': module_id,
            'status': 'success',
            'timestamp': datetime.now().isoformat()
        })

        logger.info(f"Step '{step_id}' completed successfully")

        return result

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
        retry_config: Dict[str, Any]
    ) -> Any:
        """
        Execute step with retry logic
        """
        max_retries = retry_config.get('count', DEFAULT_MAX_RETRIES)
        delay_ms = retry_config.get('delay_ms', DEFAULT_RETRY_DELAY_MS)
        backoff = retry_config.get('backoff', 'linear')

        last_error: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                return await self._execute_module(step_id, module_id, params)
            except Exception as e:
                last_error = e

                if attempt < max_retries:
                    if backoff == 'exponential':
                        wait_time = (delay_ms / 1000) * (EXPONENTIAL_BACKOFF_BASE ** attempt)
                    else:
                        wait_time = delay_ms / 1000

                    logger.warning(
                        f"Step '{step_id}' failed (attempt {attempt + 1}/{max_retries + 1}). "
                        f"Retrying in {wait_time}s..."
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
        Execute a module
        """
        from ..modules.registry import ModuleRegistry

        module_class = ModuleRegistry.get(module_id)

        if not module_class:
            raise StepExecutionError(step_id, f"Module not found: {module_id}")

        module_instance = module_class(params, self.context)

        try:
            return await module_instance.run()
        except Exception as e:
            on_error = params.get('on_error', 'fail')

            if on_error == 'continue':
                logger.warning(f"Step '{step_id}' failed but continuing: {str(e)}")
                return {'status': 'failure', 'error': str(e)}
            elif on_error == 'rollback':
                logger.error(f"Step '{step_id}' failed, initiating rollback")
                raise StepExecutionError(step_id, f"Step failed: {str(e)}", e)
            else:
                raise StepExecutionError(step_id, f"Step failed: {str(e)}", e)

    def _get_resolver(self) -> VariableResolver:
        """
        Get variable resolver with current context
        """
        workflow_metadata = {
            'id': self.workflow_id,
            'name': self.workflow_name,
            'version': self.workflow.get('version', '1.0.0')
        }

        return VariableResolver(self.params, self.context, workflow_metadata)

    def _collect_output(self) -> Dict[str, Any]:
        """
        Collect workflow output
        """
        output_template = self.workflow.get('output', {})

        if not output_template:
            return {
                'status': self.status,
                'steps': self.context,
                'execution_time': self.end_time - self.start_time if self.end_time else None
            }

        resolver = self._get_resolver()
        resolved_output = resolver.resolve(output_template)

        resolved_output['__metadata__'] = {
            'workflow_id': self.workflow_id,
            'workflow_name': self.workflow_name,
            'status': self.status,
            'execution_time': self.end_time - self.start_time if self.end_time else None,
            'timestamp': datetime.now().isoformat()
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
        Get execution summary
        """
        return {
            'workflow_id': self.workflow_id,
            'workflow_name': self.workflow_name,
            'status': self.status,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'execution_time': self.end_time - self.start_time if self.end_time else None,
            'steps_executed': len(self.execution_log),
            'execution_log': self.execution_log
        }
