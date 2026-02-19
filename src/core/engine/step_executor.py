# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Step Executor - Single step execution with retry, timeout, and foreach support

DEPRECATED: This file is maintained for backwards compatibility.
Please import from core.engine.step_executor instead:

    from core.engine.step_executor import (
        StepExecutor,
        create_step_executor,
    )

All functionality has been split into:
- core/engine/step_executor/context_builder.py - Hook context creation
- core/engine/step_executor/retry.py - Retry logic
- core/engine/step_executor/foreach.py - Foreach execution
- core/engine/step_executor/executor.py - Main StepExecutor class
"""

# Re-export for backwards compatibility
from .step_executor import (
    StepExecutor,
    create_step_executor,
    create_step_context,
    execute_with_retry,
    execute_foreach_step,
)

__all__ = [
    "StepExecutor",
    "create_step_executor",
    "create_step_context",
    "execute_with_retry",
    "execute_foreach_step",
]
