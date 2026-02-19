# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Breakpoints Module

Human-in-the-loop approval system for workflow breakpoints.
"""

from .models import (
    ApprovalMode,
    ApprovalResponse,
    BreakpointRequest,
    BreakpointResult,
    BreakpointStatus,
)
from .store import (
    BreakpointNotifier,
    BreakpointStore,
    InMemoryBreakpointStore,
    NullNotifier,
)
from .manager import (
    BreakpointManager,
    create_breakpoint_manager,
    get_breakpoint_manager,
    set_global_breakpoint_manager,
)

__all__ = [
    # Models
    "ApprovalMode",
    "ApprovalResponse",
    "BreakpointRequest",
    "BreakpointResult",
    "BreakpointStatus",
    # Store
    "BreakpointNotifier",
    "BreakpointStore",
    "InMemoryBreakpointStore",
    "NullNotifier",
    # Manager
    "BreakpointManager",
    "create_breakpoint_manager",
    "get_breakpoint_manager",
    "set_global_breakpoint_manager",
]
