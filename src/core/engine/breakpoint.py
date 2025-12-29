"""
Human-in-the-loop Breakpoint System

Provides execution pause and approval mechanisms:
- Pending approval management
- Approval/rejection handling
- Timeout support
- Multi-user approval workflows
- Custom input collection

This is a capability n8n lacks - structured human intervention points.

Design principles:
- Non-blocking: Execution state is persisted
- Resumable: Workflow can continue after approval
- Observable: All pending breakpoints are queryable
- Secure: Approval requires proper authorization
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol
from uuid import uuid4

logger = logging.getLogger(__name__)


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


class BreakpointNotifier(Protocol):
    """Protocol for breakpoint notifications"""

    async def notify_pending(self, request: BreakpointRequest) -> None:
        """Notify users of pending breakpoint"""
        ...

    async def notify_resolved(self, result: BreakpointResult) -> None:
        """Notify users of resolved breakpoint"""
        ...


class NullNotifier:
    """No-op notifier implementation"""

    async def notify_pending(self, request: BreakpointRequest) -> None:
        logger.debug(f"Breakpoint pending: {request.breakpoint_id}")

    async def notify_resolved(self, result: BreakpointResult) -> None:
        logger.debug(f"Breakpoint resolved: {result.breakpoint_id} -> {result.status}")


class BreakpointStore(Protocol):
    """Protocol for breakpoint persistence"""

    async def save(self, request: BreakpointRequest) -> None:
        """Save breakpoint request"""
        ...

    async def load(self, breakpoint_id: str) -> Optional[BreakpointRequest]:
        """Load breakpoint request"""
        ...

    async def list_pending(
        self,
        execution_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[BreakpointRequest]:
        """List pending breakpoints"""
        ...

    async def update_status(
        self,
        breakpoint_id: str,
        status: BreakpointStatus,
    ) -> None:
        """Update breakpoint status"""
        ...

    async def save_response(self, response: ApprovalResponse) -> None:
        """Save approval response"""
        ...

    async def get_responses(self, breakpoint_id: str) -> List[ApprovalResponse]:
        """Get all responses for a breakpoint"""
        ...

    async def delete(self, breakpoint_id: str) -> None:
        """Delete breakpoint and responses"""
        ...


class InMemoryBreakpointStore:
    """In-memory breakpoint store for development/testing"""

    def __init__(self):
        self._requests: Dict[str, BreakpointRequest] = {}
        self._responses: Dict[str, List[ApprovalResponse]] = {}
        self._statuses: Dict[str, BreakpointStatus] = {}

    async def save(self, request: BreakpointRequest) -> None:
        self._requests[request.breakpoint_id] = request
        self._statuses[request.breakpoint_id] = BreakpointStatus.PENDING
        self._responses[request.breakpoint_id] = []

    async def load(self, breakpoint_id: str) -> Optional[BreakpointRequest]:
        return self._requests.get(breakpoint_id)

    async def list_pending(
        self,
        execution_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[BreakpointRequest]:
        pending = []
        for bp_id, request in self._requests.items():
            if self._statuses.get(bp_id) != BreakpointStatus.PENDING:
                continue
            if execution_id and request.execution_id != execution_id:
                continue
            if user_id and user_id not in request.required_approvers:
                if request.required_approvers:  # Empty means anyone can approve
                    continue
            pending.append(request)
        return pending

    async def update_status(
        self,
        breakpoint_id: str,
        status: BreakpointStatus,
    ) -> None:
        self._statuses[breakpoint_id] = status

    async def save_response(self, response: ApprovalResponse) -> None:
        if response.breakpoint_id not in self._responses:
            self._responses[response.breakpoint_id] = []
        self._responses[response.breakpoint_id].append(response)

    async def get_responses(self, breakpoint_id: str) -> List[ApprovalResponse]:
        return self._responses.get(breakpoint_id, [])

    async def delete(self, breakpoint_id: str) -> None:
        self._requests.pop(breakpoint_id, None)
        self._responses.pop(breakpoint_id, None)
        self._statuses.pop(breakpoint_id, None)


class BreakpointManager:
    """
    Manages breakpoint lifecycle.

    Usage:
        manager = BreakpointManager(store, notifier)

        # Create breakpoint
        request = await manager.create_breakpoint(
            execution_id="exec_123",
            step_id="step_1",
            title="Approve data deletion",
            timeout_seconds=3600,
        )

        # Wait for approval (blocks until resolved or timeout)
        result = await manager.wait_for_resolution(request.breakpoint_id)

        if result.approved:
            # Continue execution
            pass
        else:
            # Handle rejection
            pass
    """

    def __init__(
        self,
        store: Optional[BreakpointStore] = None,
        notifier: Optional[BreakpointNotifier] = None,
        poll_interval: float = 0.5,
    ):
        self.store = store or InMemoryBreakpointStore()
        self.notifier = notifier or NullNotifier()
        self.poll_interval = poll_interval
        self._resolution_events: Dict[str, asyncio.Event] = {}
        self._results: Dict[str, BreakpointResult] = {}

    async def create_breakpoint(
        self,
        execution_id: str,
        step_id: str,
        title: str = "Approval Required",
        description: str = "",
        workflow_id: Optional[str] = None,
        required_approvers: Optional[List[str]] = None,
        approval_mode: ApprovalMode = ApprovalMode.SINGLE,
        timeout_seconds: Optional[int] = None,
        context_snapshot: Optional[Dict[str, Any]] = None,
        custom_fields: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BreakpointRequest:
        """
        Create a new breakpoint request.

        Args:
            execution_id: Parent execution ID
            step_id: Step that triggered breakpoint
            title: Human-readable title
            description: Detailed description
            workflow_id: Optional workflow ID
            required_approvers: Users who can approve
            approval_mode: How to count approvals
            timeout_seconds: Timeout (None for no timeout)
            context_snapshot: Context at breakpoint time
            custom_fields: Custom input fields
            metadata: Additional metadata

        Returns:
            Created breakpoint request
        """
        breakpoint_id = f"bp_{uuid4().hex[:12]}"

        request = BreakpointRequest(
            breakpoint_id=breakpoint_id,
            execution_id=execution_id,
            step_id=step_id,
            workflow_id=workflow_id,
            title=title,
            description=description,
            required_approvers=required_approvers or [],
            approval_mode=approval_mode,
            timeout_seconds=timeout_seconds,
            context_snapshot=context_snapshot or {},
            custom_fields=custom_fields or [],
            metadata=metadata or {},
        )

        await self.store.save(request)
        self._resolution_events[breakpoint_id] = asyncio.Event()

        await self.notifier.notify_pending(request)

        logger.info(f"Created breakpoint {breakpoint_id} for {execution_id}/{step_id}")

        return request

    async def respond(
        self,
        breakpoint_id: str,
        approved: bool,
        user_id: str,
        comment: Optional[str] = None,
        custom_inputs: Optional[Dict[str, Any]] = None,
    ) -> BreakpointResult:
        """
        Respond to a breakpoint request.

        Args:
            breakpoint_id: ID of the breakpoint
            approved: Whether to approve or reject
            user_id: User responding
            comment: Optional comment
            custom_inputs: Values for custom fields

        Returns:
            Breakpoint result if resolved, None if waiting for more responses
        """
        request = await self.store.load(breakpoint_id)
        if not request:
            raise ValueError(f"Breakpoint not found: {breakpoint_id}")

        if request.is_expired:
            return await self._resolve(
                breakpoint_id,
                BreakpointStatus.TIMEOUT,
            )

        # Validate approver
        if request.required_approvers and user_id not in request.required_approvers:
            raise ValueError(f"User {user_id} is not authorized to approve")

        response = ApprovalResponse(
            breakpoint_id=breakpoint_id,
            approved=approved,
            user_id=user_id,
            comment=comment,
            custom_inputs=custom_inputs or {},
        )

        await self.store.save_response(response)

        # Check if resolution criteria met
        return await self._check_resolution(request, response)

    async def _check_resolution(
        self,
        request: BreakpointRequest,
        latest_response: ApprovalResponse,
    ) -> Optional[BreakpointResult]:
        """Check if breakpoint should be resolved"""
        all_responses = await self.store.get_responses(request.breakpoint_id)

        if request.approval_mode == ApprovalMode.SINGLE:
            # Any single response resolves
            status = (
                BreakpointStatus.APPROVED
                if latest_response.approved
                else BreakpointStatus.REJECTED
            )
            return await self._resolve(
                request.breakpoint_id,
                status,
                all_responses,
                latest_response.custom_inputs,
            )

        elif request.approval_mode == ApprovalMode.FIRST:
            # First response wins (same as SINGLE)
            status = (
                BreakpointStatus.APPROVED
                if latest_response.approved
                else BreakpointStatus.REJECTED
            )
            return await self._resolve(
                request.breakpoint_id,
                status,
                all_responses,
                latest_response.custom_inputs,
            )

        elif request.approval_mode == ApprovalMode.ALL:
            # All required approvers must respond with approval
            if not request.required_approvers:
                # No specific approvers required, single approval works
                if latest_response.approved:
                    return await self._resolve(
                        request.breakpoint_id,
                        BreakpointStatus.APPROVED,
                        all_responses,
                        latest_response.custom_inputs,
                    )
                else:
                    return await self._resolve(
                        request.breakpoint_id,
                        BreakpointStatus.REJECTED,
                        all_responses,
                        latest_response.custom_inputs,
                    )

            # Any rejection means rejected
            if not latest_response.approved:
                return await self._resolve(
                    request.breakpoint_id,
                    BreakpointStatus.REJECTED,
                    all_responses,
                    {},
                )

            # Check if all approved
            approved_users = {r.user_id for r in all_responses if r.approved}
            required_set = set(request.required_approvers)

            if approved_users >= required_set:
                # Merge all custom inputs
                merged_inputs = {}
                for r in all_responses:
                    if r.approved:
                        merged_inputs.update(r.custom_inputs)
                return await self._resolve(
                    request.breakpoint_id,
                    BreakpointStatus.APPROVED,
                    all_responses,
                    merged_inputs,
                )

        elif request.approval_mode == ApprovalMode.MAJORITY:
            # Majority of approvers must approve
            approval_count = sum(1 for r in all_responses if r.approved)
            rejection_count = sum(1 for r in all_responses if not r.approved)

            total_approvers = len(request.required_approvers) or 1
            majority = (total_approvers // 2) + 1

            if approval_count >= majority:
                merged_inputs = {}
                for r in all_responses:
                    if r.approved:
                        merged_inputs.update(r.custom_inputs)
                return await self._resolve(
                    request.breakpoint_id,
                    BreakpointStatus.APPROVED,
                    all_responses,
                    merged_inputs,
                )
            elif rejection_count >= majority:
                return await self._resolve(
                    request.breakpoint_id,
                    BreakpointStatus.REJECTED,
                    all_responses,
                    {},
                )

        # Not yet resolved
        return None

    async def _resolve(
        self,
        breakpoint_id: str,
        status: BreakpointStatus,
        responses: Optional[List[ApprovalResponse]] = None,
        final_inputs: Optional[Dict[str, Any]] = None,
    ) -> BreakpointResult:
        """Resolve a breakpoint"""
        if responses is None:
            responses = await self.store.get_responses(breakpoint_id)

        result = BreakpointResult(
            breakpoint_id=breakpoint_id,
            status=status,
            responses=responses,
            final_inputs=final_inputs or {},
        )

        await self.store.update_status(breakpoint_id, status)
        self._results[breakpoint_id] = result

        # Signal resolution
        event = self._resolution_events.get(breakpoint_id)
        if event:
            event.set()

        await self.notifier.notify_resolved(result)

        logger.info(f"Resolved breakpoint {breakpoint_id} with status {status}")

        return result

    async def wait_for_resolution(
        self,
        breakpoint_id: str,
        check_timeout: bool = True,
    ) -> BreakpointResult:
        """
        Wait for breakpoint resolution.

        Args:
            breakpoint_id: ID of the breakpoint
            check_timeout: Whether to check for timeout

        Returns:
            Breakpoint result
        """
        request = await self.store.load(breakpoint_id)
        if not request:
            raise ValueError(f"Breakpoint not found: {breakpoint_id}")

        event = self._resolution_events.get(breakpoint_id)
        if not event:
            event = asyncio.Event()
            self._resolution_events[breakpoint_id] = event

        # Check if already resolved
        if breakpoint_id in self._results:
            return self._results[breakpoint_id]

        # Wait with timeout checking
        while True:
            if check_timeout and request.is_expired:
                return await self._resolve(breakpoint_id, BreakpointStatus.TIMEOUT)

            try:
                # Calculate remaining time
                if request.expires_at:
                    remaining = (request.expires_at - datetime.utcnow()).total_seconds()
                    timeout = min(remaining, self.poll_interval)
                    if timeout <= 0:
                        return await self._resolve(breakpoint_id, BreakpointStatus.TIMEOUT)
                else:
                    timeout = self.poll_interval

                await asyncio.wait_for(event.wait(), timeout=timeout)

                # Check if resolved
                if breakpoint_id in self._results:
                    return self._results[breakpoint_id]

            except asyncio.TimeoutError:
                # Poll interval expired, check again
                if breakpoint_id in self._results:
                    return self._results[breakpoint_id]
                continue

    async def cancel(self, breakpoint_id: str) -> BreakpointResult:
        """
        Cancel a pending breakpoint.

        Args:
            breakpoint_id: ID of the breakpoint

        Returns:
            Cancelled breakpoint result
        """
        return await self._resolve(breakpoint_id, BreakpointStatus.CANCELLED)

    async def list_pending(
        self,
        execution_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[BreakpointRequest]:
        """
        List pending breakpoints.

        Args:
            execution_id: Filter by execution
            user_id: Filter by approver

        Returns:
            List of pending breakpoint requests
        """
        pending = await self.store.list_pending(execution_id, user_id)

        # Filter expired
        active = []
        for request in pending:
            if request.is_expired:
                await self._resolve(request.breakpoint_id, BreakpointStatus.TIMEOUT)
            else:
                active.append(request)

        return active

    async def get_status(self, breakpoint_id: str) -> Optional[BreakpointStatus]:
        """Get current status of a breakpoint"""
        if breakpoint_id in self._results:
            return self._results[breakpoint_id].status

        request = await self.store.load(breakpoint_id)
        if not request:
            return None

        if request.is_expired:
            result = await self._resolve(breakpoint_id, BreakpointStatus.TIMEOUT)
            return result.status

        return BreakpointStatus.PENDING


# =============================================================================
# Factory Functions
# =============================================================================

_breakpoint_manager: Optional[BreakpointManager] = None


def get_breakpoint_manager() -> BreakpointManager:
    """Get global breakpoint manager instance"""
    global _breakpoint_manager
    if _breakpoint_manager is None:
        _breakpoint_manager = BreakpointManager()
    return _breakpoint_manager


def create_breakpoint_manager(
    store: Optional[BreakpointStore] = None,
    notifier: Optional[BreakpointNotifier] = None,
    poll_interval: float = 0.5,
) -> BreakpointManager:
    """
    Create a new breakpoint manager.

    Args:
        store: Storage implementation
        notifier: Notification implementation
        poll_interval: Poll interval in seconds

    Returns:
        Configured BreakpointManager
    """
    return BreakpointManager(
        store=store,
        notifier=notifier,
        poll_interval=poll_interval,
    )


def set_global_breakpoint_manager(manager: BreakpointManager) -> None:
    """Set the global breakpoint manager instance"""
    global _breakpoint_manager
    _breakpoint_manager = manager
