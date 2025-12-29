"""
Step Executor - Single step execution with retry, timeout, and foreach support

Extracted from workflow_engine.py for better modularity and testability.
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .exceptions import StepTimeoutError, StepExecutionError
from .hooks import (
    ExecutorHooks,
    HookContext,
    HookResult,
    HookAction,
)
from ..constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY_MS,
    EXPONENTIAL_BACKOFF_BASE,
)

if TYPE_CHECKING:
    from .variable_resolver import VariableResolver

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

    This class is stateless for step execution - all state is passed
    through parameters or returned as results.
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
        from .hooks import NullHooks
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
    ) -> HookContext:
        """
        Create hook context for step-level events.

        Args:
            step_config: Step configuration dictionary
            step_index: Index of the step in workflow
            context: Current workflow context
            result: Step execution result (if any)
            error: Exception if step failed
            attempt: Current retry attempt number
            max_attempts: Total retry attempts allowed
            step_start_time: When step execution started

        Returns:
            HookContext for hook callbacks
        """
        step_id = step_config.get('id', f'step_{step_index}')
        module_id = step_config.get('module', '')
        step_params = step_config.get('params', {})

        elapsed_ms = 0.0
        if step_start_time:
            elapsed_ms = (time.time() - step_start_time) * 1000

        hook_context = HookContext(
            workflow_id=self._workflow_id,
            workflow_name=self._workflow_name,
            step_id=step_id,
            step_index=step_index,
            total_steps=self._total_steps,
            module_id=module_id,
            params=step_params,
            variables=context.copy(),
            started_at=datetime.fromtimestamp(step_start_time) if step_start_time else None,
            elapsed_ms=elapsed_ms,
            result=result,
            attempt=attempt,
            max_attempts=max_attempts,
        )

        if error:
            hook_context.error = error
            hook_context.error_type = type(error).__name__
            hook_context.error_message = str(error)

        return hook_context

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
                result = await self._execute_foreach_step(
                    step_config, resolver, context, foreach_array, foreach_var, step_index
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
        """
        Execute a single step with optional timeout.

        Args:
            step_config: Step configuration
            resolver: Variable resolver for parameter resolution
            context: Current workflow context
            timeout: Timeout in seconds (0 for no timeout)
            step_index: Index of the step

        Returns:
            Step execution result
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
                    step_id, module_id, resolved_params, context, retry_config, timeout,
                    step_config, step_index
                )
            else:
                coro = self._execute_module_with_timeout(
                    step_id, module_id, resolved_params, context, timeout
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
        Handle step execution error based on on_error strategy.

        Args:
            step_id: ID of the failed step
            error: The exception that occurred
            on_error: Error handling strategy ('stop' or 'continue')

        Returns:
            Error result dict if continuing, otherwise raises

        Raises:
            The original error if on_error is 'stop'
        """
        if on_error == 'continue':
            logger.warning(f"Step '{step_id}' failed but continuing: {str(error)}")
            return {'ok': False, 'error': str(error)}
        else:
            raise error

    async def _execute_foreach_step(
        self,
        step_config: Dict[str, Any],
        resolver: "VariableResolver",
        context: Dict[str, Any],
        foreach_array: Any,
        foreach_var: str,
        step_index: int = 0,
    ) -> List[Any]:
        """
        Execute a step for each item in an array.

        Args:
            step_config: Step configuration
            resolver: Variable resolver
            context: Current workflow context
            foreach_array: Array to iterate over (may be variable reference)
            foreach_var: Variable name for current item
            step_index: Index of the step

        Returns:
            Array of results matching input array order
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
            context[foreach_var] = item
            context['__foreach_index__'] = index

            try:
                result = await self._execute_single_step(
                    step_config, resolver, context, timeout, step_index
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

        # Clean up foreach variables
        if foreach_var in context:
            del context[foreach_var]
        if '__foreach_index__' in context:
            del context['__foreach_index__']

        return results

    async def _execute_module_with_timeout(
        self,
        step_id: str,
        module_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
        timeout: int
    ) -> Any:
        """
        Execute a module with optional timeout.

        Args:
            step_id: ID of the step
            module_id: ID of the module to execute
            params: Resolved parameters
            context: Current workflow context
            timeout: Timeout in seconds (0 for no timeout)

        Returns:
            Module execution result

        Raises:
            StepTimeoutError: If execution times out
        """
        if timeout <= 0:
            return await self._execute_module(step_id, module_id, params, context)

        try:
            return await asyncio.wait_for(
                self._execute_module(step_id, module_id, params, context),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            raise StepTimeoutError(step_id, timeout)

    async def _execute_with_retry(
        self,
        step_id: str,
        module_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
        retry_config: Dict[str, Any],
        timeout: int = 0,
        step_config: Optional[Dict[str, Any]] = None,
        step_index: int = 0,
    ) -> Any:
        """
        Execute step with retry logic and optional timeout per attempt.

        Args:
            step_id: ID of the step
            module_id: ID of the module to execute
            params: Resolved parameters
            context: Current workflow context
            retry_config: Retry configuration (count, delay_ms, backoff)
            timeout: Timeout per attempt in seconds
            step_config: Full step configuration (for hooks)
            step_index: Index of the step

        Returns:
            Module execution result

        Raises:
            StepExecutionError: If all retry attempts fail
        """
        max_retries = retry_config.get('count', DEFAULT_MAX_RETRIES)
        delay_ms = retry_config.get('delay_ms', DEFAULT_RETRY_DELAY_MS)
        backoff = retry_config.get('backoff', 'linear')

        last_error: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                return await self._execute_module_with_timeout(
                    step_id, module_id, params, context, timeout
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

                    # Call retry hook
                    if step_config:
                        retry_context = self._create_step_context(
                            step_config,
                            step_index,
                            context,
                            error=e,
                            attempt=attempt + 2,
                            max_attempts=max_retries + 1,
                        )
                        retry_result = self._hooks.on_retry(retry_context)
                        if retry_result.action == HookAction.ABORT:
                            raise StepExecutionError(
                                step_id,
                                f"Retry aborted by hook: {retry_result.abort_reason}",
                                e
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
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Any:
        """
        Execute a module and return result.

        Args:
            step_id: ID of the step
            module_id: ID of the module to execute
            params: Resolved parameters
            context: Current workflow context

        Returns:
            Module execution result

        Raises:
            StepExecutionError: If module not found or execution fails
        """
        from ..modules.registry import ModuleRegistry

        module_class = ModuleRegistry.get(module_id)

        if not module_class:
            raise StepExecutionError(step_id, f"Module not found: {module_id}")

        module_instance = module_class(params, context)

        try:
            return await module_instance.run()
        except Exception as e:
            raise StepExecutionError(step_id, f"Step failed: {str(e)}", e)


# =============================================================================
# Factory Function
# =============================================================================

def create_step_executor(
    hooks: Optional[ExecutorHooks] = None,
    workflow_id: str = "unknown",
    workflow_name: str = "Unnamed Workflow",
    total_steps: int = 0,
) -> StepExecutor:
    """
    Create a step executor instance.

    Args:
        hooks: Optional executor hooks
        workflow_id: Parent workflow ID
        workflow_name: Parent workflow name
        total_steps: Total steps in workflow

    Returns:
        Configured StepExecutor instance
    """
    return StepExecutor(
        hooks=hooks,
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        total_steps=total_steps,
    )
