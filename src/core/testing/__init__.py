"""
Workflow Testing Framework

Provides structured workflow testing with:
- YAML/JSON test case definitions
- Expected outcome validation
- Snapshot testing
- Regression detection

This is a capability n8n lacks - workflow-level testing framework.
"""
from .runner import (
    TestCase,
    TestResult,
    TestReport,
    WorkflowTestRunner,
    create_test_runner,
)
from .assertions import (
    Assertion,
    AssertionResult,
    assert_equals,
    assert_contains,
    assert_status,
    assert_step_completed,
    assert_step_skipped,
    assert_output_matches,
)
from .snapshot import (
    SnapshotManager,
    SnapshotResult,
    create_snapshot_manager,
)

__all__ = [
    # Runner
    'TestCase',
    'TestResult',
    'TestReport',
    'WorkflowTestRunner',
    'create_test_runner',
    # Assertions
    'Assertion',
    'AssertionResult',
    'assert_equals',
    'assert_contains',
    'assert_status',
    'assert_step_completed',
    'assert_step_skipped',
    'assert_output_matches',
    # Snapshots
    'SnapshotManager',
    'SnapshotResult',
    'create_snapshot_manager',
]
