# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

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

    Supports three deployment modes:
    - Local (default): InMemoryBreakpointStore + asyncio.Event for same-process
    - Cloud control plane: RedisBreakpointStore + Redis Pub/Sub
    - Cloud worker: HttpBreakpointStore + HTTP polling to control plane

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

        # In-process signal (local mode)
        event = self._resolution_events.get(breakpoint_id)
        if event:
            event.set()

        # Cross-process signal (Redis Pub/Sub for cloud mode)
        if hasattr(self.store, 'publish_resolution'):
            try:
                await self.store.publish_resolution(breakpoint_id, result)
            except Exception as e:
                logger.debug("Redis publish_resolution failed: %s", e)

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

        Automatically selects the best waiting strategy:
        - HttpBreakpointStore: HTTP polling to control plane
        - RedisBreakpointStore: Redis Pub/Sub subscription
        - InMemoryBreakpointStore: asyncio.Event (same process)
        """
        request = await self.store.load(breakpoint_id)
        if not request:
            raise ValueError(f"Breakpoint not found: {breakpoint_id}")

        # Strategy 1: HTTP store — delegate to its poll-based wait
        if hasattr(self.store, 'wait_for_resolution'):
            timeout = 0
            if request.timeout_seconds and request.timeout_seconds > 0:
                timeout = request.timeout_seconds
            result = await self.store.wait_for_resolution(breakpoint_id, timeout=timeout)
            if result:
                self._results[breakpoint_id] = result
                return result
            return await self._resolve(breakpoint_id, BreakpointStatus.TIMEOUT)

        # Strategy 2: Redis store — subscribe for cross-process notification
        if hasattr(self.store, 'subscribe_resolution'):
            timeout = 0
            if request.timeout_seconds and request.timeout_seconds > 0:
                timeout = request.timeout_seconds
            result = await self.store.subscribe_resolution(breakpoint_id, timeout=timeout)
            if result:
                self._results[breakpoint_id] = result
                return result
            # Check if resolved while subscribing
            if breakpoint_id in self._results:
                return self._results[breakpoint_id]
            return await self._resolve(breakpoint_id, BreakpointStatus.TIMEOUT)

        # Strategy 3: In-memory — asyncio.Event (original behavior)
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


def create_cloud_worker_manager(
    control_plane_url: str,
    auth_token: str = "",
    poll_interval: float = 1.0,
) -> BreakpointManager:
    """
    Create a breakpoint manager for cloud workers.

    Uses HttpBreakpointStore to communicate with the control plane API.
    The worker creates breakpoints on the control plane and polls
    for user responses.

    Args:
        control_plane_url: Control plane API URL (e.g., "https://api.flyto.app")
        auth_token: Bearer token for worker authentication
        poll_interval: Seconds between status polls

    Returns:
        BreakpointManager configured for cloud worker mode
    """
    from .store_http import HttpBreakpointStore

    store = HttpBreakpointStore(
        base_url=control_plane_url,
        auth_token=auth_token,
        poll_interval=poll_interval,
    )

    return BreakpointManager(
        store=store,
        notifier=NullNotifier(),
        poll_interval=poll_interval,
    )


def auto_configure_breakpoint_manager() -> BreakpointManager:
    """
    Auto-detect deployment mode and configure the breakpoint manager.

    Environment variables:
    - DEPLOYMENT_MODE: "local" (default), "cloud", "worker"
    - CONTROL_PLANE_URL: required for "worker" mode
    - WORKER_AUTH_TOKEN: auth token for worker mode
    - REDIS_URL: if set in "cloud" mode, uses Redis store

    Returns:
        Configured BreakpointManager (also set as global)
    """
    import os

    mode = os.environ.get("DEPLOYMENT_MODE", "local")
    manager = None

    if mode == "worker":
        control_plane_url = os.environ.get("CONTROL_PLANE_URL", "")
        if not control_plane_url:
            logger.warning("CONTROL_PLANE_URL not set for worker mode, using in-memory")
            manager = BreakpointManager()
        else:
            auth_token = os.environ.get("WORKER_AUTH_TOKEN", "")
            manager = create_cloud_worker_manager(
                control_plane_url=control_plane_url,
                auth_token=auth_token,
            )
            logger.info("Breakpoint manager: cloud worker → %s", control_plane_url)

    elif mode == "cloud":
        redis_url = os.environ.get("REDIS_URL", "")
        if redis_url:
            try:
                import redis.asyncio as aioredis
                from .store_redis import RedisBreakpointStore

                redis_client = aioredis.from_url(redis_url, decode_responses=False)
                store = RedisBreakpointStore(redis_client)
                manager = BreakpointManager(store=store)
                logger.info("Breakpoint manager: Redis store (%s)", redis_url[:30])
            except ImportError:
                logger.warning("redis package not available, using in-memory")
                manager = BreakpointManager()
        else:
            manager = BreakpointManager()
            logger.info("Breakpoint manager: in-memory (cloud, no Redis)")

    else:
        manager = BreakpointManager()
        logger.info("Breakpoint manager: in-memory (local mode)")

    set_global_breakpoint_manager(manager)
    return manager
