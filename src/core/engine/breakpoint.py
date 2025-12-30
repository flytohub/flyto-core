"""
Human-in-the-loop Breakpoint System

DEPRECATED: This file is maintained for backwards compatibility.
Please import from core.engine.breakpoints instead:

    from core.engine.breakpoints import BreakpointManager

All functionality has been split into:
- core/engine/breakpoints/models.py - Enums and data classes
- core/engine/breakpoints/store.py - Storage protocols and implementations
- core/engine/breakpoints/manager.py - BreakpointManager class

Original design principles:
- Non-blocking: Execution state is persisted
- Resumable: Workflow can continue after approval
- Observable: All pending breakpoints are queryable
- Secure: Approval requires proper authorization
"""

# Re-export for backwards compatibility
from .breakpoints import (
    # Enums
    ApprovalMode,
    BreakpointStatus,
    # Data classes
    ApprovalResponse,
    BreakpointRequest,
    BreakpointResult,
    # Protocols and implementations
    BreakpointNotifier,
    BreakpointStore,
    InMemoryBreakpointStore,
    NullNotifier,
    # Manager
    BreakpointManager,
    # Factory functions
    create_breakpoint_manager,
    get_breakpoint_manager,
    set_global_breakpoint_manager,
)

__all__ = [
    # Enums
    "ApprovalMode",
    "BreakpointStatus",
    # Data classes
    "ApprovalResponse",
    "BreakpointRequest",
    "BreakpointResult",
    # Protocols and implementations
    "BreakpointNotifier",
    "BreakpointStore",
    "InMemoryBreakpointStore",
    "NullNotifier",
    # Manager
    "BreakpointManager",
    # Factory functions
    "create_breakpoint_manager",
    "get_breakpoint_manager",
    "set_global_breakpoint_manager",
]
