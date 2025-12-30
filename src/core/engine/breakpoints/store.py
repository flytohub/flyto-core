"""
Breakpoint Store

Storage protocols and implementations for breakpoint persistence.
"""

import logging
from typing import Dict, List, Optional, Protocol

from .models import (
    ApprovalResponse,
    BreakpointRequest,
    BreakpointStatus,
)

logger = logging.getLogger(__name__)


class BreakpointNotifier(Protocol):
    """Protocol for breakpoint notifications"""

    async def notify_pending(self, request: BreakpointRequest) -> None:
        """Notify users of pending breakpoint"""
        ...

    async def notify_resolved(self, result: "BreakpointResult") -> None:
        """Notify users of resolved breakpoint"""
        ...


class NullNotifier:
    """No-op notifier implementation"""

    async def notify_pending(self, request: BreakpointRequest) -> None:
        logger.debug(f"Breakpoint pending: {request.breakpoint_id}")

    async def notify_resolved(self, result: "BreakpointResult") -> None:
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
                if request.required_approvers:
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


# Import for type hint
from .models import BreakpointResult  # noqa: E402
