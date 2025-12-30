"""
Evidence Models

Data classes and protocols for the evidence system.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Literal, Optional, Protocol


@dataclass
class StepEvidence:
    """
    Evidence record for a single step execution.

    Captures complete execution state for debugging, replay, and audit.
    """
    # Identification
    step_id: str
    execution_id: str
    timestamp: datetime
    duration_ms: int

    # Context snapshots
    context_before: Dict[str, Any]
    context_after: Dict[str, Any]

    # UI evidence (browser modules only)
    screenshot_path: Optional[str] = None
    dom_snapshot_path: Optional[str] = None

    # Execution result
    status: Literal['success', 'error', 'skipped'] = 'success'
    error_message: Optional[str] = None
    output: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    module_id: Optional[str] = None
    step_index: Optional[int] = None
    attempt: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        # Convert datetime to ISO format
        if isinstance(data.get('timestamp'), datetime):
            data['timestamp'] = data['timestamp'].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepEvidence":
        """Create from dictionary"""
        # Convert ISO string back to datetime
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class BrowserContextProtocol(Protocol):
    """Protocol for browser context that provides page access"""

    def get_current_page(self) -> Any:
        """Get current browser page for screenshot/DOM capture"""
        ...
