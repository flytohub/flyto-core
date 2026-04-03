# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Queue Backend Interface — pluggable queue backend abstraction.

Defines the abstract interface that all queue backends must implement.
Backends handle persistence and distribution; the QueueManager handles
orchestration logic on top.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# =============================================================================
# Models
# =============================================================================


class QueuePriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class ItemStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE = "stale"


@dataclass
class QueueItem:
    """An item in the execution queue."""
    item_id: str
    workflow_id: str
    workflow_name: str
    priority: QueuePriority
    params: Dict[str, Any]
    context: Dict[str, Any]
    enqueued_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: ItemStatus = ItemStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    worker_id: Optional[str] = None
    attempt: int = 0
    max_attempts: int = 3

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for transport/storage."""
        d = asdict(self)
        d["priority"] = self.priority.value
        d["status"] = self.status.value
        d["enqueued_at"] = self.enqueued_at.isoformat()
        d["started_at"] = self.started_at.isoformat() if self.started_at else None
        d["completed_at"] = self.completed_at.isoformat() if self.completed_at else None
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> QueueItem:
        """Deserialize from dict."""
        d = dict(d)  # shallow copy
        d["priority"] = QueuePriority(d["priority"])
        d["status"] = ItemStatus(d["status"])
        d["enqueued_at"] = (
            datetime.fromisoformat(d["enqueued_at"])
            if isinstance(d["enqueued_at"], str)
            else d["enqueued_at"]
        )
        if d.get("started_at") and isinstance(d["started_at"], str):
            d["started_at"] = datetime.fromisoformat(d["started_at"])
        if d.get("completed_at") and isinstance(d["completed_at"], str):
            d["completed_at"] = datetime.fromisoformat(d["completed_at"])
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_json(cls, s: str) -> QueueItem:
        return cls.from_dict(json.loads(s))


# =============================================================================
# Backend Interface
# =============================================================================


class IQueueBackend(ABC):
    """
    Abstract queue backend.

    Implementations handle persistence and distribution.
    The QueueManager calls these methods for orchestration.
    """

    @abstractmethod
    async def push(self, item: QueueItem) -> None:
        """
        Add an item to the queue.

        The backend must respect priority ordering: higher priority items
        should be returned first by pop().
        """

    @abstractmethod
    async def pop(self, worker_id: str, timeout_seconds: float = 0) -> Optional[QueueItem]:
        """
        Claim the next highest-priority pending item.

        Args:
            worker_id: ID of the worker claiming the item.
            timeout_seconds: How long to wait for an item.
                0 = return immediately (non-blocking).
                >0 = block up to this many seconds.

        Returns:
            The claimed QueueItem with status=RUNNING, or None if nothing
            available within the timeout.
        """

    @abstractmethod
    async def ack(self, item_id: str, result: Any = None) -> None:
        """
        Acknowledge successful completion of an item.

        Sets status to COMPLETED and stores the result.
        """

    @abstractmethod
    async def fail(self, item_id: str, error: str) -> None:
        """
        Mark an item as failed.

        If attempt < max_attempts, the backend should re-enqueue the item
        with incremented attempt count.  Otherwise, set status to FAILED.
        """

    @abstractmethod
    async def cancel(self, item_id: str) -> bool:
        """
        Cancel a pending item.

        Returns True if the item was pending and is now cancelled.
        Returns False if the item is already running/completed/failed.
        """

    @abstractmethod
    async def get(self, item_id: str) -> Optional[QueueItem]:
        """Get item by ID."""

    @abstractmethod
    async def recover_stale(self, stale_seconds: int = 300) -> List[QueueItem]:
        """
        Recover items that have been RUNNING longer than stale_seconds.

        These items likely belong to crashed workers.
        Re-enqueue them if attempts remain, otherwise mark FAILED.

        Returns:
            List of recovered items.
        """

    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """
        Return queue statistics.

        Must include at minimum:
            pending, running, completed, failed, cancelled counts.
        """

    @abstractmethod
    async def list_items(
        self,
        status: Optional[ItemStatus] = None,
        limit: int = 100,
    ) -> List[QueueItem]:
        """List items, optionally filtered by status."""

    @abstractmethod
    async def purge(self, status: Optional[ItemStatus] = None) -> int:
        """
        Remove items from the queue.

        Args:
            status: If given, only purge items with this status.
                    If None, purge ALL items.

        Returns:
            Number of items purged.
        """

    async def close(self) -> None:
        """Release any resources held by the backend (connections, etc.)."""
