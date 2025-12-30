"""
Retry Logic

Step execution retry with backoff strategies.
"""

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, Optional

from ..exceptions import StepExecutionError, StepTimeoutError
from ..hooks import ExecutorHooks, HookAction
from ...constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY_MS,
    EXPONENTIAL_BACKOFF_BASE,
)
from .context_builder import create_step_context

logger = logging.getLogger(__name__)


async def execute_with_retry(
    step_id: str,
    execute_fn: Callable[[], Coroutine[Any, Any, Any]],
    retry_config: Dict[str, Any],
    hooks: Optional[ExecutorHooks] = None,
    step_config: Optional[Dict[str, Any]] = None,
    step_index: int = 0,
    context: Optional[Dict[str, Any]] = None,
    workflow_id: str = "unknown",
    workflow_name: str = "Unnamed Workflow",
    total_steps: int = 0,
) -> Any:
    """
    Execute with retry logic and optional timeout per attempt.

    Args:
        step_id: ID of the step
        execute_fn: Async function to execute
        retry_config: Retry configuration (count, delay_ms, backoff)
        hooks: Optional executor hooks
        step_config: Full step configuration (for hooks)
        step_index: Index of the step
        context: Current workflow context
        workflow_id: Parent workflow ID
        workflow_name: Parent workflow name
        total_steps: Total steps in workflow

    Returns:
        Execution result

    Raises:
        StepExecutionError: If all retry attempts fail
    """
    from ..hooks import NullHooks
    hooks = hooks or NullHooks()
    context = context or {}

    max_retries = retry_config.get('count', DEFAULT_MAX_RETRIES)
    delay_ms = retry_config.get('delay_ms', DEFAULT_RETRY_DELAY_MS)
    backoff = retry_config.get('backoff', 'linear')

    last_error: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            return await execute_fn()
        except (StepTimeoutError, StepExecutionError, Exception) as e:
            last_error = e

            if attempt < max_retries:
                wait_time = _calculate_wait_time(delay_ms, attempt, backoff)

                logger.warning(
                    f"Step '{step_id}' failed (attempt {attempt + 1}/{max_retries + 1}). "
                    f"Retrying in {wait_time:.1f}s..."
                )

                # Call retry hook
                if step_config:
                    retry_context = create_step_context(
                        workflow_id=workflow_id,
                        workflow_name=workflow_name,
                        total_steps=total_steps,
                        step_config=step_config,
                        step_index=step_index,
                        context=context,
                        error=e,
                        attempt=attempt + 2,
                        max_attempts=max_retries + 1,
                    )
                    retry_result = hooks.on_retry(retry_context)
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


def _calculate_wait_time(delay_ms: int, attempt: int, backoff: str) -> float:
    """Calculate wait time based on backoff strategy."""
    if backoff == 'exponential':
        return (delay_ms / 1000) * (EXPONENTIAL_BACKOFF_BASE ** attempt)
    elif backoff == 'linear':
        return (delay_ms / 1000) * (attempt + 1)
    else:
        return delay_ms / 1000
