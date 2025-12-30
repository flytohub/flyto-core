"""
Hook Models

Enums and data classes for the hooks system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class HookAction(Enum):
    """Actions a hook can request"""
    CONTINUE = "continue"      # Proceed normally
    SKIP = "skip"              # Skip current step
    RETRY = "retry"            # Retry current step
    ABORT = "abort"            # Abort execution
    SUBSTITUTE = "substitute"  # Use substitute result


@dataclass
class HookContext:
    """
    Context passed to hook methods.

    Contains all information about the current execution state
    without exposing internal engine details.
    """
    # Workflow identification
    workflow_id: str
    workflow_name: str = ""

    # Current step info (if applicable)
    step_id: Optional[str] = None
    step_index: Optional[int] = None
    total_steps: Optional[int] = None
    module_id: Optional[str] = None

    # Execution state
    params: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)

    # Timing
    started_at: Optional[datetime] = None
    elapsed_ms: float = 0

    # Error info (for error hooks)
    error: Optional[Exception] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    # Result info (for post-execute hooks)
    result: Optional[Any] = None

    # Retry info
    attempt: int = 1
    max_attempts: int = 3

    # Custom metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "step_id": self.step_id,
            "step_index": self.step_index,
            "total_steps": self.total_steps,
            "module_id": self.module_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "elapsed_ms": self.elapsed_ms,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "attempt": self.attempt,
            "metadata": self.metadata,
        }


@dataclass
class HookResult:
    """
    Result returned by hook methods.

    Allows hooks to influence execution flow without
    direct access to engine internals.
    """
    action: HookAction = HookAction.CONTINUE

    # For SUBSTITUTE action
    substitute_result: Optional[Any] = None

    # For RETRY action
    retry_delay_ms: float = 1000

    # For ABORT action
    abort_reason: Optional[str] = None

    # Additional data to pass along
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def continue_execution(cls) -> "HookResult":
        """Helper to create continue result"""
        return cls(action=HookAction.CONTINUE)

    @classmethod
    def skip_step(cls) -> "HookResult":
        """Helper to create skip result"""
        return cls(action=HookAction.SKIP)

    @classmethod
    def retry_step(cls, delay_ms: float = 1000) -> "HookResult":
        """Helper to create retry result"""
        return cls(action=HookAction.RETRY, retry_delay_ms=delay_ms)

    @classmethod
    def abort_execution(cls, reason: str) -> "HookResult":
        """Helper to create abort result"""
        return cls(action=HookAction.ABORT, abort_reason=reason)

    @classmethod
    def substitute(cls, result: Any) -> "HookResult":
        """Helper to create substitute result"""
        return cls(action=HookAction.SUBSTITUTE, substitute_result=result)
