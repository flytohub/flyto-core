"""
Breakpoint Manager

Manages breakpoint lifecycle including creation, approval, and resolution.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .models import (
    ApprovalMode,
    ApprovalResponse,
    BreakpointRequest,
    BreakpointResult,
    BreakpointStatus,
)
from .store import (
    BreakpointNotifier,
    BreakpointStore,
    InMemoryBreakpointStore,
    NullNotifier,
)

logger = logging.getLogger(__name__)


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
        """Create a new breakpoint request."""
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
        """Respond to a breakpoint request."""
        request = await self.store.load(breakpoint_id)
        if not request:
            raise ValueError(f"Breakpoint not found: {breakpoint_id}")

        if request.is_expired:
            return await self._resolve(breakpoint_id, BreakpointStatus.TIMEOUT)

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

        return await self._check_resolution(request, response)

    async def _check_resolution(
        self,
        request: BreakpointRequest,
        latest_response: ApprovalResponse,
    ) -> Optional[BreakpointResult]:
        """Check if breakpoint should be resolved"""
        all_responses = await self.store.get_responses(request.breakpoint_id)

        if request.approval_mode == ApprovalMode.SINGLE:
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
            if not request.required_approvers:
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

            if not latest_response.approved:
                return await self._resolve(
                    request.breakpoint_id,
                    BreakpointStatus.REJECTED,
                    all_responses,
                    {},
                )

            approved_users = {r.user_id for r in all_responses if r.approved}
            required_set = set(request.required_approvers)

            if approved_users >= required_set:
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
        """Wait for breakpoint resolution."""
        request = await self.store.load(breakpoint_id)
        if not request:
            raise ValueError(f"Breakpoint not found: {breakpoint_id}")

        event = self._resolution_events.get(breakpoint_id)
        if not event:
            event = asyncio.Event()
            self._resolution_events[breakpoint_id] = event

        if breakpoint_id in self._results:
            return self._results[breakpoint_id]

        while True:
            if check_timeout and request.is_expired:
                return await self._resolve(breakpoint_id, BreakpointStatus.TIMEOUT)

            try:
                if request.expires_at:
                    remaining = (request.expires_at - datetime.utcnow()).total_seconds()
                    timeout = min(remaining, self.poll_interval)
                    if timeout <= 0:
                        return await self._resolve(breakpoint_id, BreakpointStatus.TIMEOUT)
                else:
                    timeout = self.poll_interval

                await asyncio.wait_for(event.wait(), timeout=timeout)

                if breakpoint_id in self._results:
                    return self._results[breakpoint_id]

            except asyncio.TimeoutError:
                if breakpoint_id in self._results:
                    return self._results[breakpoint_id]
                continue

    async def cancel(self, breakpoint_id: str) -> BreakpointResult:
        """Cancel a pending breakpoint."""
        return await self._resolve(breakpoint_id, BreakpointStatus.CANCELLED)

    async def list_pending(
        self,
        execution_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[BreakpointRequest]:
        """List pending breakpoints."""
        pending = await self.store.list_pending(execution_id, user_id)

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
    """Create a new breakpoint manager."""
    return BreakpointManager(
        store=store,
        notifier=notifier,
        poll_interval=poll_interval,
    )


def set_global_breakpoint_manager(manager: BreakpointManager) -> None:
    """Set the global breakpoint manager instance"""
    global _breakpoint_manager
    _breakpoint_manager = manager
