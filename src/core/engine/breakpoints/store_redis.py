# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Redis Breakpoint Store

Persistent breakpoint storage using Redis for cloud deployments.
Supports cross-process resolution via Redis Pub/Sub.
"""

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

# Redis key prefixes
_PREFIX = "flyto:bp"
_REQ_KEY = f"{_PREFIX}:req"        # Hash: breakpoint data
_STATUS_KEY = f"{_PREFIX}:status"  # String: status value
_RESP_KEY = f"{_PREFIX}:resp"      # List: JSON responses
_PENDING_KEY = f"{_PREFIX}:pending"  # Set: pending breakpoint IDs
_CHANNEL = f"{_PREFIX}:resolved"   # Pub/Sub channel prefix


def _serialize_request(request: BreakpointRequest) -> Dict[str, str]:
    """Serialize BreakpointRequest to Redis hash fields."""
    return {
        "breakpoint_id": request.breakpoint_id,
        "execution_id": request.execution_id,
        "step_id": request.step_id,
        "workflow_id": request.workflow_id or "",
        "title": request.title,
        "description": request.description,
        "required_approvers": json.dumps(request.required_approvers),
        "approval_mode": request.approval_mode.value,
        "timeout_seconds": str(request.timeout_seconds or 0),
        "created_at": request.created_at.isoformat(),
        "expires_at": request.expires_at.isoformat() if request.expires_at else "",
        "context_snapshot": json.dumps(request.context_snapshot),
        "custom_fields": json.dumps(request.custom_fields),
        "metadata": json.dumps(request.metadata),
    }


def _deserialize_request(data: Dict[str, str]) -> BreakpointRequest:
    """Deserialize Redis hash fields to BreakpointRequest."""
    timeout_seconds = int(data.get("timeout_seconds", "0")) or None
    expires_at_str = data.get("expires_at", "")

    return BreakpointRequest(
        breakpoint_id=data["breakpoint_id"],
        execution_id=data["execution_id"],
        step_id=data["step_id"],
        workflow_id=data.get("workflow_id") or None,
        title=data.get("title", ""),
        description=data.get("description", ""),
        required_approvers=json.loads(data.get("required_approvers", "[]")),
        approval_mode=ApprovalMode(data.get("approval_mode", "single")),
        timeout_seconds=timeout_seconds,
        created_at=datetime.fromisoformat(data["created_at"]),
        expires_at=datetime.fromisoformat(expires_at_str) if expires_at_str else None,
        context_snapshot=json.loads(data.get("context_snapshot", "{}")),
        custom_fields=json.loads(data.get("custom_fields", "[]")),
        metadata=json.loads(data.get("metadata", "{}")),
    )


def _serialize_response(response: ApprovalResponse) -> str:
    """Serialize ApprovalResponse to JSON string."""
    return json.dumps({
        "breakpoint_id": response.breakpoint_id,
        "approved": response.approved,
        "user_id": response.user_id,
        "comment": response.comment,
        "custom_inputs": response.custom_inputs,
        "responded_at": response.responded_at.isoformat(),
    })


def _deserialize_response(data: str) -> ApprovalResponse:
    """Deserialize JSON string to ApprovalResponse."""
    d = json.loads(data)
    return ApprovalResponse(
        breakpoint_id=d["breakpoint_id"],
        approved=d["approved"],
        user_id=d["user_id"],
        comment=d.get("comment"),
        custom_inputs=d.get("custom_inputs", {}),
        responded_at=datetime.fromisoformat(d["responded_at"]),
    )


class RedisBreakpointStore:
    """
    Redis-backed breakpoint store for cloud deployments.

    Uses Redis hashes for request data, lists for responses,
    and Pub/Sub for cross-process resolution notification.

    Args:
        redis: An async redis client (redis.asyncio.Redis)
        ttl: TTL for breakpoint keys in seconds (default: 24h)
    """

    def __init__(self, redis, ttl: int = 86400):
        self._redis = redis
        self._ttl = ttl

    def _req_key(self, bp_id: str) -> str:
        return f"{_REQ_KEY}:{bp_id}"

    def _status_key(self, bp_id: str) -> str:
        return f"{_STATUS_KEY}:{bp_id}"

    def _resp_key(self, bp_id: str) -> str:
        return f"{_RESP_KEY}:{bp_id}"

    def _channel_key(self, bp_id: str) -> str:
        return f"{_CHANNEL}:{bp_id}"

    async def save(self, request: BreakpointRequest) -> None:
        pipe = self._redis.pipeline()
        pipe.hset(self._req_key(request.breakpoint_id), mapping=_serialize_request(request))
        pipe.set(self._status_key(request.breakpoint_id), BreakpointStatus.PENDING.value)
        pipe.sadd(_PENDING_KEY, request.breakpoint_id)
        # Set TTL
        pipe.expire(self._req_key(request.breakpoint_id), self._ttl)
        pipe.expire(self._status_key(request.breakpoint_id), self._ttl)
        await pipe.execute()
        logger.debug("Saved breakpoint %s to Redis", request.breakpoint_id)

    async def load(self, breakpoint_id: str) -> Optional[BreakpointRequest]:
        data = await self._redis.hgetall(self._req_key(breakpoint_id))
        if not data:
            return None
        # Redis returns bytes — decode if needed
        decoded = {}
        for k, v in data.items():
            key = k.decode() if isinstance(k, bytes) else k
            val = v.decode() if isinstance(v, bytes) else v
            decoded[key] = val
        return _deserialize_request(decoded)

    async def list_pending(
        self,
        execution_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[BreakpointRequest]:
        bp_ids = await self._redis.smembers(_PENDING_KEY)
        pending = []
        for raw_id in bp_ids:
            bp_id = raw_id.decode() if isinstance(raw_id, bytes) else raw_id
            # Check status is still pending
            status = await self._redis.get(self._status_key(bp_id))
            if status:
                status_str = status.decode() if isinstance(status, bytes) else status
                if status_str != BreakpointStatus.PENDING.value:
                    # Stale entry — remove from pending set
                    await self._redis.srem(_PENDING_KEY, bp_id)
                    continue
            request = await self.load(bp_id)
            if not request:
                await self._redis.srem(_PENDING_KEY, bp_id)
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
        await self._redis.set(
            self._status_key(breakpoint_id),
            status.value,
            ex=self._ttl,
        )
        if status != BreakpointStatus.PENDING:
            await self._redis.srem(_PENDING_KEY, breakpoint_id)

    async def save_response(self, response: ApprovalResponse) -> None:
        key = self._resp_key(response.breakpoint_id)
        await self._redis.rpush(key, _serialize_response(response))
        await self._redis.expire(key, self._ttl)

    async def get_responses(self, breakpoint_id: str) -> List[ApprovalResponse]:
        raw_list = await self._redis.lrange(self._resp_key(breakpoint_id), 0, -1)
        responses = []
        for raw in raw_list:
            data = raw.decode() if isinstance(raw, bytes) else raw
            responses.append(_deserialize_response(data))
        return responses

    async def delete(self, breakpoint_id: str) -> None:
        pipe = self._redis.pipeline()
        pipe.delete(self._req_key(breakpoint_id))
        pipe.delete(self._status_key(breakpoint_id))
        pipe.delete(self._resp_key(breakpoint_id))
        pipe.srem(_PENDING_KEY, breakpoint_id)
        await pipe.execute()

    # =========================================================================
    # Pub/Sub helpers for cross-process resolution
    # =========================================================================

    async def publish_resolution(self, breakpoint_id: str, result: BreakpointResult) -> None:
        """Publish resolution event so waiting workers can wake up."""
        payload = json.dumps(result.to_dict())
        await self._redis.publish(self._channel_key(breakpoint_id), payload)

    async def subscribe_resolution(self, breakpoint_id: str, timeout: float = 0) -> Optional[BreakpointResult]:
        """
        Subscribe and wait for a resolution event.

        Args:
            breakpoint_id: The breakpoint to wait for
            timeout: Max seconds to wait (0 = indefinite, uses poll fallback)

        Returns:
            BreakpointResult if resolved, None if timeout
        """
        import asyncio

        pubsub = self._redis.pubsub()
        channel = self._channel_key(breakpoint_id)
        await pubsub.subscribe(channel)

        try:
            # Check if already resolved before subscribing
            status = await self._redis.get(self._status_key(breakpoint_id))
            if status:
                status_str = status.decode() if isinstance(status, bytes) else status
                if status_str != BreakpointStatus.PENDING.value:
                    return None  # Already resolved — caller should fetch result

            while True:
                try:
                    wait_time = timeout if timeout > 0 else 5.0
                    msg = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                        timeout=wait_time,
                    )
                    if msg and msg["type"] == "message":
                        data = msg["data"]
                        if isinstance(data, bytes):
                            data = data.decode()
                        d = json.loads(data)
                        return BreakpointResult(
                            breakpoint_id=d["breakpoint_id"],
                            status=BreakpointStatus(d["status"]),
                            resolved_at=datetime.fromisoformat(d["resolved_at"]),
                            final_inputs=d.get("final_inputs", {}),
                        )
                except asyncio.TimeoutError:
                    if timeout > 0:
                        return None
                    # No timeout — check status as fallback
                    status = await self._redis.get(self._status_key(breakpoint_id))
                    if status:
                        s = status.decode() if isinstance(status, bytes) else status
                        if s != BreakpointStatus.PENDING.value:
                            return None
                    continue
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
