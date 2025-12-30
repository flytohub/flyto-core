"""
Workflow Replay System

DEPRECATED: This file is maintained for backwards compatibility.
Please import from core.engine.replay instead:

    from core.engine.replay import ReplayManager

All functionality has been split into:
- core/engine/replay/models.py - ReplayMode, ReplayConfig, ReplayResult
- core/engine/replay/manager.py - ReplayManager class

Original design principles:
- Non-destructive: Original evidence preserved
- Flexible: Replay from any step with any context modification
- Traceable: Replay executions are linked to originals
"""

# Re-export for backwards compatibility
from .replay import (
    # Models
    ReplayConfig,
    ReplayMode,
    ReplayResult,
    # Manager
    ReplayManager,
    # Factory functions
    create_replay_manager,
)

__all__ = [
    # Models
    "ReplayConfig",
    "ReplayMode",
    "ReplayResult",
    # Manager
    "ReplayManager",
    # Factory functions
    "create_replay_manager",
]
