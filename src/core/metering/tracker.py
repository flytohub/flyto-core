"""
Metering Tracker

Tracks usage and billing for module/plugin invocations.

Billing Rules (from spec):
- bill_on: success_only (only bill successful invocations)
- retry_attempts_billed: false (retries don't count)
- batch_mode: per_item (each item in batch counts separately)

Cost Classes:
- free: 0x multiplier
- standard: 1x multiplier
- premium: 3x multiplier
- enterprise: 10x multiplier
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class CostClass(str, Enum):
    """Cost class for billing."""
    FREE = "free"
    STANDARD = "standard"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


@dataclass
class MeteringConfig:
    """Metering configuration."""
    bill_on: str = "success_only"  # success_only, all_except_validation
    retry_attempts_billed: bool = False
    batch_mode: str = "per_item"  # per_item, per_invoke
    cost_class_multipliers: Dict[str, float] = field(default_factory=lambda: {
        "free": 0.0,
        "standard": 1.0,
        "premium": 3.0,
        "enterprise": 10.0,
    })


@dataclass
class MeteringRecord:
    """Record of a billable invocation."""
    id: str
    timestamp: float
    tenant_id: str
    execution_id: str
    plugin_id: str
    step_id: str
    cost_class: str
    base_points: int
    multiplier: float
    total_points: float
    batch_size: int = 1
    success: bool = True
    is_retry: bool = False
    duration_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "tenant_id": self.tenant_id,
            "execution_id": self.execution_id,
            "plugin_id": self.plugin_id,
            "step_id": self.step_id,
            "cost_class": self.cost_class,
            "base_points": self.base_points,
            "multiplier": self.multiplier,
            "total_points": self.total_points,
            "batch_size": self.batch_size,
            "success": self.success,
            "is_retry": self.is_retry,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


class MeteringTracker:
    """
    Tracks usage and billing for invocations.

    Usage:
        tracker = get_metering_tracker()
        record = tracker.record(
            tenant_id="tenant-123",
            execution_id="exec-456",
            plugin_id="flyto-official/database",
            step_id="query",
            cost_class="standard",
            base_points=1,
            success=True,
        )
    """

    def __init__(self, config: Optional[MeteringConfig] = None):
        self.config = config or MeteringConfig()

        # In-memory buffer for records (for batching/flushing)
        self._buffer: List[MeteringRecord] = []
        self._buffer_max_size: int = 100

        # Callbacks for record persistence
        self._on_record: Optional[Callable[[MeteringRecord], None]] = None
        self._on_flush: Optional[Callable[[List[MeteringRecord]], None]] = None

        # Statistics
        self._total_recorded: int = 0
        self._total_points: float = 0.0

    def record(
        self,
        tenant_id: str,
        execution_id: str,
        plugin_id: str,
        step_id: str,
        cost_class: str,
        base_points: int,
        success: bool = True,
        is_retry: bool = False,
        batch_size: int = 1,
        duration_ms: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[MeteringRecord]:
        """
        Record a billable invocation.

        Args:
            tenant_id: Tenant identifier
            execution_id: Execution context ID
            plugin_id: Plugin identifier
            step_id: Step identifier
            cost_class: Cost class (free/standard/premium/enterprise)
            base_points: Base point cost from manifest
            success: Whether invocation succeeded
            is_retry: Whether this is a retry attempt
            batch_size: Number of items in batch (for batch operations)
            duration_ms: Execution duration in milliseconds
            metadata: Additional metadata

        Returns:
            MeteringRecord if billable, None if skipped
        """
        # Check if should bill based on config
        if not self._should_bill(success, is_retry):
            logger.debug(
                f"Skipping metering: success={success}, is_retry={is_retry}, "
                f"bill_on={self.config.bill_on}, retry_billed={self.config.retry_attempts_billed}"
            )
            return None

        # Calculate multiplier and total points
        multiplier = self.config.cost_class_multipliers.get(cost_class, 1.0)

        # Apply batch mode
        if self.config.batch_mode == "per_item":
            effective_batch_size = batch_size
        else:  # per_invoke
            effective_batch_size = 1

        total_points = base_points * multiplier * effective_batch_size

        # Create record
        record = MeteringRecord(
            id=self._generate_id(),
            timestamp=time.time(),
            tenant_id=tenant_id,
            execution_id=execution_id,
            plugin_id=plugin_id,
            step_id=step_id,
            cost_class=cost_class,
            base_points=base_points,
            multiplier=multiplier,
            total_points=total_points,
            batch_size=batch_size,
            success=success,
            is_retry=is_retry,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )

        # Add to buffer
        self._buffer.append(record)
        self._total_recorded += 1
        self._total_points += total_points

        logger.debug(
            f"Metered: {plugin_id}.{step_id} -> {total_points} points "
            f"(base={base_points}, mult={multiplier}, batch={effective_batch_size})"
        )

        # Notify callback
        if self._on_record:
            try:
                self._on_record(record)
            except Exception as e:
                logger.error(f"Metering callback error: {e}")

        # Auto-flush if buffer full
        if len(self._buffer) >= self._buffer_max_size:
            self.flush()

        return record

    def flush(self) -> List[MeteringRecord]:
        """
        Flush buffered records.

        Returns:
            List of flushed records
        """
        if not self._buffer:
            return []

        records = self._buffer.copy()
        self._buffer.clear()

        logger.info(f"Flushing {len(records)} metering records")

        # Notify callback
        if self._on_flush:
            try:
                self._on_flush(records)
            except Exception as e:
                logger.error(f"Metering flush callback error: {e}")

        return records

    def get_tenant_usage(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get usage summary for a tenant from buffer.

        Note: This only includes buffered records.
        For full history, query the persistence layer.
        """
        tenant_records = [r for r in self._buffer if r.tenant_id == tenant_id]

        total_points = sum(r.total_points for r in tenant_records)
        by_plugin: Dict[str, float] = {}

        for record in tenant_records:
            key = f"{record.plugin_id}.{record.step_id}"
            by_plugin[key] = by_plugin.get(key, 0) + record.total_points

        return {
            "tenant_id": tenant_id,
            "total_points": total_points,
            "record_count": len(tenant_records),
            "by_plugin": by_plugin,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get tracker statistics."""
        return {
            "total_recorded": self._total_recorded,
            "total_points": self._total_points,
            "buffer_size": len(self._buffer),
            "buffer_max_size": self._buffer_max_size,
        }

    def set_on_record(self, callback: Callable[[MeteringRecord], None]):
        """Set callback for each record."""
        self._on_record = callback

    def set_on_flush(self, callback: Callable[[List[MeteringRecord]], None]):
        """Set callback for flush."""
        self._on_flush = callback

    def _should_bill(self, success: bool, is_retry: bool) -> bool:
        """Determine if invocation should be billed."""
        # Check retry policy
        if is_retry and not self.config.retry_attempts_billed:
            return False

        # Check success policy
        if self.config.bill_on == "success_only":
            return success
        elif self.config.bill_on == "all_except_validation":
            # Would need validation error flag - for now, bill all non-retries
            return True

        return True

    def _generate_id(self) -> str:
        """Generate unique record ID."""
        import secrets as sec
        return f"meter-{sec.token_hex(8)}"


# Global singleton
_tracker: Optional[MeteringTracker] = None


def get_metering_tracker(config: Optional[MeteringConfig] = None) -> MeteringTracker:
    """Get global metering tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = MeteringTracker(config)
    return _tracker
