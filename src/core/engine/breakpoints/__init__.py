# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

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
    create_cloud_worker_manager,
    auto_configure_breakpoint_manager,
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
    # Store — base
    "BreakpointNotifier",
    "BreakpointStore",
    "InMemoryBreakpointStore",
    "NullNotifier",
    # Store — cloud (lazy imports, optional deps)
    "RedisBreakpointStore",
    "HttpBreakpointStore",
    # Manager
    "BreakpointManager",
    "create_breakpoint_manager",
    "create_cloud_worker_manager",
    "auto_configure_breakpoint_manager",
    "get_breakpoint_manager",
    "set_global_breakpoint_manager",
]


def __getattr__(name):
    """Lazy import cloud stores to avoid hard dependency on redis/httpx."""
    if name == "RedisBreakpointStore":
        from .store_redis import RedisBreakpointStore
        return RedisBreakpointStore
    if name == "HttpBreakpointStore":
        from .store_http import HttpBreakpointStore
        return HttpBreakpointStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
