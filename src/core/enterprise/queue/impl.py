"""
Queue & Transaction Implementation

In-memory implementation with optional persistence hooks.
Production should use Redis/PostgreSQL backend.

Reference: ITEM_PIPELINE_SPEC.md Section 17
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from heapq import heappush, heappop
from typing import Any, Callable, Dict, List, Optional, Protocol

from . import (
    CompensationAction,
    QueueDefinition,
    QueueItem,
    QueueItemStatus,
    QueueStats,
    Transaction,
    TransactionCheckpoint,
    TransactionStatus,
)

logger = logging.getLogger(__name__)


class QueueStore(Protocol):
    """Storage protocol for queue persistence."""

    async def save_queue_def(self, definition: QueueDefinition) -> None:
        ...

    async def load_queue_def(self, queue_name: str) -> Optional[QueueDefinition]:
        ...

    async def delete_queue_def(self, queue_name: str) -> bool:
        ...

    async def save_item(self, item: QueueItem) -> None:
        ...

    async def load_item(self, item_id: str) -> Optional[QueueItem]:
        ...

    async def query_items(
        self,
        queue_name: str = None,
        status: QueueItemStatus = None,
        reference: str = None,
        tags: List[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[QueueItem]:
        ...

    async def save_transaction(self, transaction: Transaction) -> None:
        ...

    async def load_transaction(self, transaction_id: str) -> Optional[Transaction]:
        ...

    async def query_transactions(
        self,
        status: TransactionStatus = None,
        older_than: datetime = None,
    ) -> List[Transaction]:
        ...


class InMemoryQueueStore:
    """In-memory store for development/testing."""

    def __init__(self):
        self._queues: Dict[str, QueueDefinition] = {}
        self._items: Dict[str, QueueItem] = {}
        self._transactions: Dict[str, Transaction] = {}

    async def save_queue_def(self, definition: QueueDefinition) -> None:
        self._queues[definition.queue_name] = definition

    async def load_queue_def(self, queue_name: str) -> Optional[QueueDefinition]:
        return self._queues.get(queue_name)

    async def delete_queue_def(self, queue_name: str) -> bool:
        if queue_name in self._queues:
            del self._queues[queue_name]
            return True
        return False

    async def save_item(self, item: QueueItem) -> None:
        self._items[item.item_id] = item

    async def load_item(self, item_id: str) -> Optional[QueueItem]:
        return self._items.get(item_id)

    async def query_items(
        self,
        queue_name: str = None,
        status: QueueItemStatus = None,
        reference: str = None,
        tags: List[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[QueueItem]:
        results = []
        for item in self._items.values():
            if queue_name and item.queue_name != queue_name:
                continue
            if status and item.status != status:
                continue
            if reference and item.reference != reference:
                continue
            if tags and not all(t in item.tags for t in tags):
                continue
            results.append(item)

        # Sort by priority (desc) then created_at (asc)
        results.sort(key=lambda x: (-x.priority, x.created_at or datetime.min))
        return results[offset:offset + limit]

    async def save_transaction(self, transaction: Transaction) -> None:
        self._transactions[transaction.transaction_id] = transaction

    async def load_transaction(self, transaction_id: str) -> Optional[Transaction]:
        return self._transactions.get(transaction_id)

    async def query_transactions(
        self,
        status: TransactionStatus = None,
        older_than: datetime = None,
    ) -> List[Transaction]:
        results = []
        for txn in self._transactions.values():
            if status and txn.status != status:
                continue
            if older_than and txn.started_at and txn.started_at > older_than:
                continue
            results.append(txn)
        return results


class WorkQueueImpl:
    """Work queue implementation."""

    def __init__(
        self,
        store: QueueStore = None,
        default_visibility_timeout: int = 300,
    ):
        self._store = store or InMemoryQueueStore()
        self._default_visibility_timeout = default_visibility_timeout
        self._lock = asyncio.Lock()

    async def create_queue(self, definition: QueueDefinition) -> str:
        """Create a new queue."""
        now = datetime.utcnow()
        definition.created_at = definition.created_at or now
        definition.updated_at = now

        await self._store.save_queue_def(definition)
        logger.info(f"Created queue: {definition.queue_name}")
        return definition.queue_name

    async def delete_queue(self, queue_name: str) -> bool:
        """Delete a queue."""
        result = await self._store.delete_queue_def(queue_name)
        if result:
            logger.info(f"Deleted queue: {queue_name}")
        return result

    async def get_queue(self, queue_name: str) -> Optional[QueueDefinition]:
        """Get queue definition."""
        return await self._store.load_queue_def(queue_name)

    async def add_item(
        self,
        queue_name: str,
        reference: str,
        data: Dict[str, Any],
        priority: int = 5,
        deadline: datetime = None,
        defer_until: datetime = None,
        tags: List[str] = None,
    ) -> QueueItem:
        """Add item to queue."""
        queue_def = await self._store.load_queue_def(queue_name)

        now = datetime.utcnow()

        # Calculate deadline from queue default if not specified
        if not deadline and queue_def and queue_def.default_deadline_minutes:
            deadline = now + timedelta(minutes=queue_def.default_deadline_minutes)

        item = QueueItem(
            item_id=str(uuid.uuid4()),
            queue_name=queue_name,
            reference=reference,
            data=data,
            priority=max(1, min(10, priority)),
            status=QueueItemStatus.NEW,
            created_at=now,
            max_retries=queue_def.max_retries if queue_def else 3,
            deadline=deadline,
            defer_until=defer_until,
            tags=tags or [],
        )

        await self._store.save_item(item)
        logger.debug(f"Added item {item.item_id} to queue {queue_name}")
        return item

    async def add_bulk(
        self,
        queue_name: str,
        items: List[Dict[str, Any]],
    ) -> List[QueueItem]:
        """Add multiple items to queue."""
        results = []
        for item_def in items:
            item = await self.add_item(
                queue_name=queue_name,
                reference=item_def.get("reference", ""),
                data=item_def.get("data", {}),
                priority=item_def.get("priority", 5),
                deadline=item_def.get("deadline"),
                defer_until=item_def.get("defer_until"),
                tags=item_def.get("tags"),
            )
            results.append(item)
        return results

    async def get_next_item(
        self,
        queue_name: str,
        robot_id: str,
        filter_tags: List[str] = None,
        min_priority: int = None,
    ) -> Optional[QueueItem]:
        """Get next item to process."""
        async with self._lock:
            items = await self._store.query_items(
                queue_name=queue_name,
                tags=filter_tags,
            )

            now = datetime.utcnow()

            for item in items:
                # Skip if not processable
                if not item.is_processable:
                    continue

                # Check priority filter
                if min_priority and item.priority < min_priority:
                    continue

                # Claim the item
                item.status = QueueItemStatus.IN_PROGRESS
                item.started_at = now
                item.robot_id = robot_id

                await self._store.save_item(item)
                logger.debug(f"Robot {robot_id} claimed item {item.item_id}")
                return item

        return None

    async def complete_item(
        self,
        item_id: str,
        output: Dict[str, Any] = None,
    ) -> QueueItem:
        """Mark item as completed."""
        item = await self._store.load_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")

        item.status = QueueItemStatus.COMPLETED
        item.completed_at = datetime.utcnow()
        item.output = output

        await self._store.save_item(item)
        logger.debug(f"Completed item {item_id}")
        return item

    async def fail_item(
        self,
        item_id: str,
        error: str,
        error_details: Dict[str, Any] = None,
        retry: bool = True,
    ) -> QueueItem:
        """Mark item as failed."""
        item = await self._store.load_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")

        item.error = error
        item.error_details = error_details
        item.retry_count += 1

        if retry and item.retry_count < item.max_retries:
            item.status = QueueItemStatus.RETRYING
            # Exponential backoff for retry
            delay = min(60 * (2 ** item.retry_count), 3600)
            item.defer_until = datetime.utcnow() + timedelta(seconds=delay)
            logger.debug(f"Item {item_id} scheduled for retry {item.retry_count}")
        else:
            item.status = QueueItemStatus.FAILED
            item.completed_at = datetime.utcnow()
            logger.debug(f"Item {item_id} failed permanently")

        await self._store.save_item(item)
        return item

    async def defer_item(
        self,
        item_id: str,
        defer_until: datetime,
    ) -> QueueItem:
        """Defer item processing."""
        item = await self._store.load_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")

        item.status = QueueItemStatus.DEFERRED
        item.defer_until = defer_until
        item.robot_id = None

        await self._store.save_item(item)
        logger.debug(f"Deferred item {item_id} until {defer_until}")
        return item

    async def abandon_item(
        self,
        item_id: str,
        reason: str = None,
    ) -> QueueItem:
        """Abandon item (no more retries)."""
        item = await self._store.load_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")

        item.status = QueueItemStatus.ABANDONED
        item.completed_at = datetime.utcnow()
        item.error = reason or "Abandoned"

        await self._store.save_item(item)
        logger.debug(f"Abandoned item {item_id}")
        return item

    async def get_item(self, item_id: str) -> Optional[QueueItem]:
        """Get item by ID."""
        return await self._store.load_item(item_id)

    async def get_items(
        self,
        queue_name: str,
        status: QueueItemStatus = None,
        reference: str = None,
        tags: List[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[QueueItem]:
        """Get items from queue."""
        return await self._store.query_items(
            queue_name=queue_name,
            status=status,
            reference=reference,
            tags=tags,
            limit=limit,
            offset=offset,
        )

    async def get_stats(self, queue_name: str) -> QueueStats:
        """Get queue statistics."""
        items = await self._store.query_items(queue_name=queue_name, limit=10000)

        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        stats = QueueStats(
            queue_name=queue_name,
            timestamp=now,
            total_items=len(items),
        )

        processing_times = []
        wait_times = []

        for item in items:
            if item.status == QueueItemStatus.NEW:
                stats.new_items += 1
            elif item.status == QueueItemStatus.IN_PROGRESS:
                stats.in_progress += 1
            elif item.status == QueueItemStatus.COMPLETED:
                if item.completed_at and item.completed_at >= today_start:
                    stats.completed_today += 1
                if item.started_at and item.completed_at:
                    processing_times.append(
                        (item.completed_at - item.started_at).total_seconds() * 1000
                    )
            elif item.status == QueueItemStatus.FAILED:
                if item.completed_at and item.completed_at >= today_start:
                    stats.failed_today += 1
            elif item.status == QueueItemStatus.ABANDONED:
                stats.abandoned += 1

            # Wait time
            if item.created_at and item.started_at:
                wait_times.append(
                    (item.started_at - item.created_at).total_seconds() * 1000
                )

            # Deadline exceeded
            if item.deadline and now > item.deadline:
                if item.status not in (QueueItemStatus.COMPLETED, QueueItemStatus.ABANDONED):
                    stats.items_exceeding_deadline += 1

        if processing_times:
            stats.avg_processing_time_ms = int(sum(processing_times) / len(processing_times))
            stats.max_processing_time_ms = int(max(processing_times))

        if wait_times:
            stats.avg_wait_time_ms = int(sum(wait_times) / len(wait_times))

        # Calculate throughput
        if stats.completed_today > 0:
            hours_elapsed = (now - today_start).total_seconds() / 3600
            if hours_elapsed > 0:
                stats.throughput_per_hour = stats.completed_today / hours_elapsed

        return stats


class TransactionManagerImpl:
    """Transaction manager implementation."""

    def __init__(
        self,
        store: QueueStore = None,
        compensation_executor: Callable = None,
    ):
        """
        Initialize transaction manager.

        Args:
            store: Storage backend
            compensation_executor: Function to execute compensation actions
                                  Signature: async def(action: CompensationAction, context: Dict) -> Dict
        """
        self._store = store or InMemoryQueueStore()
        self._compensation_executor = compensation_executor
        self._lock = asyncio.Lock()

    async def begin_transaction(
        self,
        queue_item_id: str,
        workflow_id: str,
    ) -> Transaction:
        """Begin a new transaction."""
        transaction = Transaction(
            transaction_id=str(uuid.uuid4()),
            queue_item_id=queue_item_id,
            workflow_id=workflow_id,
            status=TransactionStatus.STARTED,
            started_at=datetime.utcnow(),
        )

        await self._store.save_transaction(transaction)
        logger.info(f"Started transaction {transaction.transaction_id}")
        return transaction

    async def checkpoint(
        self,
        transaction_id: str,
        step_id: str,
        state: Dict[str, Any],
        compensation: CompensationAction = None,
    ) -> TransactionCheckpoint:
        """Create checkpoint."""
        transaction = await self._store.load_transaction(transaction_id)
        if not transaction:
            raise ValueError(f"Transaction not found: {transaction_id}")

        if transaction.status != TransactionStatus.STARTED:
            raise ValueError(f"Cannot checkpoint {transaction.status} transaction")

        checkpoint = transaction.add_checkpoint(step_id, state, compensation)
        await self._store.save_transaction(transaction)

        logger.debug(f"Checkpoint {checkpoint.checkpoint_id} for transaction {transaction_id}")
        return checkpoint

    async def commit(self, transaction_id: str) -> Transaction:
        """Commit transaction."""
        async with self._lock:
            transaction = await self._store.load_transaction(transaction_id)
            if not transaction:
                raise ValueError(f"Transaction not found: {transaction_id}")

            if transaction.status != TransactionStatus.STARTED:
                raise ValueError(f"Cannot commit {transaction.status} transaction")

            transaction.status = TransactionStatus.COMMITTED
            transaction.completed_at = datetime.utcnow()

            await self._store.save_transaction(transaction)
            logger.info(f"Committed transaction {transaction_id}")
            return transaction

    async def rollback(
        self,
        transaction_id: str,
        execute_compensation: bool = True,
    ) -> Transaction:
        """Rollback transaction."""
        async with self._lock:
            transaction = await self._store.load_transaction(transaction_id)
            if not transaction:
                raise ValueError(f"Transaction not found: {transaction_id}")

            if transaction.status not in (TransactionStatus.STARTED, TransactionStatus.FAILED):
                raise ValueError(f"Cannot rollback {transaction.status} transaction")

            # Execute compensation actions in reverse order
            if execute_compensation and self._compensation_executor:
                for action in reversed(transaction.compensation_actions):
                    if not action.executed:
                        try:
                            context = {
                                "transaction_id": transaction_id,
                                "queue_item_id": transaction.queue_item_id,
                            }
                            result = await self._compensation_executor(action, context)
                            action.executed = True
                            action.executed_at = datetime.utcnow()
                            action.result = result
                        except Exception as e:
                            action.error = str(e)
                            logger.error(f"Compensation action {action.action_id} failed: {e}")

            transaction.status = TransactionStatus.ROLLED_BACK
            transaction.completed_at = datetime.utcnow()

            await self._store.save_transaction(transaction)
            logger.info(f"Rolled back transaction {transaction_id}")
            return transaction

    async def recover(self, transaction_id: str) -> Transaction:
        """Recover transaction from last checkpoint."""
        transaction = await self._store.load_transaction(transaction_id)
        if not transaction:
            raise ValueError(f"Transaction not found: {transaction_id}")

        if not transaction.checkpoints:
            logger.warning(f"No checkpoints for transaction {transaction_id}")
            return transaction

        # Get last checkpoint
        last_checkpoint = transaction.checkpoints[-1]
        logger.info(
            f"Recovering transaction {transaction_id} from checkpoint {last_checkpoint.checkpoint_id}"
        )

        return transaction

    async def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        """Get transaction by ID."""
        return await self._store.load_transaction(transaction_id)

    async def get_pending_transactions(
        self,
        older_than: timedelta = None,
    ) -> List[Transaction]:
        """Get pending (incomplete) transactions."""
        cutoff = None
        if older_than:
            cutoff = datetime.utcnow() - older_than

        return await self._store.query_transactions(
            status=TransactionStatus.STARTED,
            older_than=cutoff,
        )


# Singleton instances
_work_queue: Optional[WorkQueueImpl] = None
_transaction_manager: Optional[TransactionManagerImpl] = None


def get_work_queue(store: QueueStore = None) -> WorkQueueImpl:
    """Get or create work queue singleton."""
    global _work_queue
    if _work_queue is None:
        _work_queue = WorkQueueImpl(store=store)
    return _work_queue


def get_transaction_manager(
    store: QueueStore = None,
    compensation_executor: Callable = None,
) -> TransactionManagerImpl:
    """Get or create transaction manager singleton."""
    global _transaction_manager
    if _transaction_manager is None:
        _transaction_manager = TransactionManagerImpl(
            store=store,
            compensation_executor=compensation_executor,
        )
    return _transaction_manager


def reset_queue_system() -> None:
    """Reset singletons (for testing)."""
    global _work_queue, _transaction_manager
    _work_queue = None
    _transaction_manager = None
