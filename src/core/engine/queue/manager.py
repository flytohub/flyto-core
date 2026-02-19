# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Execution Queue Manager — priority-based workflow execution queue.

Pro feature gated behind FeatureFlag.WORK_QUEUE.
Manages concurrent execution with priority ordering and backpressure.
"""

import asyncio
import heapq
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

from core.licensing import FeatureFlag, LicenseError, LicenseManager

logger = logging.getLogger(__name__)


# =============================================================================
# Models
# =============================================================================


class QueuePriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class QueueItem:
    item_id: str
    workflow_id: str
    workflow_name: str
    priority: QueuePriority
    params: Dict[str, Any]
    context: Dict[str, Any]
    enqueued_at: datetime
    started_at: Optional[datetime] = None
    status: str = "pending"  # pending, running, completed, failed, cancelled
    result: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Queue Manager
# =============================================================================


class ExecutionQueueManager:
    """
    Priority-based execution queue for workflow runs.

    Pro feature — requires FeatureFlag.WORK_QUEUE.
    Manages concurrent execution with priority ordering.
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        on_execute: Optional[
            Callable[..., Coroutine[Any, Any, Any]]
        ] = None,
    ) -> None:
        self._require_feature()

        self._max_concurrent = max_concurrent
        self._on_execute = on_execute

        # Priority heap: entries are (-priority_value, enqueued_timestamp, item_id)
        # Negative priority so higher priority values are dequeued first.
        self._heap: List[tuple] = []

        # All items indexed by item_id
        self._items: Dict[str, QueueItem] = {}

        # Concurrency control
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # Event to signal new work available
        self._work_event = asyncio.Event()

        # Processing loop task
        self._loop_task: Optional[asyncio.Task] = None
        self._running = False

        # Counters for stats
        self._completed_count = 0
        self._failed_count = 0

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def enqueue(
        self,
        workflow_id: str,
        workflow_name: str,
        params: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        priority: QueuePriority = QueuePriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> QueueItem:
        """Add a workflow run to the queue. Returns the created QueueItem."""
        self._require_feature()

        item_id = str(uuid.uuid4())
        now = datetime.utcnow()

        item = QueueItem(
            item_id=item_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            priority=priority,
            params=params or {},
            context=context or {},
            enqueued_at=now,
            metadata=metadata or {},
        )

        self._items[item_id] = item

        # Push onto priority heap.
        # Negate priority value so higher priority dequeues first.
        # Use timestamp as tiebreaker (FIFO within same priority).
        heap_entry = (-priority.value, now.timestamp(), item_id)
        heapq.heappush(self._heap, heap_entry)

        logger.info(
            "Enqueued item %s for workflow %s (priority=%s)",
            item_id,
            workflow_name,
            priority.name,
        )

        # Signal the processing loop that work is available
        self._work_event.set()

        return item

    def cancel(self, item_id: str) -> bool:
        """Cancel a pending item. Returns True if cancelled, False otherwise."""
        self._require_feature()

        item = self._items.get(item_id)
        if item is None:
            return False

        if item.status != "pending":
            return False

        item.status = "cancelled"
        logger.info("Cancelled item %s", item_id)
        return True

    def get_status(self, item_id: str) -> Optional[QueueItem]:
        """Get the status of a queue item by ID."""
        return self._items.get(item_id)

    def get_queue(self) -> List[QueueItem]:
        """Get all items sorted by priority (highest first), then enqueued_at."""
        items = list(self._items.values())
        items.sort(
            key=lambda i: (-i.priority.value, i.enqueued_at)
        )
        return items

    def get_running(self) -> List[QueueItem]:
        """Get currently running items."""
        return [
            item for item in self._items.values()
            if item.status == "running"
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        pending = sum(
            1 for i in self._items.values() if i.status == "pending"
        )
        running = sum(
            1 for i in self._items.values() if i.status == "running"
        )
        return {
            "pending": pending,
            "running": running,
            "completed": self._completed_count,
            "failed": self._failed_count,
            "max_concurrent": self._max_concurrent,
        }

    async def start(self) -> None:
        """Start the processing loop."""
        self._require_feature()

        if self._running:
            logger.warning("Queue manager already running")
            return

        self._running = True
        self._loop_task = asyncio.ensure_future(self._process_loop())
        logger.info(
            "Queue manager started (max_concurrent=%d)",
            self._max_concurrent,
        )

    async def stop(self) -> None:
        """Stop the processing loop gracefully."""
        if not self._running:
            return

        self._running = False
        self._work_event.set()  # Wake up the loop so it can exit

        if self._loop_task is not None:
            try:
                await asyncio.wait_for(self._loop_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning(
                    "Queue processing loop did not stop within timeout, cancelling"
                )
                self._loop_task.cancel()
                try:
                    await self._loop_task
                except asyncio.CancelledError:
                    pass
            self._loop_task = None

        logger.info("Queue manager stopped")

    # -----------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------

    async def _process_loop(self) -> None:
        """Internal processing loop: pick next highest-priority item and execute."""
        while self._running:
            # Wait for work signal
            self._work_event.clear()

            # Try to find the next pending item from the heap
            item = self._pick_next()

            if item is None:
                # No work available — wait for signal
                await self._work_event.wait()
                continue

            # Acquire semaphore slot (respects max_concurrent)
            await self._semaphore.acquire()

            # Launch execution as a detached task so the loop continues
            asyncio.ensure_future(self._execute_item(item))

    def _pick_next(self) -> Optional[QueueItem]:
        """Pick the next pending item from the priority heap."""
        while self._heap:
            neg_priority, timestamp, item_id = self._heap[0]
            item = self._items.get(item_id)

            # Item was removed or already processed — discard stale entry
            if item is None or item.status != "pending":
                heapq.heappop(self._heap)
                continue

            heapq.heappop(self._heap)
            return item

        return None

    async def _execute_item(self, item: QueueItem) -> None:
        """Execute a single queue item via the on_execute callback."""
        try:
            item.status = "running"
            item.started_at = datetime.utcnow()

            logger.info(
                "Executing item %s — workflow %s",
                item.item_id,
                item.workflow_name,
            )

            if self._on_execute is not None:
                result = await self._on_execute(
                    workflow_id=item.workflow_id,
                    workflow_name=item.workflow_name,
                    params=item.params,
                    context=item.context,
                    metadata=item.metadata,
                )
                item.result = result

            item.status = "completed"
            self._completed_count += 1

            logger.info("Item %s completed", item.item_id)

        except Exception as exc:
            item.status = "failed"
            item.error = str(exc)
            self._failed_count += 1

            newline = "\n"
            logger.error(
                "Item %s failed: %s%s%s",
                item.item_id,
                exc,
                newline,
                type(exc).__name__,
            )

        finally:
            self._semaphore.release()
            # Signal loop in case it is waiting — more slots available now
            self._work_event.set()

    @staticmethod
    def _require_feature() -> None:
        """Verify that the WORK_QUEUE feature is licensed."""
        manager = LicenseManager.get_instance()
        if not manager.has_feature(FeatureFlag.WORK_QUEUE):
            raise LicenseError(
                "Execution Queue requires a Pro license",
                feature=FeatureFlag.WORK_QUEUE,
            )
