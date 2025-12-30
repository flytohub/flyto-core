"""
Workflow Test Runner

DEPRECATED: This file is maintained for backwards compatibility.
Please import from core.testing.runner instead:

    from core.testing.runner import WorkflowTestRunner

All functionality has been split into:
- core/testing/runner/models.py - TestStatus, TestCase, TestResult, TestReport
- core/testing/runner/executor.py - WorkflowTestRunner class

Original design principles:
- Declarative: Tests defined in YAML/JSON
- Isolated: Each test runs in clean environment
- Detailed: Comprehensive failure reporting
"""

# Re-export for backwards compatibility
from .runner import (
    # Models
    TestCase,
    TestReport,
    TestResult,
    TestStatus,
    # Executor
    WorkflowTestRunner,
    # Factory
    create_test_runner,
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
