# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

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
