# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Memory Queue Backend — in-process priority queue.

Zero external dependencies.  Best for:
- Desktop / single-machine deployments
- Development and testing
- Low-volume workloads

Limitations:
- State is lost on process crash
- Cannot distribute work across machines
"""

from __future__ import annotations

import asyncio
import heapq
import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .backend import IQueueBackend, ItemStatus, QueueItem, QueuePriority

logger = logging.getLogger(__name__)


class MemoryBackend(IQueueBackend):
    """In-process priority queue backed by a binary heap."""

    def __init__(self) -> None:
        # Priority heap: (-priority_value, enqueued_timestamp, item_id)
        self._heap: list[tuple[int, float, str]] = []

        # All items by ID
        self._items: Dict[str, QueueItem] = {}

        # Event fired when new work arrives (for blocking pop)
        self._work_event = asyncio.Event()

    # ------------------------------------------------------------------
    # IQueueBackend implementation
    # ------------------------------------------------------------------

    async def push(self, item: QueueItem) -> None:
        self._items[item.item_id] = item
        heapq.heappush(
            self._heap,
            (-item.priority.value, item.enqueued_at.timestamp(), item.item_id),
        )
        self._work_event.set()
        logger.debug("push %s priority=%s", item.item_id, item.priority.name)

    async def pop(
        self, worker_id: str, timeout_seconds: float = 0
    ) -> Optional[QueueItem]:
        item = self._try_pop(worker_id)
        if item is not None:
            return item

        if timeout_seconds <= 0:
            return None

        # Block until work arrives or timeout
        try:
            self._work_event.clear()
            await asyncio.wait_for(self._work_event.wait(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            return None

        return self._try_pop(worker_id)

    async def ack(self, item_id: str, result: Any = None) -> None:
        item = self._items.get(item_id)
        if item is None:
            return
        item.status = ItemStatus.COMPLETED
        item.result = result
        item.completed_at = datetime.utcnow()
        logger.debug("ack %s", item_id)

    async def fail(self, item_id: str, error: str) -> None:
        item = self._items.get(item_id)
        if item is None:
            return

        item.attempt += 1

        if item.attempt < item.max_attempts:
            # Re-enqueue
            item.status = ItemStatus.PENDING
            item.started_at = None
            item.worker_id = None
            item.error = error
            heapq.heappush(
                self._heap,
                (-item.priority.value, item.enqueued_at.timestamp(), item.item_id),
            )
            self._work_event.set()
            logger.info(
                "fail %s attempt=%d/%d — re-enqueued",
                item_id, item.attempt, item.max_attempts,
            )
        else:
            item.status = ItemStatus.FAILED
            item.error = error
            item.completed_at = datetime.utcnow()
            logger.warning("fail %s — max attempts reached", item_id)

    async def cancel(self, item_id: str) -> bool:
        item = self._items.get(item_id)
        if item is None or item.status != ItemStatus.PENDING:
            return False
        item.status = ItemStatus.CANCELLED
        item.completed_at = datetime.utcnow()
        return True

    async def get(self, item_id: str) -> Optional[QueueItem]:
        return self._items.get(item_id)

    async def recover_stale(self, stale_seconds: int = 300) -> List[QueueItem]:
        cutoff = datetime.utcnow() - timedelta(seconds=stale_seconds)
        recovered: List[QueueItem] = []

        for item in list(self._items.values()):
            if (
                item.status == ItemStatus.RUNNING
                and item.started_at is not None
                and item.started_at < cutoff
            ):
                item.attempt += 1
                if item.attempt < item.max_attempts:
                    item.status = ItemStatus.PENDING
                    item.started_at = None
                    item.worker_id = None
                    heapq.heappush(
                        self._heap,
                        (-item.priority.value, item.enqueued_at.timestamp(), item.item_id),
                    )
                    self._work_event.set()
                else:
                    item.status = ItemStatus.FAILED
                    item.error = "stale: worker did not respond"
                    item.completed_at = datetime.utcnow()

                recovered.append(item)
                logger.info("recovered stale item %s", item.item_id)

        return recovered

    async def get_stats(self) -> Dict[str, Any]:
        counts = Counter(item.status for item in self._items.values())
        return {
            "pending": counts.get(ItemStatus.PENDING, 0),
            "running": counts.get(ItemStatus.RUNNING, 0),
            "completed": counts.get(ItemStatus.COMPLETED, 0),
            "failed": counts.get(ItemStatus.FAILED, 0),
            "cancelled": counts.get(ItemStatus.CANCELLED, 0),
            "total": len(self._items),
        }

    async def list_items(
        self, status: Optional[ItemStatus] = None, limit: int = 100
    ) -> List[QueueItem]:
        items = list(self._items.values())
        if status is not None:
            items = [i for i in items if i.status == status]
        items.sort(key=lambda i: (-i.priority.value, i.enqueued_at))
        return items[:limit]

    async def purge(self, status: Optional[ItemStatus] = None) -> int:
        if status is None:
            count = len(self._items)
            self._items.clear()
            self._heap.clear()
            return count

        to_remove = [
            item_id
            for item_id, item in self._items.items()
            if item.status == status
        ]
        for item_id in to_remove:
            del self._items[item_id]
        # Rebuild heap without removed items
        self._heap = [
            entry for entry in self._heap if entry[2] in self._items
        ]
        heapq.heapify(self._heap)
        return len(to_remove)

    async def close(self) -> None:
        self._items.clear()
        self._heap.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _try_pop(self, worker_id: str) -> Optional[QueueItem]:
        """Pop the highest-priority pending item from the heap."""
        while self._heap:
            neg_priority, ts, item_id = self._heap[0]
            item = self._items.get(item_id)

            # Stale heap entry — skip
            if item is None or item.status != ItemStatus.PENDING:
                heapq.heappop(self._heap)
                continue

            heapq.heappop(self._heap)
            item.status = ItemStatus.RUNNING
            item.started_at = datetime.utcnow()
            item.worker_id = worker_id
            logger.debug("pop %s → worker %s", item_id, worker_id)
            return item

        return None
