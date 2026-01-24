"""
Queue & Transaction System

Enterprise work queue and transaction support:
- Work item queues with priority
- Reliable task distribution
- Transaction support (exactly-once processing)
- Checkpoint and recovery
- Compensation (rollback) support

Reference: ITEM_PIPELINE_SPEC.md Section 17
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


class QueueItemStatus(Enum):
    """Work queue item status."""
    NEW = "new"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"
    RETRYING = "retrying"
    DEFERRED = "deferred"


class TransactionStatus(Enum):
    """Transaction status."""
    STARTED = "started"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class QueueItem:
    """Work queue item."""
    item_id: str
    queue_name: str
    reference: str                  # Business reference (e.g., order ID)
    data: Dict[str, Any]            # Item payload
    priority: int = 5               # 1-10, 10 = highest

    # Status
    status: QueueItemStatus = QueueItemStatus.NEW
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Processing info
    robot_id: Optional[str] = None
    execution_id: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    error: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None

    # Deadlines
    deadline: Optional[datetime] = None
    defer_until: Optional[datetime] = None

    # Output
    output: Optional[Dict[str, Any]] = None

    # Metadata
    tags: List[str] = field(default_factory=list)
    custom_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_processable(self) -> bool:
        """Check if item can be processed."""
        if self.status not in (QueueItemStatus.NEW, QueueItemStatus.RETRYING):
            return False
        if self.defer_until and datetime.utcnow() < self.defer_until:
            return False
        return True


@dataclass
class QueueStats:
    """Queue statistics."""
    queue_name: str
    timestamp: datetime

    # Counts
    total_items: int = 0
    new_items: int = 0
    in_progress: int = 0
    completed_today: int = 0
    failed_today: int = 0
    abandoned: int = 0

    # Performance
    avg_processing_time_ms: int = 0
    max_processing_time_ms: int = 0
    throughput_per_hour: float = 0.0

    # SLA
    items_exceeding_deadline: int = 0
    avg_wait_time_ms: int = 0


@dataclass
class QueueDefinition:
    """Queue configuration."""
    queue_name: str
    description: Optional[str] = None

    # Processing settings
    max_retries: int = 3
    retry_delay_seconds: int = 60
    visibility_timeout_seconds: int = 300  # Lock duration

    # Priority settings
    enforce_priority: bool = True
    fifo_within_priority: bool = True

    # Limits
    max_items: Optional[int] = None
    max_item_size_bytes: int = 1024 * 1024  # 1MB

    # SLA
    default_deadline_minutes: Optional[int] = None

    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class TransactionCheckpoint:
    """Transaction checkpoint for recovery."""
    checkpoint_id: str
    step_id: str
    timestamp: datetime
    state: Dict[str, Any]
    sequence: int = 0


@dataclass
class CompensationAction:
    """Compensation action for rollback."""
    action_id: str
    step_id: str
    compensation_type: str  # "workflow" | "http" | "custom"

    # Action definition
    workflow_id: Optional[str] = None
    http_config: Optional[Dict[str, Any]] = None
    params: Dict[str, Any] = field(default_factory=dict)

    # Status
    executed: bool = False
    executed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class Transaction:
    """Transaction for exactly-once processing."""
    transaction_id: str
    queue_item_id: str
    workflow_id: str

    # Status
    status: TransactionStatus = TransactionStatus.STARTED
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Checkpoints (for recovery)
    checkpoints: List[TransactionCheckpoint] = field(default_factory=list)
    last_checkpoint_id: Optional[str] = None

    # Compensation actions (for rollback)
    compensation_actions: List[CompensationAction] = field(default_factory=list)

    # Execution context
    execution_id: Optional[str] = None
    robot_id: Optional[str] = None

    # Error info
    error: Optional[str] = None

    def add_checkpoint(
        self,
        step_id: str,
        state: Dict[str, Any],
        compensation: CompensationAction = None,
    ) -> TransactionCheckpoint:
        """Add a checkpoint."""
        checkpoint = TransactionCheckpoint(
            checkpoint_id=f"{self.transaction_id}_{len(self.checkpoints)}",
            step_id=step_id,
            timestamp=datetime.utcnow(),
            state=state,
            sequence=len(self.checkpoints),
        )
        self.checkpoints.append(checkpoint)
        self.last_checkpoint_id = checkpoint.checkpoint_id

        if compensation:
            self.compensation_actions.append(compensation)

        return checkpoint


class WorkQueue:
    """
    Work queue interface.

    Manages work items for distributed processing.
    """

    async def create_queue(self, definition: QueueDefinition) -> str:
        """
        Create a new queue.

        Args:
            definition: Queue configuration

        Returns:
            Queue name
        """
        raise NotImplementedError("Implementation required")

    async def delete_queue(self, queue_name: str) -> bool:
        """
        Delete a queue.

        Args:
            queue_name: Queue to delete

        Returns:
            True if successful
        """
        raise NotImplementedError("Implementation required")

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
        """
        Add item to queue.

        Args:
            queue_name: Target queue
            reference: Business reference
            data: Item payload
            priority: Priority (1-10)
            deadline: Optional deadline
            defer_until: Optional defer time
            tags: Optional tags

        Returns:
            Created item
        """
        raise NotImplementedError("Implementation required")

    async def add_bulk(
        self,
        queue_name: str,
        items: List[Dict[str, Any]],
    ) -> List[QueueItem]:
        """
        Add multiple items to queue.

        Args:
            queue_name: Target queue
            items: List of item definitions

        Returns:
            Created items
        """
        raise NotImplementedError("Implementation required")

    async def get_next_item(
        self,
        queue_name: str,
        robot_id: str,
        filter_tags: List[str] = None,
        min_priority: int = None,
    ) -> Optional[QueueItem]:
        """
        Get next item to process.

        Args:
            queue_name: Source queue
            robot_id: Robot claiming the item
            filter_tags: Optional tag filter
            min_priority: Minimum priority

        Returns:
            Next item or None
        """
        raise NotImplementedError("Implementation required")

    async def complete_item(
        self,
        item_id: str,
        output: Dict[str, Any] = None,
    ) -> QueueItem:
        """
        Mark item as completed.

        Args:
            item_id: Item to complete
            output: Optional output data

        Returns:
            Updated item
        """
        raise NotImplementedError("Implementation required")

    async def fail_item(
        self,
        item_id: str,
        error: str,
        error_details: Dict[str, Any] = None,
        retry: bool = True,
    ) -> QueueItem:
        """
        Mark item as failed.

        Args:
            item_id: Item to fail
            error: Error message
            error_details: Optional error details
            retry: Whether to retry

        Returns:
            Updated item
        """
        raise NotImplementedError("Implementation required")

    async def defer_item(
        self,
        item_id: str,
        defer_until: datetime,
    ) -> QueueItem:
        """
        Defer item processing.

        Args:
            item_id: Item to defer
            defer_until: When to process

        Returns:
            Updated item
        """
        raise NotImplementedError("Implementation required")

    async def abandon_item(
        self,
        item_id: str,
        reason: str = None,
    ) -> QueueItem:
        """
        Abandon item (no more retries).

        Args:
            item_id: Item to abandon
            reason: Optional reason

        Returns:
            Updated item
        """
        raise NotImplementedError("Implementation required")

    async def get_item(self, item_id: str) -> Optional[QueueItem]:
        """Get item by ID."""
        raise NotImplementedError("Implementation required")

    async def get_items(
        self,
        queue_name: str,
        status: QueueItemStatus = None,
        reference: str = None,
        tags: List[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[QueueItem]:
        """
        Get items from queue.

        Args:
            queue_name: Source queue
            status: Filter by status
            reference: Filter by reference
            tags: Filter by tags
            limit: Maximum results
            offset: Skip items

        Returns:
            List of items
        """
        raise NotImplementedError("Implementation required")

    async def get_stats(self, queue_name: str) -> QueueStats:
        """Get queue statistics."""
        raise NotImplementedError("Implementation required")


class TransactionManager:
    """
    Transaction management interface.

    Provides exactly-once processing guarantees.
    """

    async def begin_transaction(
        self,
        queue_item_id: str,
        workflow_id: str,
    ) -> Transaction:
        """
        Begin a new transaction.

        Args:
            queue_item_id: Queue item being processed
            workflow_id: Workflow ID

        Returns:
            New transaction
        """
        raise NotImplementedError("Implementation required")

    async def checkpoint(
        self,
        transaction_id: str,
        step_id: str,
        state: Dict[str, Any],
        compensation: CompensationAction = None,
    ) -> TransactionCheckpoint:
        """
        Create checkpoint.

        Args:
            transaction_id: Transaction ID
            step_id: Current step
            state: State to checkpoint
            compensation: Optional compensation action

        Returns:
            Created checkpoint
        """
        raise NotImplementedError("Implementation required")

    async def commit(self, transaction_id: str) -> Transaction:
        """
        Commit transaction.

        Args:
            transaction_id: Transaction to commit

        Returns:
            Committed transaction
        """
        raise NotImplementedError("Implementation required")

    async def rollback(
        self,
        transaction_id: str,
        execute_compensation: bool = True,
    ) -> Transaction:
        """
        Rollback transaction.

        Args:
            transaction_id: Transaction to rollback
            execute_compensation: Run compensation actions

        Returns:
            Rolled back transaction
        """
        raise NotImplementedError("Implementation required")

    async def recover(
        self,
        transaction_id: str,
    ) -> Transaction:
        """
        Recover transaction from checkpoint.

        Args:
            transaction_id: Transaction to recover

        Returns:
            Recovered transaction (ready to resume)
        """
        raise NotImplementedError("Implementation required")

    async def get_transaction(
        self,
        transaction_id: str,
    ) -> Optional[Transaction]:
        """Get transaction by ID."""
        raise NotImplementedError("Implementation required")

    async def get_pending_transactions(
        self,
        older_than: timedelta = None,
    ) -> List[Transaction]:
        """
        Get pending (incomplete) transactions.

        Args:
            older_than: Filter by age

        Returns:
            List of pending transactions
        """
        raise NotImplementedError("Implementation required")


__all__ = [
    # Enums
    'QueueItemStatus',
    'TransactionStatus',
    # Queue structures
    'QueueItem',
    'QueueStats',
    'QueueDefinition',
    # Transaction structures
    'TransactionCheckpoint',
    'CompensationAction',
    'Transaction',
    # Interfaces
    'WorkQueue',
    'TransactionManager',
]
