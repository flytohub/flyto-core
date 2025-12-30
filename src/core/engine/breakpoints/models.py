"""
Breakpoint Models

Enums and data classes for the breakpoint system.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


class BreakpointStatus(str, Enum):
    """Status of a breakpoint"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class ApprovalMode(str, Enum):
    """Approval mode for breakpoints"""
    SINGLE = "single"       # Any single approver
    ALL = "all"             # All approvers must approve
    MAJORITY = "majority"   # Majority must approve
    FIRST = "first"         # First response wins


@dataclass
class BreakpointRequest:
    """
    A pending breakpoint request.

    Attributes:
        breakpoint_id: Unique identifier
        execution_id: Parent execution ID
        step_id: Step that triggered the breakpoint
        workflow_id: Workflow ID
        title: Human-readable title
        description: Detailed description
        required_approvers: List of user IDs who can approve
        approval_mode: How approvals are counted
        timeout_seconds: Timeout in seconds (None for no timeout)
        created_at: When breakpoint was created
        expires_at: When breakpoint expires
        context_snapshot: Context at breakpoint time
        custom_fields: Custom input fields to collect
        metadata: Additional metadata
    """
    breakpoint_id: str
    execution_id: str
    step_id: str
    workflow_id: Optional[str] = None
    title: str = "Approval Required"
    description: str = ""
    required_approvers: List[str] = field(default_factory=list)
    approval_mode: ApprovalMode = ApprovalMode.SINGLE
    timeout_seconds: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    context_snapshot: Dict[str, Any] = field(default_factory=dict)
    custom_fields: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.timeout_seconds and not self.expires_at:
            self.expires_at = self.created_at + timedelta(seconds=self.timeout_seconds)

    @property
    def is_expired(self) -> bool:
        """Check if breakpoint has expired"""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "breakpoint_id": self.breakpoint_id,
            "execution_id": self.execution_id,
            "step_id": self.step_id,
            "workflow_id": self.workflow_id,
            "title": self.title,
            "description": self.description,
            "required_approvers": self.required_approvers,
            "approval_mode": self.approval_mode.value,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expired": self.is_expired,
            "context_snapshot": self.context_snapshot,
            "custom_fields": self.custom_fields,
            "metadata": self.metadata,
        }


@dataclass
class ApprovalResponse:
    """
    Response to a breakpoint request.

    Attributes:
        breakpoint_id: ID of the breakpoint
        approved: Whether approved or rejected
        user_id: User who responded
        comment: Optional comment
        custom_inputs: Values for custom fields
        responded_at: Response timestamp
    """
    breakpoint_id: str
    approved: bool
    user_id: str
    comment: Optional[str] = None
    custom_inputs: Dict[str, Any] = field(default_factory=dict)
    responded_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "breakpoint_id": self.breakpoint_id,
            "approved": self.approved,
            "user_id": self.user_id,
            "comment": self.comment,
            "custom_inputs": self.custom_inputs,
            "responded_at": self.responded_at.isoformat(),
        }


@dataclass
class BreakpointResult:
    """
    Result of a breakpoint resolution.

    Attributes:
        breakpoint_id: ID of the breakpoint
        status: Final status
        responses: All approval responses
        resolved_at: When resolved
        final_inputs: Merged custom inputs
    """
    breakpoint_id: str
    status: BreakpointStatus
    responses: List[ApprovalResponse] = field(default_factory=list)
    resolved_at: datetime = field(default_factory=datetime.utcnow)
    final_inputs: Dict[str, Any] = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        """Check if breakpoint was approved"""
        return self.status == BreakpointStatus.APPROVED

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "breakpoint_id": self.breakpoint_id,
            "status": self.status.value,
            "approved": self.approved,
            "responses": [r.to_dict() for r in self.responses],
            "resolved_at": self.resolved_at.isoformat(),
            "final_inputs": self.final_inputs,
        }
