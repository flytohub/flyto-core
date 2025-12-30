"""
Replay Models

Enums and data classes for the replay system.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Set


class ReplayMode(str, Enum):
    """Replay execution modes"""
    FROM_STEP = "from_step"          # Continue from step to end
    SINGLE_STEP = "single_step"      # Execute only the specified step
    RANGE = "range"                  # Execute step range
    MODIFIED = "modified"            # Re-run only modified steps


@dataclass
class ReplayConfig:
    """
    Configuration for replay execution.

    Attributes:
        mode: Replay mode
        start_step_id: Step to start from
        end_step_id: Optional step to end at
        modified_context: Context modifications to apply
        skip_steps: Steps to skip during replay
        breakpoints: Steps to pause at
        dry_run: If True, validate only without executing
    """
    mode: ReplayMode = ReplayMode.FROM_STEP
    start_step_id: str = ""
    end_step_id: Optional[str] = None
    modified_context: Dict[str, Any] = field(default_factory=dict)
    skip_steps: Set[str] = field(default_factory=set)
    breakpoints: Set[str] = field(default_factory=set)
    dry_run: bool = False


@dataclass
class ReplayResult:
    """
    Result of a replay execution.

    Attributes:
        ok: Whether replay completed successfully
        execution_id: New execution ID for this replay
        original_execution_id: Original execution being replayed
        start_step: Step replay started from
        end_step: Step replay ended at
        steps_executed: Number of steps executed
        steps_skipped: Number of steps skipped
        context: Final context after replay
        error: Error message if failed
        duration_ms: Total replay duration
    """
    ok: bool
    execution_id: str
    original_execution_id: str
    start_step: str
    end_step: Optional[str] = None
    steps_executed: int = 0
    steps_skipped: int = 0
    context: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "ok": self.ok,
            "execution_id": self.execution_id,
            "original_execution_id": self.original_execution_id,
            "start_step": self.start_step,
            "end_step": self.end_step,
            "steps_executed": self.steps_executed,
            "steps_skipped": self.steps_skipped,
            "context": self.context,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }
