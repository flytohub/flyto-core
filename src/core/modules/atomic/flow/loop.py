"""
Loop / ForEach - Iteration Module

DEPRECATED: This file is maintained for backwards compatibility.
Please import from core.modules.atomic.flow.loop instead:

    from core.modules.atomic.flow.loop import (
        LoopModule,
        resolve_params,
    )

All functionality has been split into:
- core/modules/atomic/flow/loop/resolver.py - Parameter resolution
- core/modules/atomic/flow/loop/edge_mode.py - Edge-based loop execution
- core/modules/atomic/flow/loop/nested_mode.py - Nested loop execution
- core/modules/atomic/flow/loop/module.py - Main LoopModule class
"""

# Re-export for backwards compatibility
from .loop import (
    LoopModule,
    LOOP_CONFIG,
    FOREACH_CONFIG,
    execute_edge_mode,
    execute_nested_mode,
    resolve_params,
    resolve_variable,
    ITERATION_PREFIX,
)

__all__ = [
    "LoopModule",
    "LOOP_CONFIG",
    "FOREACH_CONFIG",
    "execute_edge_mode",
    "execute_nested_mode",
    "resolve_params",
    "resolve_variable",
    "ITERATION_PREFIX",
]
