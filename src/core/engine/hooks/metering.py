# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Usage Metering Hook

Tracks per-workflow and per-step execution metrics for billing/usage tracking.
Gated behind Pro licensing (FeatureFlag.API_ACCESS).

When the license check fails, all methods are no-ops — zero overhead for
unlicensed (FREE tier) users.
"""

import logging
import time
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .base import ExecutorHooks
from .models import HookContext, HookResult
from core.licensing import FeatureFlag, LicenseManager

logger = logging.getLogger(__name__)


# =============================================================================
# Usage Record Model
# =============================================================================

@dataclass
class UsageRecord:
    """
    A single usage record for billing purposes.

    Represents either a completed workflow execution or an individual
    step execution within a workflow.
    """
    record_id: str
    record_type: str  # "workflow" or "step"
    workflow_id: str
    workflow_name: str
    step_id: Optional[str]
    module_id: Optional[str]
    started_at: datetime
    duration_ms: float
    status: str  # "success", "failed"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for export."""
        return {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "step_id": self.step_id,
            "module_id": self.module_id,
            "started_at": self.started_at.isoformat(),
            "duration_ms": self.duration_ms,
            "status": self.status,
            "metadata": self.metadata,
        }


# =============================================================================
# Internal Tracking State
# =============================================================================

@dataclass
class _WorkflowTracker:
    """Internal state for an in-flight workflow."""
    workflow_id: str
    workflow_name: str
    start_time: float  # monotonic clock
    started_at: datetime
    step_count: int = 0


@dataclass
class _StepTracker:
    """Internal state for an in-flight step."""
    step_id: str
    module_id: Optional[str]
    start_time: float  # monotonic clock
    started_at: datetime


# =============================================================================
# Metering Hook
# =============================================================================

class MeteringHook(ExecutorHooks):
    """
    Usage metering hook for billing and usage tracking.

    Collects per-workflow and per-step execution records including
    module_id, duration_ms, step_count, workflow_id, and timestamp.

    Gated behind FeatureFlag.API_ACCESS — when the feature is not
    licensed, all hook methods are no-ops with zero overhead.

    Args:
        on_record: Optional callback invoked for each completed usage
            record. Use this to stream records to an external billing
            system in real time.
        license_manager: Optional LicenseManager instance. Defaults to
            LicenseManager.get_instance().
    """

    def __init__(
        self,
        on_record: Optional[Callable[[UsageRecord], None]] = None,
        license_manager: Optional[LicenseManager] = None,
    ):
        self._on_record = on_record
        self._license_manager = license_manager or LicenseManager.get_instance()

        # Thread-safe storage
        self._lock = threading.Lock()
        self._records: List[UsageRecord] = []

        # In-flight tracking (keyed by workflow_id)
        self._active_workflows: Dict[str, _WorkflowTracker] = {}
        # In-flight step tracking (keyed by workflow_id + step_id)
        self._active_steps: Dict[str, _StepTracker] = {}

    # ------------------------------------------------------------------
    # License gate helper
    # ------------------------------------------------------------------

    def _is_enabled(self) -> bool:
        """Check if metering is enabled via licensing."""
        return self._license_manager.has_feature(FeatureFlag.API_ACCESS)

    # ------------------------------------------------------------------
    # Record management helpers
    # ------------------------------------------------------------------

    def _emit_record(self, record: UsageRecord) -> None:
        """Store a record and invoke the on_record callback."""
        with self._lock:
            self._records.append(record)

        if self._on_record is not None:
            try:
                self._on_record(record)
            except Exception as e:
                logger.warning(
                    "Metering on_record callback failed: %s", e
                )

    @staticmethod
    def _step_key(workflow_id: str, step_id: str) -> str:
        """Create a composite key for step tracking."""
        return workflow_id + "::" + step_id

    # ------------------------------------------------------------------
    # Workflow lifecycle hooks
    # ------------------------------------------------------------------

    def on_workflow_start(self, context: HookContext) -> HookResult:
        """Record workflow start time and increment counter."""
        if not self._is_enabled():
            return HookResult.continue_execution()

        tracker = _WorkflowTracker(
            workflow_id=context.workflow_id,
            workflow_name=context.workflow_name,
            start_time=time.monotonic(),
            started_at=datetime.utcnow(),
        )
        with self._lock:
            self._active_workflows[context.workflow_id] = tracker

        logger.debug(
            "Metering: workflow started %s (%s)",
            context.workflow_id,
            context.workflow_name,
        )
        return HookResult.continue_execution()

    def on_workflow_complete(self, context: HookContext) -> None:
        """Record workflow duration and emit a usage record."""
        if not self._is_enabled():
            return

        with self._lock:
            tracker = self._active_workflows.pop(context.workflow_id, None)

        if tracker is None:
            logger.warning(
                "Metering: on_workflow_complete called without matching start "
                "for workflow %s",
                context.workflow_id,
            )
            return

        duration_ms = (time.monotonic() - tracker.start_time) * 1000.0
        record = UsageRecord(
            record_id=uuid.uuid4().hex,
            record_type="workflow",
            workflow_id=tracker.workflow_id,
            workflow_name=tracker.workflow_name,
            step_id=None,
            module_id=None,
            started_at=tracker.started_at,
            duration_ms=duration_ms,
            status="success",
            metadata={
                "step_count": tracker.step_count,
            },
        )
        self._emit_record(record)

        logger.debug(
            "Metering: workflow completed %s (%.1fms, %d steps)",
            tracker.workflow_id,
            duration_ms,
            tracker.step_count,
        )

    def on_workflow_failed(self, context: HookContext) -> None:
        """Record workflow as failed with error details."""
        if not self._is_enabled():
            return

        with self._lock:
            tracker = self._active_workflows.pop(context.workflow_id, None)

        if tracker is None:
            logger.warning(
                "Metering: on_workflow_failed called without matching start "
                "for workflow %s",
                context.workflow_id,
            )
            return

        duration_ms = (time.monotonic() - tracker.start_time) * 1000.0
        record = UsageRecord(
            record_id=uuid.uuid4().hex,
            record_type="workflow",
            workflow_id=tracker.workflow_id,
            workflow_name=tracker.workflow_name,
            step_id=None,
            module_id=None,
            started_at=tracker.started_at,
            duration_ms=duration_ms,
            status="failed",
            metadata={
                "step_count": tracker.step_count,
                "error_type": context.error_type,
                "error_message": context.error_message,
            },
        )
        self._emit_record(record)

        logger.debug(
            "Metering: workflow failed %s (%.1fms) - %s: %s",
            tracker.workflow_id,
            duration_ms,
            context.error_type,
            context.error_message,
        )

    # ------------------------------------------------------------------
    # Step lifecycle hooks
    # ------------------------------------------------------------------

    def on_pre_execute(self, context: HookContext) -> HookResult:
        """Record step start time."""
        if not self._is_enabled():
            return HookResult.continue_execution()

        step_id = context.step_id or "unknown"
        key = self._step_key(context.workflow_id, step_id)

        step_tracker = _StepTracker(
            step_id=step_id,
            module_id=context.module_id,
            start_time=time.monotonic(),
            started_at=datetime.utcnow(),
        )

        with self._lock:
            self._active_steps[key] = step_tracker
            # Increment the workflow step counter
            wf_tracker = self._active_workflows.get(context.workflow_id)
            if wf_tracker is not None:
                wf_tracker.step_count += 1

        return HookResult.continue_execution()

    def on_post_execute(self, context: HookContext) -> HookResult:
        """Record step duration, module usage, and emit a step record."""
        if not self._is_enabled():
            return HookResult.continue_execution()

        step_id = context.step_id or "unknown"
        key = self._step_key(context.workflow_id, step_id)

        with self._lock:
            step_tracker = self._active_steps.pop(key, None)

        if step_tracker is None:
            logger.warning(
                "Metering: on_post_execute called without matching "
                "on_pre_execute for step %s in workflow %s",
                step_id,
                context.workflow_id,
            )
            return HookResult.continue_execution()

        duration_ms = (time.monotonic() - step_tracker.start_time) * 1000.0
        status = "failed" if context.error else "success"

        step_metadata: Dict[str, Any] = {}
        if context.error:
            step_metadata["error_type"] = context.error_type
            step_metadata["error_message"] = context.error_message
        if context.step_index is not None:
            step_metadata["step_index"] = context.step_index
        if context.total_steps is not None:
            step_metadata["total_steps"] = context.total_steps

        record = UsageRecord(
            record_id=uuid.uuid4().hex,
            record_type="step",
            workflow_id=context.workflow_id,
            workflow_name=context.workflow_name,
            step_id=step_tracker.step_id,
            module_id=step_tracker.module_id,
            started_at=step_tracker.started_at,
            duration_ms=duration_ms,
            status=status,
            metadata=step_metadata,
        )
        self._emit_record(record)

        return HookResult.continue_execution()

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def get_usage_records(self) -> List[UsageRecord]:
        """
        Return a copy of all collected usage records.

        Returns:
            List of UsageRecord instances.
        """
        with self._lock:
            return list(self._records)

    def get_summary(self) -> Dict[str, Any]:
        """
        Return an aggregate summary of usage.

        Returns:
            Dictionary with keys:
            - total_workflows: int
            - total_steps: int
            - total_duration_ms: float
            - workflows_succeeded: int
            - workflows_failed: int
            - steps_succeeded: int
            - steps_failed: int
            - module_breakdown: Dict[str, {count, total_duration_ms}]
        """
        with self._lock:
            records = list(self._records)

        total_workflows = 0
        total_steps = 0
        total_duration_ms = 0.0
        workflows_succeeded = 0
        workflows_failed = 0
        steps_succeeded = 0
        steps_failed = 0
        module_breakdown: Dict[str, Dict[str, Any]] = {}

        for record in records:
            total_duration_ms += record.duration_ms

            if record.record_type == "workflow":
                total_workflows += 1
                if record.status == "success":
                    workflows_succeeded += 1
                else:
                    workflows_failed += 1

            elif record.record_type == "step":
                total_steps += 1
                if record.status == "success":
                    steps_succeeded += 1
                else:
                    steps_failed += 1

                # Module breakdown
                mod_id = record.module_id or "unknown"
                if mod_id not in module_breakdown:
                    module_breakdown[mod_id] = {
                        "count": 0,
                        "total_duration_ms": 0.0,
                        "success": 0,
                        "failed": 0,
                    }
                entry = module_breakdown[mod_id]
                entry["count"] += 1
                entry["total_duration_ms"] += record.duration_ms
                if record.status == "success":
                    entry["success"] += 1
                else:
                    entry["failed"] += 1

        return {
            "total_workflows": total_workflows,
            "total_steps": total_steps,
            "total_duration_ms": total_duration_ms,
            "workflows_succeeded": workflows_succeeded,
            "workflows_failed": workflows_failed,
            "steps_succeeded": steps_succeeded,
            "steps_failed": steps_failed,
            "module_breakdown": module_breakdown,
        }

    def flush(self) -> List[UsageRecord]:
        """
        Clear all usage records and return them.

        Useful for periodic export to a billing system. Returns the
        records that were flushed so the caller can process them.

        Returns:
            List of flushed UsageRecord instances.
        """
        with self._lock:
            flushed = self._records
            self._records = []
        return flushed
