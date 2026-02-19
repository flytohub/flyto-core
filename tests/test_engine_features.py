# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Comprehensive tests for the 6 new engine features:

1. MeteringHook        — usage metering per workflow/step
2. TimeoutGuard        — execution timeout protection
3. ExecutionQueueManager — priority-based execution queue
4. WorkflowVersionManager — workflow versioning, diff, rollback
5. WebhookTriggerManager — webhook trigger registration & verification
6. CronTriggerManager  — cron-based scheduled triggers
"""

import asyncio
import hashlib
import hmac
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Set
from unittest.mock import MagicMock, patch

import pytest

from core.licensing import FeatureFlag, LicenseError, LicenseManager


# =============================================================================
# Fixtures: License mocking
# =============================================================================


class _AllFeaturesChecker:
    """A fake LicenseChecker that grants all features."""

    def get_tier(self):
        from core.licensing import LicenseTier
        return LicenseTier.ENTERPRISE

    def has_feature(self, feature: FeatureFlag) -> bool:
        return True

    def can_access_module(self, module_id: str) -> bool:
        return True

    def get_module_access_info(self, module_id: str) -> Dict[str, Any]:
        return {"accessible": True}


class _NoFeaturesChecker:
    """A fake LicenseChecker that denies all non-FREE features."""

    def get_tier(self):
        from core.licensing import LicenseTier
        return LicenseTier.FREE

    def has_feature(self, feature: FeatureFlag) -> bool:
        return feature in {
            FeatureFlag.BASIC_WORKFLOW,
            FeatureFlag.BASIC_MODULES,
            FeatureFlag.LOCAL_EXECUTION,
        }

    def can_access_module(self, module_id: str) -> bool:
        return True

    def get_module_access_info(self, module_id: str) -> Dict[str, Any]:
        return {"accessible": True}


@pytest.fixture(autouse=True)
def _enable_all_features():
    """Register an all-features license checker for every test, then clean up."""
    original = LicenseManager._checker
    LicenseManager.register_checker(_AllFeaturesChecker())
    yield
    LicenseManager._checker = original


@pytest.fixture()
def disable_all_features():
    """Switch to a no-features checker for a single test."""
    original = LicenseManager._checker
    LicenseManager.register_checker(_NoFeaturesChecker())
    yield
    LicenseManager._checker = original


# =============================================================================
# Imports (after fixture defs so they are available)
# =============================================================================

from core.engine.hooks.metering import MeteringHook, UsageRecord
from core.engine.hooks.models import HookAction, HookContext, HookResult
from core.engine.guards.timeout import (
    ExecutionTimeoutError,
    TimeoutGuard,
    TimeoutHooks,
)
from core.engine.queue.manager import (
    ExecutionQueueManager,
    QueueItem,
    QueuePriority,
)
from core.engine.versioning.manager import (
    VersionDiff,
    WorkflowVersion,
    WorkflowVersionManager,
)
from core.engine.triggers.webhook import WebhookConfig, WebhookTriggerManager
from core.engine.triggers.cron import CronConfig, CronTriggerManager
from core.engine.triggers.base import TriggerStatus


# =============================================================================
# Helpers
# =============================================================================


def _make_hook_context(
    workflow_id: str = "wf-1",
    workflow_name: str = "Test Workflow",
    step_id: str = None,
    module_id: str = None,
    error: Exception = None,
    error_type: str = None,
    error_message: str = None,
    step_index: int = None,
    total_steps: int = None,
    metadata: Dict[str, Any] = None,
) -> HookContext:
    ctx = HookContext(
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        step_id=step_id,
        module_id=module_id,
        error=error,
        error_type=error_type,
        error_message=error_message,
        step_index=step_index,
        total_steps=total_steps,
        metadata=metadata or {},
    )
    return ctx


# =========================================================================
# 1. MeteringHook Tests
# =========================================================================


class TestMeteringHook:
    """Tests for core.engine.hooks.metering.MeteringHook."""

    # --- workflow start / complete / failed create UsageRecords ----------

    def test_workflow_start_complete_creates_usage_record(self):
        hook = MeteringHook()
        ctx = _make_hook_context()

        hook.on_workflow_start(ctx)
        # Allow a tiny amount of time to pass so duration_ms > 0
        hook.on_workflow_complete(ctx)

        records = hook.get_usage_records()
        assert len(records) == 1

        rec = records[0]
        assert rec.record_type == "workflow"
        assert rec.workflow_id == "wf-1"
        assert rec.workflow_name == "Test Workflow"
        assert rec.status == "success"
        assert rec.duration_ms >= 0
        assert rec.step_id is None
        assert rec.module_id is None

    def test_workflow_start_failed_creates_failed_record(self):
        hook = MeteringHook()
        ctx_start = _make_hook_context()
        ctx_fail = _make_hook_context(
            error_type="RuntimeError",
            error_message="something broke",
        )

        hook.on_workflow_start(ctx_start)
        hook.on_workflow_failed(ctx_fail)

        records = hook.get_usage_records()
        assert len(records) == 1

        rec = records[0]
        assert rec.record_type == "workflow"
        assert rec.status == "failed"
        assert rec.metadata["error_type"] == "RuntimeError"
        assert rec.metadata["error_message"] == "something broke"

    # --- on_pre_execute / on_post_execute create step records ------------

    def test_pre_post_execute_creates_step_record(self):
        hook = MeteringHook()

        # Start workflow so step counter works
        ctx_wf = _make_hook_context()
        hook.on_workflow_start(ctx_wf)

        ctx_step = _make_hook_context(
            step_id="step-1",
            module_id="mod-http",
            step_index=0,
            total_steps=3,
        )
        result_pre = hook.on_pre_execute(ctx_step)
        assert result_pre.action == HookAction.CONTINUE

        result_post = hook.on_post_execute(ctx_step)
        assert result_post.action == HookAction.CONTINUE

        records = hook.get_usage_records()
        step_records = [r for r in records if r.record_type == "step"]
        assert len(step_records) == 1

        rec = step_records[0]
        assert rec.step_id == "step-1"
        assert rec.module_id == "mod-http"
        assert rec.status == "success"
        assert rec.duration_ms >= 0
        assert rec.metadata.get("step_index") == 0
        assert rec.metadata.get("total_steps") == 3

    def test_pre_post_execute_with_error_creates_failed_step(self):
        hook = MeteringHook()
        ctx_wf = _make_hook_context()
        hook.on_workflow_start(ctx_wf)

        ctx_step = _make_hook_context(
            step_id="step-err",
            module_id="mod-file",
            error=RuntimeError("fail"),
            error_type="RuntimeError",
            error_message="fail",
        )
        hook.on_pre_execute(ctx_step)
        hook.on_post_execute(ctx_step)

        records = hook.get_usage_records()
        step_records = [r for r in records if r.record_type == "step"]
        assert len(step_records) == 1
        assert step_records[0].status == "failed"
        assert step_records[0].metadata["error_type"] == "RuntimeError"

    # --- get_summary() returns correct aggregates -----------------------

    def test_get_summary_returns_correct_aggregates(self):
        hook = MeteringHook()

        # Successful workflow with 2 steps
        ctx = _make_hook_context(workflow_id="wf-a")
        hook.on_workflow_start(ctx)

        for i in range(2):
            step_ctx = _make_hook_context(
                workflow_id="wf-a",
                step_id="step-{}".format(i),
                module_id="mod-a",
            )
            hook.on_pre_execute(step_ctx)
            hook.on_post_execute(step_ctx)

        hook.on_workflow_complete(ctx)

        # Failed workflow with 1 step
        ctx_b = _make_hook_context(workflow_id="wf-b")
        hook.on_workflow_start(ctx_b)

        step_ctx_b = _make_hook_context(
            workflow_id="wf-b",
            step_id="step-0",
            module_id="mod-b",
            error=RuntimeError("x"),
            error_type="RuntimeError",
            error_message="x",
        )
        hook.on_pre_execute(step_ctx_b)
        hook.on_post_execute(step_ctx_b)
        hook.on_workflow_failed(
            _make_hook_context(
                workflow_id="wf-b",
                error_type="RuntimeError",
                error_message="x",
            )
        )

        summary = hook.get_summary()
        assert summary["total_workflows"] == 2
        assert summary["total_steps"] == 3
        assert summary["workflows_succeeded"] == 1
        assert summary["workflows_failed"] == 1
        assert summary["steps_succeeded"] == 2
        assert summary["steps_failed"] == 1
        assert summary["total_duration_ms"] >= 0

        # Module breakdown
        assert "mod-a" in summary["module_breakdown"]
        assert summary["module_breakdown"]["mod-a"]["count"] == 2
        assert "mod-b" in summary["module_breakdown"]
        assert summary["module_breakdown"]["mod-b"]["count"] == 1
        assert summary["module_breakdown"]["mod-b"]["failed"] == 1

    # --- flush() clears and returns records -----------------------------

    def test_flush_clears_and_returns_records(self):
        hook = MeteringHook()

        ctx = _make_hook_context()
        hook.on_workflow_start(ctx)
        hook.on_workflow_complete(ctx)

        assert len(hook.get_usage_records()) == 1

        flushed = hook.flush()
        assert len(flushed) == 1
        assert flushed[0].record_type == "workflow"

        # After flush, no records remain
        assert len(hook.get_usage_records()) == 0

    # --- on_record callback is called -----------------------------------

    def test_on_record_callback_is_called(self):
        callback_records = []
        hook = MeteringHook(on_record=lambda rec: callback_records.append(rec))

        ctx = _make_hook_context()
        hook.on_workflow_start(ctx)
        hook.on_workflow_complete(ctx)

        assert len(callback_records) == 1
        assert isinstance(callback_records[0], UsageRecord)
        assert callback_records[0].record_type == "workflow"

    # --- Feature-gated no-ops -------------------------------------------

    def test_disabled_feature_hooks_are_noops(self, disable_all_features):
        hook = MeteringHook()

        ctx = _make_hook_context()
        result = hook.on_workflow_start(ctx)
        assert result.action == HookAction.CONTINUE

        hook.on_workflow_complete(ctx)
        hook.on_workflow_failed(ctx)

        pre = hook.on_pre_execute(ctx)
        assert pre.action == HookAction.CONTINUE
        post = hook.on_post_execute(ctx)
        assert post.action == HookAction.CONTINUE

        # No records should have been created
        assert len(hook.get_usage_records()) == 0

    # --- UsageRecord.to_dict() works ------------------------------------

    def test_usage_record_to_dict(self):
        hook = MeteringHook()
        ctx = _make_hook_context()
        hook.on_workflow_start(ctx)
        hook.on_workflow_complete(ctx)

        rec = hook.get_usage_records()[0]
        d = rec.to_dict()
        assert d["record_type"] == "workflow"
        assert "record_id" in d
        assert "started_at" in d
        assert isinstance(d["started_at"], str)


# =========================================================================
# 2. TimeoutGuard Tests
# =========================================================================


class TestTimeoutGuard:
    """Tests for core.engine.guards.timeout.TimeoutGuard."""

    # --- execute_with_timeout: fast coroutine succeeds ------------------

    async def test_execute_with_timeout_fast_coro_succeeds(self):
        guard = TimeoutGuard(step_timeout_ms=5000)

        async def fast():
            return 42

        result = await guard.execute_with_timeout(fast(), label="fast-op")
        assert result == 42

    # --- execute_with_timeout: slow coroutine raises --------------------

    async def test_execute_with_timeout_slow_coro_raises(self):
        guard = TimeoutGuard(step_timeout_ms=50)

        async def slow():
            await asyncio.sleep(10)
            return "never"

        with pytest.raises(ExecutionTimeoutError) as exc_info:
            await guard.execute_with_timeout(
                slow(), timeout_ms=50, label="slow-op"
            )
        assert exc_info.value.timeout_ms == 50
        assert exc_info.value.label == "slow-op"

    # --- guard_workflow succeeds for fast coro ---------------------------

    async def test_guard_workflow_succeeds(self):
        guard = TimeoutGuard(workflow_timeout_ms=5000)

        async def fast_workflow():
            return "done"

        result = await guard.guard_workflow(fast_workflow(), workflow_id="wf-1")
        assert result == "done"

    # --- guard_workflow raises for slow coro -----------------------------

    async def test_guard_workflow_raises_for_slow(self):
        guard = TimeoutGuard(workflow_timeout_ms=50)

        async def slow_workflow():
            await asyncio.sleep(10)

        with pytest.raises(ExecutionTimeoutError) as exc_info:
            await guard.guard_workflow(slow_workflow(), workflow_id="wf-slow")
        assert exc_info.value.workflow_id == "wf-slow"
        assert exc_info.value.timeout_ms == 50

    # --- guard_step succeeds / raises -----------------------------------

    async def test_guard_step_succeeds(self):
        guard = TimeoutGuard(step_timeout_ms=5000)

        async def fast_step():
            return {"key": "value"}

        result = await guard.guard_step(
            fast_step(), step_id="s1", module_id="mod-http"
        )
        assert result == {"key": "value"}

    async def test_guard_step_raises_for_slow(self):
        guard = TimeoutGuard(step_timeout_ms=50)

        async def slow_step():
            await asyncio.sleep(10)

        with pytest.raises(ExecutionTimeoutError) as exc_info:
            await guard.guard_step(
                slow_step(), step_id="s1", module_id="mod-http"
            )
        assert exc_info.value.step_id == "s1"

    # --- TimeoutHooks.on_pre_execute aborts when budget exceeded ---------

    def test_timeout_hooks_abort_when_budget_exceeded(self):
        guard = TimeoutGuard(workflow_timeout_ms=1)  # 1ms budget
        hooks = TimeoutHooks(guard)

        ctx = _make_hook_context()
        hooks.on_workflow_start(ctx)

        # Wait just enough for the 1ms budget to expire
        time.sleep(0.01)

        result = hooks.on_pre_execute(ctx)
        assert result.action == HookAction.ABORT
        assert "exceeded time budget" in result.abort_reason

    def test_timeout_hooks_continue_within_budget(self):
        guard = TimeoutGuard(workflow_timeout_ms=60_000)  # 60s budget
        hooks = TimeoutHooks(guard)

        ctx = _make_hook_context()
        hooks.on_workflow_start(ctx)

        result = hooks.on_pre_execute(ctx)
        assert result.action == HookAction.CONTINUE

    # --- on_timeout_callback is called ----------------------------------

    async def test_on_timeout_callback_is_called(self):
        errors = []
        guard = TimeoutGuard(
            step_timeout_ms=50,
            on_timeout_callback=lambda e: errors.append(e),
        )

        async def slow():
            await asyncio.sleep(10)

        with pytest.raises(ExecutionTimeoutError):
            await guard.execute_with_timeout(slow(), timeout_ms=50)

        assert len(errors) == 1
        assert isinstance(errors[0], ExecutionTimeoutError)

    def test_on_timeout_callback_called_from_hooks(self):
        errors = []
        guard = TimeoutGuard(
            workflow_timeout_ms=1,
            on_timeout_callback=lambda e: errors.append(e),
        )
        hooks = TimeoutHooks(guard)

        ctx = _make_hook_context()
        hooks.on_workflow_start(ctx)
        time.sleep(0.01)
        hooks.on_pre_execute(ctx)

        assert len(errors) == 1
        assert isinstance(errors[0], ExecutionTimeoutError)

    # --- ExecutionTimeoutError.to_dict() --------------------------------

    def test_execution_timeout_error_to_dict(self):
        err = ExecutionTimeoutError(
            message="Timed out",
            timeout_ms=5000,
            label="test",
            workflow_id="wf-1",
            step_id="s-1",
        )
        d = err.to_dict()
        assert d["timeout_ms"] == 5000
        assert d["label"] == "test"
        assert d["workflow_id"] == "wf-1"
        assert d["step_id"] == "s-1"

    # --- Cleanup in hooks -----------------------------------------------

    def test_timeout_hooks_cleanup_on_complete(self):
        guard = TimeoutGuard()
        hooks = TimeoutHooks(guard)

        ctx = _make_hook_context()
        hooks.on_workflow_start(ctx)
        assert "wf-1" in hooks._workflow_start_times

        hooks.on_workflow_complete(ctx)
        assert "wf-1" not in hooks._workflow_start_times

    def test_timeout_hooks_cleanup_on_failed(self):
        guard = TimeoutGuard()
        hooks = TimeoutHooks(guard)

        ctx = _make_hook_context()
        hooks.on_workflow_start(ctx)
        hooks.on_workflow_failed(ctx)
        assert "wf-1" not in hooks._workflow_start_times


# =========================================================================
# 3. ExecutionQueueManager Tests
# =========================================================================


class TestExecutionQueueManager:
    """Tests for core.engine.queue.manager.ExecutionQueueManager."""

    # --- enqueue creates QueueItem --------------------------------------

    def test_enqueue_creates_queue_item(self):
        mgr = ExecutionQueueManager(max_concurrent=5)
        item = mgr.enqueue(
            workflow_id="wf-1",
            workflow_name="My Workflow",
            params={"key": "val"},
        )
        assert isinstance(item, QueueItem)
        assert item.workflow_id == "wf-1"
        assert item.workflow_name == "My Workflow"
        assert item.status == "pending"
        assert item.params == {"key": "val"}
        assert item.priority == QueuePriority.NORMAL

    def test_enqueue_with_priority(self):
        mgr = ExecutionQueueManager(max_concurrent=5)
        item = mgr.enqueue(
            workflow_id="wf-1",
            workflow_name="Urgent",
            priority=QueuePriority.CRITICAL,
        )
        assert item.priority == QueuePriority.CRITICAL

    # --- priority ordering (CRITICAL before NORMAL) ---------------------

    def test_priority_ordering_critical_before_normal(self):
        mgr = ExecutionQueueManager(max_concurrent=5)

        normal = mgr.enqueue(
            workflow_id="wf-normal",
            workflow_name="Normal Task",
            priority=QueuePriority.NORMAL,
        )
        critical = mgr.enqueue(
            workflow_id="wf-critical",
            workflow_name="Critical Task",
            priority=QueuePriority.CRITICAL,
        )
        low = mgr.enqueue(
            workflow_id="wf-low",
            workflow_name="Low Task",
            priority=QueuePriority.LOW,
        )

        queue = mgr.get_queue()
        assert queue[0].item_id == critical.item_id
        assert queue[1].item_id == normal.item_id
        assert queue[2].item_id == low.item_id

    # --- cancel changes status ------------------------------------------

    def test_cancel_changes_status(self):
        mgr = ExecutionQueueManager(max_concurrent=5)
        item = mgr.enqueue(
            workflow_id="wf-1",
            workflow_name="Cancel Me",
        )
        assert item.status == "pending"

        result = mgr.cancel(item.item_id)
        assert result is True

        status = mgr.get_status(item.item_id)
        assert status.status == "cancelled"

    def test_cancel_nonexistent_returns_false(self):
        mgr = ExecutionQueueManager(max_concurrent=5)
        assert mgr.cancel("nonexistent-id") is False

    def test_cancel_non_pending_returns_false(self):
        mgr = ExecutionQueueManager(max_concurrent=5)
        item = mgr.enqueue(
            workflow_id="wf-1",
            workflow_name="Task",
        )
        # Cancel once
        mgr.cancel(item.item_id)
        # Try to cancel again (already cancelled)
        assert mgr.cancel(item.item_id) is False

    # --- get_stats returns correct counts -------------------------------

    def test_get_stats_returns_correct_counts(self):
        mgr = ExecutionQueueManager(max_concurrent=5)

        mgr.enqueue(workflow_id="wf-1", workflow_name="A")
        mgr.enqueue(workflow_id="wf-2", workflow_name="B")
        item_c = mgr.enqueue(workflow_id="wf-3", workflow_name="C")
        mgr.cancel(item_c.item_id)

        stats = mgr.get_stats()
        assert stats["pending"] == 2
        assert stats["running"] == 0
        assert stats["completed"] == 0
        assert stats["failed"] == 0
        assert stats["max_concurrent"] == 5

    # --- get_queue returns sorted items ---------------------------------

    def test_get_queue_returns_sorted_items(self):
        mgr = ExecutionQueueManager(max_concurrent=5)

        a = mgr.enqueue(
            workflow_id="wf-a",
            workflow_name="A",
            priority=QueuePriority.LOW,
        )
        b = mgr.enqueue(
            workflow_id="wf-b",
            workflow_name="B",
            priority=QueuePriority.HIGH,
        )
        c = mgr.enqueue(
            workflow_id="wf-c",
            workflow_name="C",
            priority=QueuePriority.NORMAL,
        )

        queue = mgr.get_queue()
        ids = [item.item_id for item in queue]
        assert ids == [b.item_id, c.item_id, a.item_id]

    # --- LicenseError when feature disabled -----------------------------

    def test_queue_raises_license_error_when_disabled(self, disable_all_features):
        with pytest.raises(LicenseError):
            ExecutionQueueManager(max_concurrent=5)

    # --- get_status for unknown item returns None -----------------------

    def test_get_status_unknown_returns_none(self):
        mgr = ExecutionQueueManager(max_concurrent=5)
        assert mgr.get_status("no-such-id") is None


# =========================================================================
# 4. WorkflowVersionManager Tests
# =========================================================================


class TestWorkflowVersionManager:
    """Tests for core.engine.versioning.manager.WorkflowVersionManager."""

    def _sample_definition(self, steps=None):
        if steps is None:
            steps = [
                {"id": "s1", "module": "http_get", "url": "https://example.com"},
                {"id": "s2", "module": "json_parse", "path": "$.data"},
            ]
        return {"steps": steps, "name": "sample"}

    # --- save_version creates a version ---------------------------------

    def test_save_version_creates_version(self):
        mgr = WorkflowVersionManager()
        ver = mgr.save_version(
            workflow_id="wf-1",
            name="Initial",
            definition=self._sample_definition(),
            version="1.0.0",
            created_by="tester",
        )
        assert isinstance(ver, WorkflowVersion)
        assert ver.workflow_id == "wf-1"
        assert ver.version == "1.0.0"
        assert ver.name == "Initial"
        assert ver.is_published is False
        assert ver.parent_version is None

    def test_save_version_links_parent(self):
        mgr = WorkflowVersionManager()
        v1 = mgr.save_version(
            workflow_id="wf-1",
            name="V1",
            definition=self._sample_definition(),
            version="1.0.0",
        )
        v2 = mgr.save_version(
            workflow_id="wf-1",
            name="V2",
            definition=self._sample_definition(),
            version="1.1.0",
        )
        assert v2.parent_version == v1.version_id

    # --- get_latest returns most recent ---------------------------------

    def test_get_latest_returns_most_recent(self):
        mgr = WorkflowVersionManager()
        mgr.save_version(
            workflow_id="wf-1",
            name="V1",
            definition=self._sample_definition(),
            version="1.0.0",
        )
        v2 = mgr.save_version(
            workflow_id="wf-1",
            name="V2",
            definition=self._sample_definition(),
            version="1.1.0",
        )
        latest = mgr.get_latest("wf-1")
        assert latest.version_id == v2.version_id
        assert latest.version == "1.1.0"

    def test_get_latest_nonexistent_returns_none(self):
        mgr = WorkflowVersionManager()
        assert mgr.get_latest("no-such-wf") is None

    # --- list_versions returns sorted list (newest first) ---------------

    def test_list_versions_sorted_newest_first(self):
        mgr = WorkflowVersionManager()
        v1 = mgr.save_version(
            workflow_id="wf-1",
            name="V1",
            definition=self._sample_definition(),
            version="1.0.0",
        )
        v2 = mgr.save_version(
            workflow_id="wf-1",
            name="V2",
            definition=self._sample_definition(),
            version="1.1.0",
        )
        v3 = mgr.save_version(
            workflow_id="wf-1",
            name="V3",
            definition=self._sample_definition(),
            version="2.0.0",
        )

        versions = mgr.list_versions("wf-1")
        assert len(versions) == 3
        assert versions[0].version_id == v3.version_id
        assert versions[1].version_id == v2.version_id
        assert versions[2].version_id == v1.version_id

    # --- diff detects added/removed/modified steps ----------------------

    def test_diff_detects_changes(self):
        mgr = WorkflowVersionManager()

        def_a = {
            "steps": [
                {"id": "s1", "module": "http_get", "url": "https://a.com"},
                {"id": "s2", "module": "json_parse", "path": "$.data"},
                {"id": "s3", "module": "log", "msg": "done"},
            ]
        }
        def_b = {
            "steps": [
                {"id": "s1", "module": "http_get", "url": "https://b.com"},  # modified
                # s2 removed
                {"id": "s3", "module": "log", "msg": "done"},  # unchanged
                {"id": "s4", "module": "email", "to": "a@b.com"},  # added
            ]
        }

        v1 = mgr.save_version(
            workflow_id="wf-1",
            name="V1",
            definition=def_a,
            version="1.0.0",
        )
        v2 = mgr.save_version(
            workflow_id="wf-1",
            name="V2",
            definition=def_b,
            version="1.1.0",
        )

        diff = mgr.diff(v1.version_id, v2.version_id)
        assert isinstance(diff, VersionDiff)
        assert "s4" in diff.steps_added
        assert "s2" in diff.steps_removed
        assert "s1" in diff.steps_modified
        assert "s3" not in diff.steps_modified

        # params_changed for s1
        assert "s1" in diff.params_changed
        assert diff.params_changed["s1"]["url"]["old"] == "https://a.com"
        assert diff.params_changed["s1"]["url"]["new"] == "https://b.com"

        assert "added" in diff.summary
        assert "removed" in diff.summary
        assert "modified" in diff.summary

    def test_diff_no_changes(self):
        mgr = WorkflowVersionManager()
        defn = self._sample_definition()
        v1 = mgr.save_version(
            workflow_id="wf-1",
            name="V1",
            definition=defn,
            version="1.0.0",
        )
        v2 = mgr.save_version(
            workflow_id="wf-1",
            name="V2",
            definition=defn,
            version="1.0.1",
        )
        diff = mgr.diff(v1.version_id, v2.version_id)
        assert diff.summary == "No changes"
        assert diff.steps_added == []
        assert diff.steps_removed == []
        assert diff.steps_modified == []

    # --- rollback creates new version from old --------------------------

    def test_rollback_creates_new_version_from_old(self):
        mgr = WorkflowVersionManager()

        def_v1 = self._sample_definition([
            {"id": "s1", "module": "http_get"},
        ])
        def_v2 = self._sample_definition([
            {"id": "s1", "module": "http_get"},
            {"id": "s2", "module": "email"},
        ])

        v1 = mgr.save_version(
            workflow_id="wf-1",
            name="V1",
            definition=def_v1,
            version="1.0.0",
            created_by="alice",
        )
        v2 = mgr.save_version(
            workflow_id="wf-1",
            name="V2",
            definition=def_v2,
            version="1.1.0",
        )

        rolled_back = mgr.rollback("wf-1", v1.version_id)

        assert rolled_back.version == "1.1.1"  # patch bump from 1.1.0
        assert rolled_back.definition == def_v1
        assert rolled_back.parent_version == v2.version_id
        assert "Rollback" in rolled_back.description

        # New version should be the latest
        latest = mgr.get_latest("wf-1")
        assert latest.version_id == rolled_back.version_id

    # --- publish marks version ------------------------------------------

    def test_publish_marks_version(self):
        mgr = WorkflowVersionManager()
        ver = mgr.save_version(
            workflow_id="wf-1",
            name="V1",
            definition=self._sample_definition(),
            version="1.0.0",
        )
        assert ver.is_published is False

        published = mgr.publish(ver.version_id)
        assert published.is_published is True
        assert published.version_id == ver.version_id

    # --- delete_version won't delete published --------------------------

    def test_delete_version_wont_delete_published(self):
        mgr = WorkflowVersionManager()
        ver = mgr.save_version(
            workflow_id="wf-1",
            name="V1",
            definition=self._sample_definition(),
            version="1.0.0",
        )
        mgr.publish(ver.version_id)

        with pytest.raises(ValueError, match="Cannot delete published"):
            mgr.delete_version(ver.version_id)

    def test_delete_version_succeeds_for_unpublished(self):
        mgr = WorkflowVersionManager()
        ver = mgr.save_version(
            workflow_id="wf-1",
            name="V1",
            definition=self._sample_definition(),
            version="1.0.0",
        )
        result = mgr.delete_version(ver.version_id)
        assert result is True
        assert mgr.get_version(ver.version_id) is None

    def test_delete_nonexistent_returns_false(self):
        mgr = WorkflowVersionManager()
        assert mgr.delete_version("no-such-id") is False

    # --- LicenseError when feature disabled -----------------------------

    def test_versioning_raises_license_error_when_disabled(self, disable_all_features):
        mgr = WorkflowVersionManager()  # __init__ has no gate
        with pytest.raises(LicenseError):
            mgr.save_version(
                workflow_id="wf-1",
                name="V1",
                definition={},
            )


# =========================================================================
# 5. WebhookTriggerManager Tests
# =========================================================================


class TestWebhookTriggerManager:
    """Tests for core.engine.triggers.webhook.WebhookTriggerManager."""

    # --- register_webhook creates config --------------------------------

    def test_register_webhook_creates_config(self):
        mgr = WebhookTriggerManager()
        cfg = mgr.register_webhook(
            workflow_id="wf-1",
            name="GitHub Push",
            secret="my-secret",
            allowed_methods=["POST"],
            payload_mapping={"repo": "repository.full_name"},
        )
        assert isinstance(cfg, WebhookConfig)
        assert cfg.workflow_id == "wf-1"
        assert cfg.name == "GitHub Push"
        assert cfg.secret == "my-secret"
        assert cfg.allowed_methods == ["POST"]
        assert cfg.payload_mapping == {"repo": "repository.full_name"}
        assert cfg.status == TriggerStatus.ACTIVE

    # --- verify_signature with valid HMAC -------------------------------

    def test_verify_signature_valid(self):
        mgr = WebhookTriggerManager()
        secret = "test-secret-key"
        cfg = mgr.register_webhook(
            workflow_id="wf-1",
            name="Signed Hook",
            secret=secret,
        )

        payload = b'{"event": "push"}'
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        assert mgr.verify_signature(cfg.trigger_id, payload, expected_sig) is True

    def test_verify_signature_with_sha256_prefix(self):
        mgr = WebhookTriggerManager()
        secret = "my-secret"
        cfg = mgr.register_webhook(
            workflow_id="wf-1",
            name="GitHub Style",
            secret=secret,
        )

        payload = b'{"ref": "main"}'
        raw_sig = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # GitHub-style prefix
        prefixed = "sha256=" + raw_sig
        assert mgr.verify_signature(cfg.trigger_id, payload, prefixed) is True

    # --- verify_signature with invalid HMAC -----------------------------

    def test_verify_signature_invalid(self):
        mgr = WebhookTriggerManager()
        cfg = mgr.register_webhook(
            workflow_id="wf-1",
            name="Bad Sig",
            secret="correct-secret",
        )

        payload = b'{"event": "push"}'
        assert mgr.verify_signature(cfg.trigger_id, payload, "invalid-sig") is False

    def test_verify_signature_no_secret_always_passes(self):
        mgr = WebhookTriggerManager()
        cfg = mgr.register_webhook(
            workflow_id="wf-1",
            name="No Secret",
            secret="",
        )
        assert mgr.verify_signature(cfg.trigger_id, b"anything", "anything") is True

    def test_verify_signature_unknown_trigger(self):
        mgr = WebhookTriggerManager()
        assert mgr.verify_signature("no-such-id", b"data", "sig") is False

    # --- process_webhook with valid request -----------------------------

    def test_process_webhook_valid_request(self):
        mgr = WebhookTriggerManager()
        cfg = mgr.register_webhook(
            workflow_id="wf-deploy",
            name="Deploy Hook",
            allowed_methods=["POST"],
            payload_mapping={"branch": "ref"},
        )

        event = mgr.process_webhook(
            trigger_id=cfg.trigger_id,
            method="POST",
            headers={"Content-Type": "application/json"},
            payload={"ref": "main", "commits": []},
        )
        assert event is not None
        assert event.workflow_id == "wf-deploy"
        assert event.payload == {"branch": "main"}
        assert event.metadata["method"] == "POST"

    # --- process_webhook rejects wrong method ---------------------------

    def test_process_webhook_rejects_wrong_method(self):
        mgr = WebhookTriggerManager()
        cfg = mgr.register_webhook(
            workflow_id="wf-1",
            name="POST Only",
            allowed_methods=["POST"],
        )
        event = mgr.process_webhook(
            trigger_id=cfg.trigger_id,
            method="GET",
            headers={},
            payload={},
        )
        assert event is None

    def test_process_webhook_rejects_inactive_trigger(self):
        mgr = WebhookTriggerManager()
        cfg = mgr.register_webhook(
            workflow_id="wf-1",
            name="Paused",
        )
        mgr.pause(cfg.trigger_id)

        event = mgr.process_webhook(
            trigger_id=cfg.trigger_id,
            method="POST",
            headers={},
            payload={},
        )
        assert event is None

    def test_process_webhook_rejects_missing_trigger(self):
        mgr = WebhookTriggerManager()
        event = mgr.process_webhook(
            trigger_id="no-such-id",
            method="POST",
            headers={},
            payload={},
        )
        assert event is None

    # --- map_payload maps nested fields ---------------------------------

    def test_map_payload_maps_nested_fields(self):
        cfg = WebhookConfig(
            trigger_id="t1",
            trigger_type="webhook",
            workflow_id="wf-1",
            name="Test",
            payload_mapping={
                "repo": "repository.full_name",
                "branch": "ref",
                "author": "commits.0.author.name",  # won't resolve (list)
            },
        )
        payload = {
            "repository": {"full_name": "org/repo"},
            "ref": "main",
            "commits": [{"author": {"name": "alice"}}],
        }
        result = WebhookTriggerManager.map_payload(cfg, payload)
        assert result["repo"] == "org/repo"
        assert result["branch"] == "main"
        # "commits.0.author.name" won't traverse into list items (not dicts)
        assert "author" not in result

    def test_map_payload_no_mapping_returns_full_payload(self):
        cfg = WebhookConfig(
            trigger_id="t1",
            trigger_type="webhook",
            workflow_id="wf-1",
            name="Test",
            payload_mapping={},
        )
        payload = {"key": "value"}
        result = WebhookTriggerManager.map_payload(cfg, payload)
        assert result == {"key": "value"}

    # --- LicenseError ---------------------------------------------------

    def test_webhook_raises_license_error_when_disabled(self, disable_all_features):
        with pytest.raises(LicenseError):
            WebhookTriggerManager()


# =========================================================================
# 6. CronTriggerManager Tests
# =========================================================================


class TestCronTriggerManager:
    """Tests for core.engine.triggers.cron.CronTriggerManager."""

    # --- register_schedule creates config -------------------------------

    def test_register_schedule_creates_config(self):
        mgr = CronTriggerManager()
        cfg = mgr.register_schedule(
            workflow_id="wf-daily",
            name="Daily Report",
            expression="0 9 * * 1-5",
            params={"report_type": "daily"},
        )
        assert isinstance(cfg, CronConfig)
        assert cfg.workflow_id == "wf-daily"
        assert cfg.name == "Daily Report"
        assert cfg.expression == "0 9 * * 1-5"
        assert cfg.params == {"report_type": "daily"}
        assert cfg.status == TriggerStatus.ACTIVE
        assert cfg.next_run is not None
        assert cfg.run_count == 0

    def test_register_schedule_rejects_bad_expression(self):
        mgr = CronTriggerManager()
        with pytest.raises(ValueError):
            mgr.register_schedule(
                workflow_id="wf-1",
                name="Bad",
                expression="not a cron",
            )

    # --- parse_expression parses "0 9 * * 1-5" -------------------------

    def test_parse_expression_weekday_mornings(self):
        fields = CronTriggerManager.parse_expression("0 9 * * 1-5")
        assert fields["minute"] == {0}
        assert fields["hour"] == {9}
        assert fields["day_of_month"] == set(range(1, 32))
        assert fields["month"] == set(range(1, 13))
        assert fields["day_of_week"] == {1, 2, 3, 4, 5}

    def test_parse_expression_every_5_minutes(self):
        fields = CronTriggerManager.parse_expression("*/5 * * * *")
        assert fields["minute"] == {0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}

    def test_parse_expression_specific_values(self):
        fields = CronTriggerManager.parse_expression("30 14 1 6 0")
        assert fields["minute"] == {30}
        assert fields["hour"] == {14}
        assert fields["day_of_month"] == {1}
        assert fields["month"] == {6}
        assert fields["day_of_week"] == {0}  # Sunday

    # --- parse_expression validates bad expression ----------------------

    def test_parse_expression_too_few_fields(self):
        with pytest.raises(ValueError, match="5 fields"):
            CronTriggerManager.parse_expression("0 9 *")

    def test_parse_expression_too_many_fields(self):
        with pytest.raises(ValueError, match="5 fields"):
            CronTriggerManager.parse_expression("0 9 * * 1 extra")

    def test_parse_expression_out_of_range(self):
        with pytest.raises(ValueError):
            CronTriggerManager.parse_expression("60 9 * * *")  # minute 60

    # --- calculate_next_run ---------------------------------------------

    def test_calculate_next_run(self):
        # "0 9 * * *" = every day at 09:00
        after = datetime(2026, 2, 19, 8, 0, 0)
        next_run = CronTriggerManager.calculate_next_run(
            "0 9 * * *", after=after
        )
        assert next_run.hour == 9
        assert next_run.minute == 0
        assert next_run.day >= 19

    def test_calculate_next_run_wraps_to_next_day(self):
        # After 10:00, next 09:00 should be tomorrow
        after = datetime(2026, 2, 19, 10, 0, 0)
        next_run = CronTriggerManager.calculate_next_run(
            "0 9 * * *", after=after
        )
        assert next_run.day == 20
        assert next_run.hour == 9
        assert next_run.minute == 0

    # --- should_run returns True when due -------------------------------

    def test_should_run_returns_true_when_due(self):
        mgr = CronTriggerManager()
        cfg = mgr.register_schedule(
            workflow_id="wf-1",
            name="Test",
            expression="* * * * *",  # every minute
        )
        # Manually set next_run to the past so it's due
        cfg.next_run = datetime.utcnow() - timedelta(minutes=1)

        assert mgr.should_run(cfg.trigger_id) is True

    def test_should_run_returns_false_when_not_due(self):
        mgr = CronTriggerManager()
        cfg = mgr.register_schedule(
            workflow_id="wf-1",
            name="Test",
            expression="* * * * *",
        )
        # Set next_run far in the future
        cfg.next_run = datetime.utcnow() + timedelta(hours=1)

        assert mgr.should_run(cfg.trigger_id) is False

    def test_should_run_respects_max_runs(self):
        mgr = CronTriggerManager()
        cfg = mgr.register_schedule(
            workflow_id="wf-1",
            name="Limited",
            expression="* * * * *",
            max_runs=3,
        )
        cfg.next_run = datetime.utcnow() - timedelta(minutes=1)
        cfg.run_count = 3  # already exhausted

        assert mgr.should_run(cfg.trigger_id) is False

    def test_should_run_returns_false_for_paused(self):
        mgr = CronTriggerManager()
        cfg = mgr.register_schedule(
            workflow_id="wf-1",
            name="Paused",
            expression="* * * * *",
        )
        cfg.next_run = datetime.utcnow() - timedelta(minutes=1)
        mgr.pause(cfg.trigger_id)

        assert mgr.should_run(cfg.trigger_id) is False

    # --- record_run updates counters ------------------------------------

    def test_record_run_updates_counters(self):
        mgr = CronTriggerManager()
        cfg = mgr.register_schedule(
            workflow_id="wf-1",
            name="Test",
            expression="* * * * *",
        )
        assert cfg.run_count == 0
        assert cfg.next_run is not None

        updated = mgr.record_run(cfg.trigger_id)
        assert updated.run_count == 1
        assert updated.last_run is not None
        # next_run should have been recomputed to a future time
        assert updated.next_run is not None
        assert updated.next_run > updated.last_run

    def test_record_run_disables_at_max_runs(self):
        mgr = CronTriggerManager()
        cfg = mgr.register_schedule(
            workflow_id="wf-1",
            name="One-shot",
            expression="* * * * *",
            max_runs=1,
        )
        updated = mgr.record_run(cfg.trigger_id)
        assert updated.run_count == 1
        assert updated.status == TriggerStatus.DISABLED
        assert updated.next_run is None

    def test_record_run_raises_for_unknown_trigger(self):
        mgr = CronTriggerManager()
        with pytest.raises(KeyError):
            mgr.record_run("no-such-id")

    # --- get_due_triggers -----------------------------------------------

    def test_get_due_triggers(self):
        mgr = CronTriggerManager()

        cfg_due = mgr.register_schedule(
            workflow_id="wf-due",
            name="Due",
            expression="* * * * *",
        )
        cfg_due.next_run = datetime.utcnow() - timedelta(minutes=1)

        cfg_future = mgr.register_schedule(
            workflow_id="wf-future",
            name="Future",
            expression="* * * * *",
        )
        cfg_future.next_run = datetime.utcnow() + timedelta(hours=1)

        cfg_paused = mgr.register_schedule(
            workflow_id="wf-paused",
            name="Paused",
            expression="* * * * *",
        )
        cfg_paused.next_run = datetime.utcnow() - timedelta(minutes=1)
        mgr.pause(cfg_paused.trigger_id)

        due = mgr.get_due_triggers()
        due_ids = [c.trigger_id for c in due]
        assert cfg_due.trigger_id in due_ids
        assert cfg_future.trigger_id not in due_ids
        assert cfg_paused.trigger_id not in due_ids

    # --- LicenseError ---------------------------------------------------

    def test_cron_raises_license_error_when_disabled(self, disable_all_features):
        with pytest.raises(LicenseError):
            CronTriggerManager()
