"""
Step Executor

Handles execution of individual workflow steps.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..exceptions import StepTimeoutError, StepExecutionError
from ..hooks import ExecutorHooks, HookAction
from .context_builder import create_step_context
from .foreach import execute_foreach_step
from .retry import execute_with_retry

if TYPE_CHECKING:
    from ..variable_resolver import VariableResolver

logger = logging.getLogger(__name__)


class StepExecutor:
    """
    Handles execution of individual workflow steps.

    Responsibilities:
    - Execute single steps with timeout
    - Handle foreach iteration
    - Implement retry logic with backoff
    - Integrate with executor hooks
    - Track execution results
    """

    def __init__(
        self,
        hooks: Optional[ExecutorHooks] = None,
        workflow_id: str = "unknown",
        workflow_name: str = "Unnamed Workflow",
        total_steps: int = 0,
    ):
        """
        Initialize step executor.

        Args:
            hooks: Optional executor hooks for lifecycle events
            workflow_id: ID of the parent workflow (for logging/hooks)
            workflow_name: Name of the parent workflow (for hooks)
            total_steps: Total number of steps in workflow (for hooks)
        """
        from ..hooks import NullHooks
        self._hooks = hooks or NullHooks()
        self._workflow_id = workflow_id
        self._workflow_name = workflow_name
        self._total_steps = total_steps

    def _create_step_context(
        self,
        step_config: Dict[str, Any],
        step_index: int,
        context: Dict[str, Any],
        result: Any = None,
        error: Optional[Exception] = None,
        attempt: int = 1,
        max_attempts: int = 1,
        step_start_time: Optional[float] = None,
    ):
        """Create hook context for step-level events."""
        return create_step_context(
            workflow_id=self._workflow_id,
            workflow_name=self._workflow_name,
            total_steps=self._total_steps,
            step_config=step_config,
            step_index=step_index,
            context=context,
            result=result,
            error=error,
            attempt=attempt,
            max_attempts=max_attempts,
            step_start_time=step_start_time,
        )

    async def execute_step(
        self,
        step_config: Dict[str, Any],
        step_index: int,
        context: Dict[str, Any],
        resolver: "VariableResolver",
        should_execute: bool = True,
    ) -> Optional[Any]:
        """
        Execute a single step with timeout and foreach support.

        Args:
            step_config: Step configuration from workflow
            step_index: Index of the step
            context: Current workflow context (will be modified)
            resolver: Variable resolver instance
            should_execute: Whether the step should execute (from 'when' condition)

        Returns:
            Step execution result, or None if skipped

        Raises:
            StepExecutionError: If step execution fails and on_error is 'stop'
        """
        step_id = step_config.get('id', f'step_{id(step_config)}')
        module_id = step_config.get('module')
        description = step_config.get('description', '')
        timeout = step_config.get('timeout', 0)
        foreach_array = step_config.get('foreach')
        foreach_var = step_config.get('as', 'item')

        if not module_id:
            raise StepExecutionError(step_id, "Step missing 'module' field")

        if not should_execute:
            logger.info(f"Skipping step '{step_id}' (condition not met)")
            return None

        step_start_time = time.time()

        # Call pre-execute hook
        pre_context = self._create_step_context(
            step_config, step_index, context, step_start_time=step_start_time
        )
        pre_result = self._hooks.on_pre_execute(pre_context)

        if pre_result.action == HookAction.SKIP:
            logger.info(f"Skipping step '{step_id}' (hook requested skip)")
            return None
        if pre_result.action == HookAction.ABORT:
            raise StepExecutionError(
                step_id, f"Step aborted by hook: {pre_result.abort_reason}"
            )

        log_message = f"Executing step '{step_id}': {module_id}"
        if description:
            log_message += f" - {description}"
        logger.info(log_message)

        result = None
        error = None

        try:
            if foreach_array:
                result = await execute_foreach_step(
                    step_config, resolver, context, foreach_array, foreach_var,
                    self._execute_single_step, step_index
                )
            else:
                result = await self._execute_single_step(
                    step_config, resolver, context, timeout, step_index
                )

            # Store result in context
            context[step_id] = result

            output_var = step_config.get('output')
            if output_var:
                context[output_var] = result

            logger.info(f"Step '{step_id}' completed successfully")

        except Exception as e:
            error = e
            raise

        finally:
            # Call post-execute hook
            post_context = self._create_step_context(
                step_config,
                step_index,
                context,
                result=result,
                error=error,
                step_start_time=step_start_time,
            )
            self._hooks.on_post_execute(post_context)

        return result

    async def _execute_single_step(
        self,
        step_config: Dict[str, Any],
        resolver: "VariableResolver",
        context: Dict[str, Any],
        timeout: int,
        step_index: int = 0,
    ) -> Any:
        """Execute a single step with optional timeout."""
        step_id = step_config.get('id', f'step_{id(step_config)}')
        module_id = step_config.get('module')
        step_params = step_config.get('params', {})
        resolved_params = resolver.resolve(step_params)
        on_error = step_config.get('on_error', 'stop')

        retry_config = step_config.get('retry', {})

        try:
            if retry_config:
                async def execute_fn():
                    return await self._execute_module_with_timeout(
                        step_id, module_id, resolved_params, context, timeout
                    )

                return await execute_with_retry(
                    step_id=step_id,
                    execute_fn=execute_fn,
                    retry_config=retry_config,
                    hooks=self._hooks,
                    step_config=step_config,
                    step_index=step_index,
                    context=context,
                    workflow_id=self._workflow_id,
                    workflow_name=self._workflow_name,
                    total_steps=self._total_steps,
                )
            else:
                return await self._execute_module_with_timeout(
                    step_id, module_id, resolved_params, context, timeout
                )

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
        """Handle step execution error based on on_error strategy."""
        if on_error == 'continue':
            logger.warning(f"Step '{step_id}' failed but continuing: {str(error)}")
            return {'ok': False, 'error': str(error)}
        else:
            raise error

    async def _execute_module_with_timeout(
        self,
        step_id: str,
        module_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
        timeout: int
    ) -> Any:
        """Execute a module with optional timeout."""
        if timeout <= 0:
            return await self._execute_module(step_id, module_id, params, context)

        try:
            return await asyncio.wait_for(
                self._execute_module(step_id, module_id, params, context),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            raise StepTimeoutError(step_id, timeout)

    async def _execute_module(
        self,
        step_id: str,
        module_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Any:
        """Execute a module and return result."""
        from ...modules.registry import ModuleRegistry

        module_class = ModuleRegistry.get(module_id)

        if not module_class:
            raise StepExecutionError(step_id, f"Module not found: {module_id}")

        module_instance = module_class(params, context)

        try:
            return await module_instance.run()
        except Exception as e:
            raise StepExecutionError(step_id, f"Step failed: {str(e)}", e)
