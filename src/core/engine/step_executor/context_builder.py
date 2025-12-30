"""
Step Context Builder

Creates hook context for step-level events.
"""

import time
from datetime import datetime
from typing import Any, Dict, Optional

from ..hooks import HookContext


def create_step_context(
    workflow_id: str,
    workflow_name: str,
    total_steps: int,
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
        workflow_id: Parent workflow ID
        workflow_name: Parent workflow name
        total_steps: Total steps in workflow
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
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        step_id=step_id,
        step_index=step_index,
        total_steps=total_steps,
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
