# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
HTTP Breakpoint Store

Cloud worker uses this to communicate with the Control Plane's breakpoint API.
The worker creates breakpoints and waits for resolution via HTTP polling.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .models import (
    ApprovalMode,
    ApprovalResponse,
    BreakpointRequest,
    BreakpointResult,
    BreakpointStatus,
)

logger = logging.getLogger(__name__)


class HttpBreakpointStore:
    """
    HTTP-backed breakpoint store for cloud workers.

    Proxies all breakpoint operations to the Control Plane API.
    Workers use this instead of InMemoryBreakpointStore so that
    breakpoints are visible to the frontend and resolvable by users.

    Args:
        base_url: Control plane API base URL (e.g., "https://api.flyto.app")
        auth_token: Bearer token for worker authentication
        poll_interval: Seconds between status polls (default: 1.0)
    """

    def __init__(
        self,
        base_url: str,
        auth_token: str = "",
        poll_interval: float = 1.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._auth_token = auth_token
        self._poll_interval = poll_interval
        self._client = None

    async def _get_client(self):
        if self._client is None:
            try:
                import httpx
                self._client = httpx.AsyncClient(
                    base_url=self._base_url,
                    timeout=30.0,
                    headers=self._headers(),
                )
            except ImportError:
                raise RuntimeError("httpx is required for HttpBreakpointStore: pip install httpx")
        return self._client

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._auth_token:
            h["Authorization"] = f"Bearer {self._auth_token}"
        return h

    async def save(self, request: BreakpointRequest) -> None:
        """POST breakpoint to control plane."""
        client = await self._get_client()
        payload = request.to_dict()
        resp = await client.post("/api/breakpoints/create", json=payload)
        if resp.status_code not in (200, 201):
            logger.error("Failed to create breakpoint: %s %s", resp.status_code, resp.text)
            raise RuntimeError(f"Failed to create breakpoint: {resp.status_code}")
        logger.debug("Created breakpoint %s on control plane", request.breakpoint_id)

    async def load(self, breakpoint_id: str) -> Optional[BreakpointRequest]:
        """GET breakpoint from control plane."""
        client = await self._get_client()
        resp = await client.get(f"/api/breakpoints/{breakpoint_id}")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            logger.error("Failed to load breakpoint: %s", resp.status_code)
            return None
        return _dict_to_request(resp.json())

    async def list_pending(
        self,
        execution_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[BreakpointRequest]:
        """GET pending breakpoints from control plane."""
        client = await self._get_client()
        params = {}
        if execution_id:
            params["execution_id"] = execution_id
        if user_id:
            params["user_id"] = user_id
        resp = await client.get("/api/breakpoints/pending", params=params)
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [_dict_to_request(bp) for bp in data.get("breakpoints", [])]

    async def update_status(
        self,
        breakpoint_id: str,
        status: BreakpointStatus,
    ) -> None:
        """PATCH breakpoint status on control plane."""
        client = await self._get_client()
        resp = await client.patch(
            f"/api/breakpoints/{breakpoint_id}/status",
            json={"status": status.value},
        )
        if resp.status_code not in (200, 204):
            logger.error("Failed to update status: %s", resp.status_code)

    async def save_response(self, response: ApprovalResponse) -> None:
        """POST approval response to control plane."""
        client = await self._get_client()
        resp = await client.post(
            f"/api/breakpoints/{response.breakpoint_id}/respond",
            json={
                "approved": response.approved,
                "user_id": response.user_id,
                "comment": response.comment,
                "custom_inputs": response.custom_inputs,
            },
        )
        if resp.status_code not in (200, 201):
            logger.error("Failed to save response: %s", resp.status_code)

    async def get_responses(self, breakpoint_id: str) -> List[ApprovalResponse]:
        """GET responses from control plane."""
        client = await self._get_client()
        resp = await client.get(f"/api/breakpoints/{breakpoint_id}")
        if resp.status_code != 200:
            return []
        data = resp.json()
        responses = []
        for r in data.get("responses", []):
            responses.append(ApprovalResponse(
                breakpoint_id=breakpoint_id,
                approved=r["approved"],
                user_id=r["user_id"],
                comment=r.get("comment"),
                custom_inputs=r.get("custom_inputs", {}),
                responded_at=datetime.fromisoformat(r["responded_at"]),
            ))
        return responses

    async def delete(self, breakpoint_id: str) -> None:
        """DELETE breakpoint from control plane."""
        client = await self._get_client()
        await client.delete(f"/api/breakpoints/{breakpoint_id}")

    # =========================================================================
    # Cloud worker: wait for resolution via polling
    # =========================================================================

    async def wait_for_resolution(
        self,
        breakpoint_id: str,
        timeout: float = 0,
    ) -> Optional[BreakpointResult]:
        """
        Poll control plane until breakpoint is resolved.

        Args:
            breakpoint_id: Breakpoint to wait for
            timeout: Max seconds (0 = indefinite)

        Returns:
            BreakpointResult if resolved, None if timeout
        """
        client = await self._get_client()
        start = asyncio.get_event_loop().time()

        while True:
            resp = await client.get(f"/api/breakpoints/{breakpoint_id}/status")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("is_resolved"):
                    # Fetch full result
                    detail_resp = await client.get(f"/api/breakpoints/{breakpoint_id}/result")
                    if detail_resp.status_code == 200:
                        return _dict_to_result(detail_resp.json())
                    # Fallback: construct minimal result
                    return BreakpointResult(
                        breakpoint_id=breakpoint_id,
                        status=BreakpointStatus(data["status"]),
                    )

            if timeout > 0:
                elapsed = asyncio.get_event_loop().time() - start
                if elapsed >= timeout:
                    return None

            await asyncio.sleep(self._poll_interval)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


def _dict_to_request(d: Dict[str, Any]) -> BreakpointRequest:
    """Convert API response dict to BreakpointRequest."""
    timeout_seconds = d.get("timeout_seconds")
    if timeout_seconds == 0:
        timeout_seconds = None

    created_at = d.get("created_at", "")
    if isinstance(created_at, str) and created_at:
        created_at = datetime.fromisoformat(created_at)
    else:
        created_at = datetime.utcnow()

    expires_at = d.get("expires_at")
    if isinstance(expires_at, str) and expires_at:
        expires_at = datetime.fromisoformat(expires_at)
    else:
        expires_at = None

    return BreakpointRequest(
        breakpoint_id=d["breakpoint_id"],
        execution_id=d["execution_id"],
        step_id=d["step_id"],
        workflow_id=d.get("workflow_id"),
        title=d.get("title", ""),
        description=d.get("description", ""),
        required_approvers=d.get("required_approvers", []),
        approval_mode=ApprovalMode(d.get("approval_mode", "single")),
        timeout_seconds=timeout_seconds,
        created_at=created_at,
        expires_at=expires_at,
        context_snapshot=d.get("context_snapshot", {}),
        custom_fields=d.get("custom_fields", []),
        metadata=d.get("metadata", {}),
    )


def _dict_to_result(d: Dict[str, Any]) -> BreakpointResult:
    """Convert API response dict to BreakpointResult."""
    resolved_at = d.get("resolved_at", "")
    if isinstance(resolved_at, str) and resolved_at:
        resolved_at = datetime.fromisoformat(resolved_at)
    else:
        resolved_at = datetime.utcnow()

    return BreakpointResult(
        breakpoint_id=d["breakpoint_id"],
        status=BreakpointStatus(d["status"]),
        final_inputs=d.get("final_inputs", {}),
        resolved_at=resolved_at,
    )
