"""
Step Executor Package

Single step execution with retry, timeout, and foreach support.
"""

from typing import Optional

from ..hooks import ExecutorHooks
from .executor import StepExecutor
from .context_builder import create_step_context
from .retry import execute_with_retry
from .foreach import execute_foreach_step


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


__all__ = [
    "StepExecutor",
    "create_step_executor",
    "create_step_context",
    "execute_with_retry",
    "execute_foreach_step",
]
