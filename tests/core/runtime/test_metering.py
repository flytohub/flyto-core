"""
Metering Tests

Tests for metering tracker functionality.
Tasks: 1.21, 1.22
"""

import pytest
from unittest.mock import MagicMock

from src.core.metering.tracker import (
    MeteringTracker,
    MeteringRecord,
    MeteringConfig,
    CostClass,
    get_metering_tracker,
)


class TestMeteringRecordsSuccess:
    """Test 1.21: Metering records success."""

    @pytest.fixture
    def tracker(self):
        """Create a fresh metering tracker."""
        return MeteringTracker(
            config=MeteringConfig(
                bill_on="success_only",
                retry_attempts_billed=False,
            )
        )

    def test_record_successful_invocation(self, tracker):
        """Test recording a successful invocation."""
        record = tracker.record(
            tenant_id="tenant-123",
            execution_id="exec-456",
            plugin_id="flyto-official/database",
            step_id="query",
            cost_class="standard",
            base_points=1,
            success=True,
        )

        assert record is not None
        assert record.success is True
        assert record.total_points == 1.0
        assert record.plugin_id == "flyto-official/database"

    def test_cost_class_multipliers(self, tracker):
        """Test cost class multipliers are applied."""
        # Standard = 1x
        record_standard = tracker.record(
            tenant_id="t1",
            execution_id="e1",
            plugin_id="p1",
            step_id="s1",
            cost_class="standard",
            base_points=10,
            success=True,
        )
        assert record_standard.total_points == 10.0

        # Premium = 3x
        record_premium = tracker.record(
            tenant_id="t1",
            execution_id="e2",
            plugin_id="p1",
            step_id="s1",
            cost_class="premium",
            base_points=10,
            success=True,
        )
        assert record_premium.total_points == 30.0

        # Free = 0x
        record_free = tracker.record(
            tenant_id="t1",
            execution_id="e3",
            plugin_id="p1",
            step_id="s1",
            cost_class="free",
            base_points=10,
            success=True,
        )
        assert record_free.total_points == 0.0

    def test_batch_mode_per_item(self, tracker):
        """Test batch mode per_item multiplies by batch size."""
        record = tracker.record(
            tenant_id="t1",
            execution_id="e1",
            plugin_id="p1",
            step_id="s1",
            cost_class="standard",
            base_points=1,
            batch_size=5,
            success=True,
        )

        assert record.total_points == 5.0  # 1 * 1.0 * 5

    def test_on_record_callback(self, tracker):
        """Test on_record callback is called."""
        callback = MagicMock()
        tracker.set_on_record(callback)

        tracker.record(
            tenant_id="t1",
            execution_id="e1",
            plugin_id="p1",
            step_id="s1",
            cost_class="standard",
            base_points=1,
            success=True,
        )

        callback.assert_called_once()


class TestMeteringSkipsFailure:
    """Test 1.22: Metering skips failure."""

    @pytest.fixture
    def tracker(self):
        """Create tracker with success_only billing."""
        return MeteringTracker(
            config=MeteringConfig(
                bill_on="success_only",
                retry_attempts_billed=False,
            )
        )

    def test_skip_failed_invocation(self, tracker):
        """Test that failed invocations are not billed."""
        record = tracker.record(
            tenant_id="tenant-123",
            execution_id="exec-456",
            plugin_id="flyto-official/database",
            step_id="query",
            cost_class="standard",
            base_points=1,
            success=False,  # Failed
        )

        assert record is None  # Not billed

    def test_skip_retry_attempts(self, tracker):
        """Test that retry attempts are not billed."""
        record = tracker.record(
            tenant_id="tenant-123",
            execution_id="exec-456",
            plugin_id="flyto-official/database",
            step_id="query",
            cost_class="standard",
            base_points=1,
            success=True,
            is_retry=True,  # Retry attempt
        )

        assert record is None  # Not billed

    def test_stats_only_count_billed(self, tracker):
        """Test stats only count actually billed records."""
        # Success - billed
        tracker.record(
            tenant_id="t1",
            execution_id="e1",
            plugin_id="p1",
            step_id="s1",
            cost_class="standard",
            base_points=10,
            success=True,
        )

        # Failure - not billed
        tracker.record(
            tenant_id="t1",
            execution_id="e2",
            plugin_id="p1",
            step_id="s1",
            cost_class="standard",
            base_points=10,
            success=False,
        )

        stats = tracker.get_stats()

        assert stats["total_recorded"] == 1
        assert stats["total_points"] == 10.0


class TestMeteringConfig:
    """Test metering configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = MeteringConfig()

        assert config.bill_on == "success_only"
        assert config.retry_attempts_billed is False
        assert config.batch_mode == "per_item"
        assert config.cost_class_multipliers["standard"] == 1.0

    def test_all_except_validation_mode(self):
        """Test all_except_validation billing mode."""
        tracker = MeteringTracker(
            config=MeteringConfig(bill_on="all_except_validation")
        )

        # Even failures should be billed in this mode
        record = tracker.record(
            tenant_id="t1",
            execution_id="e1",
            plugin_id="p1",
            step_id="s1",
            cost_class="standard",
            base_points=1,
            success=False,
        )

        assert record is not None

    def test_per_invoke_batch_mode(self):
        """Test per_invoke batch mode (batch size ignored)."""
        tracker = MeteringTracker(
            config=MeteringConfig(batch_mode="per_invoke")
        )

        record = tracker.record(
            tenant_id="t1",
            execution_id="e1",
            plugin_id="p1",
            step_id="s1",
            cost_class="standard",
            base_points=1,
            batch_size=100,  # Should be ignored
            success=True,
        )

        assert record.total_points == 1.0  # Not 100


class TestMeteringRecord:
    """Test MeteringRecord dataclass."""

    def test_to_dict(self):
        """Test serialization."""
        record = MeteringRecord(
            id="meter-123",
            timestamp=1234567890.0,
            tenant_id="t1",
            execution_id="e1",
            plugin_id="p1",
            step_id="s1",
            cost_class="standard",
            base_points=10,
            multiplier=1.0,
            total_points=10.0,
        )

        data = record.to_dict()

        assert data["id"] == "meter-123"
        assert data["total_points"] == 10.0
        assert data["cost_class"] == "standard"


class TestCostClass:
    """Test CostClass enum."""

    def test_cost_class_values(self):
        """Test cost class enum values."""
        assert CostClass.FREE.value == "free"
        assert CostClass.STANDARD.value == "standard"
        assert CostClass.PREMIUM.value == "premium"
        assert CostClass.ENTERPRISE.value == "enterprise"


class TestFlushAndBuffer:
    """Test buffer and flush functionality."""

    @pytest.fixture
    def tracker(self):
        """Create tracker with small buffer."""
        tracker = MeteringTracker()
        tracker._buffer_max_size = 3
        return tracker

    def test_flush_returns_records(self, tracker):
        """Test flush returns buffered records."""
        tracker.record(
            tenant_id="t1", execution_id="e1", plugin_id="p1",
            step_id="s1", cost_class="standard", base_points=1, success=True,
        )
        tracker.record(
            tenant_id="t1", execution_id="e2", plugin_id="p1",
            step_id="s1", cost_class="standard", base_points=2, success=True,
        )

        records = tracker.flush()

        assert len(records) == 2
        assert tracker._buffer == []  # Buffer cleared

    def test_auto_flush_on_buffer_full(self, tracker):
        """Test auto-flush when buffer is full."""
        callback = MagicMock()
        tracker.set_on_flush(callback)

        # Fill buffer beyond max
        for i in range(4):
            tracker.record(
                tenant_id="t1", execution_id=f"e{i}", plugin_id="p1",
                step_id="s1", cost_class="standard", base_points=1, success=True,
            )

        # Should have triggered flush
        callback.assert_called_once()

    def test_get_tenant_usage(self):
        """Test getting tenant usage summary."""
        # Use a fresh tracker with large buffer to avoid auto-flush
        tracker = MeteringTracker()

        tracker.record(
            tenant_id="tenant-A", execution_id="e1", plugin_id="p1",
            step_id="s1", cost_class="standard", base_points=10, success=True,
        )
        tracker.record(
            tenant_id="tenant-A", execution_id="e2", plugin_id="p2",
            step_id="s2", cost_class="premium", base_points=5, success=True,
        )
        tracker.record(
            tenant_id="tenant-B", execution_id="e3", plugin_id="p1",
            step_id="s1", cost_class="standard", base_points=20, success=True,
        )

        usage = tracker.get_tenant_usage("tenant-A")

        assert usage["tenant_id"] == "tenant-A"
        assert usage["record_count"] == 2
        assert usage["total_points"] == 25.0  # 10 + 5*3
