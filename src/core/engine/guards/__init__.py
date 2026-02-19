# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Execution Guards

Safety guards for workflow execution — timeouts, resource limits, etc.
"""

from .timeout import (
    DEFAULT_STEP_TIMEOUT_MS,
    DEFAULT_WORKFLOW_TIMEOUT_MS,
    ExecutionTimeoutError,
    TimeoutCallback,
    TimeoutGuard,
    TimeoutHooks,
)

__all__ = [
    "DEFAULT_STEP_TIMEOUT_MS",
    "DEFAULT_WORKFLOW_TIMEOUT_MS",
    "ExecutionTimeoutError",
    "TimeoutCallback",
    "TimeoutGuard",
    "TimeoutHooks",
]
