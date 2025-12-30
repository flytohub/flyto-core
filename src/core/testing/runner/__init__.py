"""
Workflow Test Runner Module

Executes test cases against workflows and validates outcomes.
"""

from typing import Callable, Optional

from .models import (
    TestCase,
    TestReport,
    TestResult,
    TestStatus,
)
from .executor import WorkflowTestRunner


def create_test_runner(
    workflow_executor: Optional[Callable] = None,
    parallel: bool = False,
) -> WorkflowTestRunner:
    """
    Create a test runner.

    Args:
        workflow_executor: Optional custom executor
        parallel: Whether to run tests in parallel

    Returns:
        Configured WorkflowTestRunner
    """
    return WorkflowTestRunner(
        workflow_executor=workflow_executor,
        parallel=parallel,
    )


__all__ = [
    # Models
    "TestCase",
    "TestReport",
    "TestResult",
    "TestStatus",
    # Executor
    "WorkflowTestRunner",
    # Factory
    "create_test_runner",
]
