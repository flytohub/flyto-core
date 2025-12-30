"""
Executor Hooks Interface

DEPRECATED: This file is maintained for backwards compatibility.
Please import from core.engine.hooks instead:

    from core.engine.hooks import ExecutorHooks

All functionality has been split into:
- core/engine/hooks/models.py - HookAction, HookContext, HookResult
- core/engine/hooks/base.py - ExecutorHooks ABC, NullHooks
- core/engine/hooks/implementations.py - LoggingHooks, MetricsHooks, CompositeHooks

Original design principles:
- Zero coupling: hooks are optional, engine works without them
- Protocol-based: any object implementing the protocol works
- Composable: multiple hooks can be combined
- Fail-safe: hook errors don't break execution
"""

# Re-export for backwards compatibility
from .hooks import (
    # Models
    HookAction,
    HookContext,
    HookResult,
    # Base
    ExecutorHooks,
    NullHooks,
    # Implementations
    CompositeHooks,
    LoggingHooks,
    MetricsHooks,
    # Factory
    create_hooks,
)

__all__ = [
    # Models
    "HookAction",
    "HookContext",
    "HookResult",
    # Base
    "ExecutorHooks",
    "NullHooks",
    # Implementations
    "CompositeHooks",
    "LoggingHooks",
    "MetricsHooks",
    # Factory
    "create_hooks",
]
