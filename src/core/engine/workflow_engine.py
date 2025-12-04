"""
Workflow Engine - Execute YAML workflows
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from .variable_resolver import VariableResolver
from ..constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY_MS,
    EXPONENTIAL_BACKOFF_BASE,
    WorkflowStatus,
    ErrorMessages,
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
    - Flow control (when, retry, parallel)
    - Error handling
    - Context management
    """

    def __init__(self, workflow: Dict[str, Any], params: Dict[str, Any] = None):
        """
        Initialize workflow engine

        Args:
            workflow: Parsed workflow YAML
            params: Workflow input parameters
        """
        self.workflow = workflow

        # Parse params - convert list format to dict with defaults
        self.params = self._parse_params(workflow.get('params', []), params or {})

        self.context = {}
        self.execution_log = []

        # Workflow metadata
        self.workflow_id = workflow.get('id', 'unknown')
        self.workflow_name = workflow.get('name', 'Unnamed Workflow')

        # Execution state
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.status: str = WorkflowStatus.PENDING

    def _parse_params(self, param_schema: List[Dict[str, Any]], provided_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse parameter schema and merge with provided values

        Args:
            param_schema: List of parameter definitions from YAML
            provided_params: User-provided parameter values

        Returns:
            Dict of parameter name -> value with defaults applied
        """
        result = {}

        # If param_schema is already a dict, return it merged with provided
        if isinstance(param_schema, dict):
            result = param_schema.copy()
            result.update(provided_params)
            return result

        # Parse list format
        for param_def in param_schema:
            param_name = param_def.get('name')
            if not param_name:
                continue

            # Use provided value if available, otherwise use default
            if param_name in provided_params:
                result[param_name] = provided_params[param_name]
            elif 'default' in param_def:
                result[param_name] = param_def['default']

        return result

    async def execute(self) -> Dict[str, Any]:
        """
        Execute the workflow

        Returns:
            Workflow output
        """
        self.start_time = time.time()
        self.status = WorkflowStatus.RUNNING

        logger.info(f"Starting workflow: {self.workflow_name} (ID: {self.workflow_id})")

        try:
            # Get steps
            steps = self.workflow.get('steps', [])
            if not steps:
                raise WorkflowExecutionError("No steps defined in workflow")

            # Execute steps
            await self._execute_steps(steps)

            # Update status before collecting output
            self.status = WorkflowStatus.COMPLETED
            self.end_time = time.time()

            logger.info(f"Workflow completed successfully in {self.end_time - self.start_time:.2f}s")

            # Collect output (after status is set)
            output = self._collect_output()

            return output

        except Exception as e:
            self.status = WorkflowStatus.FAILURE
            self.end_time = time.time()

            logger.error(f"Workflow failed: {str(e)}")

            # Handle workflow-level error
            await self._handle_workflow_error(e)

            raise WorkflowExecutionError(f"Workflow execution failed: {str(e)}") from e

    async def _execute_steps(self, steps: List[Dict[str, Any]]):
        """Execute all workflow steps"""
        # Separate parallel and sequential steps
        parallel_batch = []

        for step in steps:
            # Check if step should run in parallel
            if step.get('parallel', False):
                parallel_batch.append(step)
            else:
                # Execute any pending parallel batch first
                if parallel_batch:
                    await self._execute_parallel_steps(parallel_batch)
                    parallel_batch = []

                # Execute this step sequentially
                await self._execute_step(step)

        # Execute any remaining parallel steps
        if parallel_batch:
            await self._execute_parallel_steps(parallel_batch)

    async def _execute_parallel_steps(self, steps: List[Dict[str, Any]]):
        """Execute multiple steps in parallel"""
        logger.info(f"Executing {len(steps)} steps in parallel")

        tasks = [self._execute_step(step) for step in steps]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for errors
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                step_id = steps[i].get('id', f'step_{i}')
                raise StepExecutionError(step_id, f"Parallel step failed: {str(result)}", result)

    async def _execute_step(self, step_config: Dict[str, Any]) -> Any:
        """Execute a single step"""
        step_id = step_config.get('id', f'step_{id(step_config)}')
        module_id = step_config.get('module')

        if not module_id:
            raise StepExecutionError(step_id, "Step missing 'module' field")

        # Check if step should be executed (conditional execution)
        if not await self._should_execute_step(step_config):
            logger.info(f"Skipping step '{step_id}' (condition not met)")
            return None

        logger.info(f"Executing step '{step_id}': {module_id}")

        # Get resolver with current context
        resolver = self._get_resolver()

        # Resolve step parameters
        step_params = step_config.get('params', {})
        resolved_params = resolver.resolve(step_params)

        # Execute with retry if configured
        retry_config = step_config.get('retry', {})
        if retry_config:
            result = await self._execute_with_retry(
                step_id, module_id, resolved_params, retry_config
            )
        else:
            result = await self._execute_module(step_id, module_id, resolved_params)

        # Store result in context
        self.context[step_id] = result

        # Log execution
        self.execution_log.append({
            'step_id': step_id,
            'module_id': module_id,
            'status': 'success',
            'timestamp': datetime.now().isoformat()
        })

        logger.info(f"Step '{step_id}' completed successfully")

        return result

    async def _should_execute_step(self, step_config: Dict[str, Any]) -> bool:
        """Check if step should be executed based on 'when' condition"""
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
        """Execute step with retry logic"""
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
                    # Calculate delay based on backoff strategy
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

        raise StepExecutionError(step_id, f"Step failed after {max_retries + 1} attempts", last_error)

    async def _execute_module(
        self,
        step_id: str,
        module_id: str,
        params: Dict[str, Any]
    ) -> Any:
        """Execute a module"""
        # Use relative import to avoid coupling issues
        from ..modules.registry import ModuleRegistry

        # Get module class
        module_class = ModuleRegistry.get(module_id)

        if not module_class:
            raise StepExecutionError(step_id, f"Module not found: {module_id}")

        # Create module instance
        module_instance = module_class(params, self.context)

        try:
            # Execute module
            result = await module_instance.run()
            return result

        except Exception as e:
            # Handle step error based on configuration
            on_error = params.get('on_error', 'fail')

            if on_error == 'continue':
                logger.warning(f"Step '{step_id}' failed but continuing: {str(e)}")
                return {'status': 'failure', 'error': str(e)}
            elif on_error == 'rollback':
                logger.error(f"Step '{step_id}' failed, initiating rollback")
                raise StepExecutionError(step_id, f"Step failed: {str(e)}", e)
            else:  # 'fail'
                raise StepExecutionError(step_id, f"Step failed: {str(e)}", e)

    def _get_resolver(self) -> VariableResolver:
        """Get variable resolver with current context"""
        workflow_metadata = {
            'id': self.workflow_id,
            'name': self.workflow_name,
            'version': self.workflow.get('version', '1.0.0')
        }

        return VariableResolver(self.params, self.context, workflow_metadata)

    def _collect_output(self) -> Dict[str, Any]:
        """Collect workflow output"""
        output_template = self.workflow.get('output', {})

        if not output_template:
            # Return all step results
            return {
                'status': self.status,
                'steps': self.context,
                'execution_time': self.end_time - self.start_time if self.end_time else None
            }

        # Resolve output template
        resolver = self._get_resolver()
        resolved_output = resolver.resolve(output_template)

        # Add metadata
        resolved_output['__metadata__'] = {
            'workflow_id': self.workflow_id,
            'workflow_name': self.workflow_name,
            'status': self.status,
            'execution_time': self.end_time - self.start_time if self.end_time else None,
            'timestamp': datetime.now().isoformat()
        }

        return resolved_output

    async def _handle_workflow_error(self, error: Exception):
        """Handle workflow-level errors"""
        on_error_config = self.workflow.get('on_error', {})

        if not on_error_config:
            return

        # Execute rollback steps if configured
        rollback_steps = on_error_config.get('rollback_steps', [])
        if rollback_steps:
            logger.info("Executing rollback steps...")
            try:
                await self._execute_steps(rollback_steps)
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {str(rollback_error)}")

        # TODO: Send notification if configured
        notify_config = on_error_config.get('notify')
        if notify_config:
            logger.info(f"Error notification: {notify_config}")

    def get_execution_summary(self) -> Dict[str, Any]:
        """Get execution summary"""
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
