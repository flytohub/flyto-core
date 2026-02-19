# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Real integration tests for the 6 engine features.

No mocking — all tests exercise real code paths:
1. MeteringHook        — real hook lifecycle with real timing
2. TimeoutGuard        — real asyncio timeouts with real coroutines
3. ExecutionQueueManager — real async processing loop executing real callbacks
4. WorkflowVersionManager — real versioning, diff, rollback on in-memory store
5. WebhookTriggerManager — real HMAC-SHA256 crypto, real payload mapping
6. CronTriggerManager  — real cron parsing, real scheduler loop firing callbacks
"""

import asyncio
import hashlib
import hmac
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Set

import pytest

from core.licensing import (
    FeatureFlag,
    LicenseError,
    LicenseManager,
    LicenseTier,
)
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
from core.engine.triggers.base import TriggerStatus, TriggerType


# =============================================================================
# License Checker — real Protocol implementation (not a mock)
#
# In production, flyto-pro registers its own LicenseChecker.
# Here we use a minimal but real implementation of the same Protocol.
# =============================================================================


class EnterpriseLicenseChecker:
    """
    Real LicenseChecker implementation for testing.

    Identical to how flyto-pro registers a checker at startup.
    This is NOT a mock — it implements the LicenseChecker Protocol fully.
    """

    def get_tier(self) -> LicenseTier:
        return LicenseTier.ENTERPRISE

    def has_feature(self, feature: FeatureFlag) -> bool:
        return True

    def can_access_module(self, module_id: str) -> bool:
        return True

    def get_module_access_info(self, module_id: str) -> Dict[str, Any]:
        return {"accessible": True, "current_tier": "enterprise"}


@pytest.fixture(autouse=True)
def enable_enterprise_license():
    """Register an enterprise license checker for each test, restore after."""
    original = LicenseManager._checker
    LicenseManager.register_checker(EnterpriseLicenseChecker())
    yield
    LicenseManager._checker = original


@pytest.fixture()
def free_tier_license():
    """Remove checker so LicenseManager falls back to FREE tier behavior."""
    original = LicenseManager._checker
    LicenseManager._checker = None
    yield
    LicenseManager._checker = original


# =============================================================================
# Helpers
# =============================================================================


def _ctx(
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
    return HookContext(
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


# =========================================================================
# 1. MeteringHook — real hook lifecycle
# =========================================================================


class TestMeteringHook:

    def test_full_workflow_lifecycle_records(self):
        """A complete workflow start→step→step→complete produces correct records."""
        hook = MeteringHook()

        # Start workflow
        hook.on_workflow_start(_ctx())

        # Execute 2 steps with real time gaps
        for i in range(2):
            step = _ctx(step_id="s-{}".format(i), module_id="string.reverse", step_index=i, total_steps=2)
            hook.on_pre_execute(step)
            time.sleep(0.002)  # real 2ms gap
            hook.on_post_execute(step)

        # Complete
        hook.on_workflow_complete(_ctx())

        records = hook.get_usage_records()
        step_records = [r for r in records if r.record_type == "step"]
        wf_records = [r for r in records if r.record_type == "workflow"]

        assert len(step_records) == 2
        assert len(wf_records) == 1

        # Step records have real duration > 0
        for sr in step_records:
            assert sr.duration_ms > 0
            assert sr.module_id == "string.reverse"
            assert sr.status == "success"

        # Workflow record
        assert wf_records[0].status == "success"
        assert wf_records[0].duration_ms >= 0

    def test_failed_workflow_records_error(self):
        hook = MeteringHook()
        hook.on_workflow_start(_ctx())
        hook.on_workflow_failed(_ctx(error_type="RuntimeError", error_message="boom"))

        records = hook.get_usage_records()
        assert len(records) == 1
        assert records[0].status == "failed"
        assert records[0].metadata["error_type"] == "RuntimeError"
        assert records[0].metadata["error_message"] == "boom"

    def test_failed_step_records_error(self):
        hook = MeteringHook()
        hook.on_workflow_start(_ctx())

        step = _ctx(
            step_id="s-err", module_id="file.write",
            error=RuntimeError("disk full"),
            error_type="RuntimeError", error_message="disk full",
        )
        hook.on_pre_execute(step)
        hook.on_post_execute(step)

        step_records = [r for r in hook.get_usage_records() if r.record_type == "step"]
        assert len(step_records) == 1
        assert step_records[0].status == "failed"
        assert step_records[0].metadata["error_type"] == "RuntimeError"

    def test_summary_aggregation(self):
        hook = MeteringHook()

        # 2 workflows: one success (2 steps), one failed (1 step with error)
        hook.on_workflow_start(_ctx(workflow_id="wf-a"))
        for i in range(2):
            s = _ctx(workflow_id="wf-a", step_id="s{}".format(i), module_id="http.get")
            hook.on_pre_execute(s)
            hook.on_post_execute(s)
        hook.on_workflow_complete(_ctx(workflow_id="wf-a"))

        hook.on_workflow_start(_ctx(workflow_id="wf-b"))
        s = _ctx(
            workflow_id="wf-b", step_id="s0", module_id="db.query",
            error=RuntimeError("x"), error_type="RuntimeError", error_message="x",
        )
        hook.on_pre_execute(s)
        hook.on_post_execute(s)
        hook.on_workflow_failed(_ctx(workflow_id="wf-b", error_type="RuntimeError", error_message="x"))

        summary = hook.get_summary()
        assert summary["total_workflows"] == 2
        assert summary["workflows_succeeded"] == 1
        assert summary["workflows_failed"] == 1
        assert summary["total_steps"] == 3
        assert summary["steps_succeeded"] == 2
        assert summary["steps_failed"] == 1
        assert "http.get" in summary["module_breakdown"]
        assert summary["module_breakdown"]["http.get"]["count"] == 2
        assert "db.query" in summary["module_breakdown"]
        assert summary["module_breakdown"]["db.query"]["failed"] == 1

    def test_flush_returns_and_clears(self):
        hook = MeteringHook()
        hook.on_workflow_start(_ctx())
        hook.on_workflow_complete(_ctx())
        assert len(hook.get_usage_records()) == 1

        flushed = hook.flush()
        assert len(flushed) == 1
        assert len(hook.get_usage_records()) == 0

    def test_on_record_callback_receives_every_record(self):
        received = []
        hook = MeteringHook(on_record=lambda rec: received.append(rec))

        hook.on_workflow_start(_ctx())
        s = _ctx(step_id="s1", module_id="string.upper")
        hook.on_pre_execute(s)
        hook.on_post_execute(s)
        hook.on_workflow_complete(_ctx())

        # 1 step record + 1 workflow record
        assert len(received) == 2
        types = {r.record_type for r in received}
        assert types == {"step", "workflow"}

    def test_usage_record_to_dict_serialization(self):
        hook = MeteringHook()
        hook.on_workflow_start(_ctx())
        hook.on_workflow_complete(_ctx())

        d = hook.get_usage_records()[0].to_dict()
        assert isinstance(d["record_id"], str)
        assert isinstance(d["started_at"], str)  # ISO format
        assert d["record_type"] == "workflow"

    def test_free_tier_all_hooks_are_noops(self, free_tier_license):
        hook = MeteringHook()
        hook.on_workflow_start(_ctx())
        s = _ctx(step_id="s1", module_id="x")
        hook.on_pre_execute(s)
        hook.on_post_execute(s)
        hook.on_workflow_complete(_ctx())
        hook.on_workflow_failed(_ctx())

        assert len(hook.get_usage_records()) == 0
        assert hook.get_summary()["total_workflows"] == 0


# =========================================================================
# 2. TimeoutGuard — real async timeouts
# =========================================================================


class TestTimeoutGuard:

    async def test_fast_coroutine_completes(self):
        guard = TimeoutGuard(step_timeout_ms=5000)

        async def fast():
            await asyncio.sleep(0.001)
            return 42

        result = await guard.execute_with_timeout(fast(), label="fast")
        assert result == 42

    async def test_slow_coroutine_raises_timeout(self):
        guard = TimeoutGuard(step_timeout_ms=50)

        async def slow():
            await asyncio.sleep(10)

        with pytest.raises(ExecutionTimeoutError) as exc_info:
            await guard.execute_with_timeout(slow(), timeout_ms=50, label="slow-op")

        assert exc_info.value.timeout_ms == 50
        assert exc_info.value.label == "slow-op"

    async def test_guard_workflow_succeeds(self):
        guard = TimeoutGuard(workflow_timeout_ms=5000)

        async def work():
            await asyncio.sleep(0.001)
            return {"ok": True}

        result = await guard.guard_workflow(work(), workflow_id="wf-fast")
        assert result == {"ok": True}

    async def test_guard_workflow_timeout(self):
        guard = TimeoutGuard(workflow_timeout_ms=50)

        async def slow_work():
            await asyncio.sleep(10)

        with pytest.raises(ExecutionTimeoutError) as exc_info:
            await guard.guard_workflow(slow_work(), workflow_id="wf-slow")

        assert exc_info.value.workflow_id == "wf-slow"
        assert exc_info.value.timeout_ms == 50

    async def test_guard_step_succeeds(self):
        guard = TimeoutGuard(step_timeout_ms=5000)

        async def step():
            return {"data": "hello"}

        result = await guard.guard_step(step(), step_id="s1", module_id="string.upper")
        assert result == {"data": "hello"}

    async def test_guard_step_timeout(self):
        guard = TimeoutGuard(step_timeout_ms=50)

        async def slow_step():
            await asyncio.sleep(10)

        with pytest.raises(ExecutionTimeoutError) as exc_info:
            await guard.guard_step(slow_step(), step_id="s1", module_id="http.get")

        assert exc_info.value.step_id == "s1"

    async def test_guard_step_custom_timeout_overrides_default(self):
        guard = TimeoutGuard(step_timeout_ms=60000)  # 60s default

        async def slow():
            await asyncio.sleep(10)

        with pytest.raises(ExecutionTimeoutError):
            await guard.guard_step(slow(), step_id="s1", module_id="x", custom_timeout_ms=50)

    def test_timeout_hooks_abort_when_budget_exceeded(self):
        guard = TimeoutGuard(workflow_timeout_ms=1)  # 1ms budget
        hooks = TimeoutHooks(guard)

        hooks.on_workflow_start(_ctx())
        time.sleep(0.01)  # wait 10ms — exceeds 1ms budget

        result = hooks.on_pre_execute(_ctx())
        assert result.action == HookAction.ABORT
        assert "exceeded time budget" in result.abort_reason

    def test_timeout_hooks_continue_within_budget(self):
        guard = TimeoutGuard(workflow_timeout_ms=60000)
        hooks = TimeoutHooks(guard)
        hooks.on_workflow_start(_ctx())

        result = hooks.on_pre_execute(_ctx())
        assert result.action == HookAction.CONTINUE

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

    def test_timeout_hooks_callback_on_abort(self):
        errors = []
        guard = TimeoutGuard(
            workflow_timeout_ms=1,
            on_timeout_callback=lambda e: errors.append(e),
        )
        hooks = TimeoutHooks(guard)
        hooks.on_workflow_start(_ctx())
        time.sleep(0.01)
        hooks.on_pre_execute(_ctx())

        assert len(errors) == 1
        assert isinstance(errors[0], ExecutionTimeoutError)

    def test_timeout_error_to_dict(self):
        err = ExecutionTimeoutError(
            message="Timed out", timeout_ms=5000, label="test",
            workflow_id="wf-1", step_id="s-1",
        )
        d = err.to_dict()
        assert d["timeout_ms"] == 5000
        assert d["workflow_id"] == "wf-1"
        assert d["step_id"] == "s-1"

    def test_hooks_cleanup_on_complete(self):
        hooks = TimeoutHooks(TimeoutGuard())
        hooks.on_workflow_start(_ctx())
        assert "wf-1" in hooks._workflow_start_times
        hooks.on_workflow_complete(_ctx())
        assert "wf-1" not in hooks._workflow_start_times

    def test_hooks_cleanup_on_failed(self):
        hooks = TimeoutHooks(TimeoutGuard())
        hooks.on_workflow_start(_ctx())
        hooks.on_workflow_failed(_ctx())
        assert "wf-1" not in hooks._workflow_start_times


# =========================================================================
# 3. ExecutionQueueManager — real async processing loop
# =========================================================================


class TestExecutionQueueManager:

    def test_enqueue_creates_item(self):
        mgr = ExecutionQueueManager(max_concurrent=5)
        item = mgr.enqueue(workflow_id="wf-1", workflow_name="My WF", params={"key": "val"})

        assert isinstance(item, QueueItem)
        assert item.workflow_id == "wf-1"
        assert item.status == "pending"
        assert item.priority == QueuePriority.NORMAL

    def test_priority_ordering(self):
        mgr = ExecutionQueueManager(max_concurrent=5)
        low = mgr.enqueue(workflow_id="wf-low", workflow_name="Low", priority=QueuePriority.LOW)
        normal = mgr.enqueue(workflow_id="wf-norm", workflow_name="Normal", priority=QueuePriority.NORMAL)
        critical = mgr.enqueue(workflow_id="wf-crit", workflow_name="Critical", priority=QueuePriority.CRITICAL)
        high = mgr.enqueue(workflow_id="wf-high", workflow_name="High", priority=QueuePriority.HIGH)

        queue = mgr.get_queue()
        ids = [i.item_id for i in queue]
        assert ids == [critical.item_id, high.item_id, normal.item_id, low.item_id]

    def test_cancel(self):
        mgr = ExecutionQueueManager(max_concurrent=5)
        item = mgr.enqueue(workflow_id="wf-1", workflow_name="Cancel Me")
        assert mgr.cancel(item.item_id) is True
        assert mgr.get_status(item.item_id).status == "cancelled"
        # Can't cancel twice
        assert mgr.cancel(item.item_id) is False

    def test_cancel_nonexistent(self):
        mgr = ExecutionQueueManager(max_concurrent=5)
        assert mgr.cancel("nonexistent") is False

    def test_get_stats(self):
        mgr = ExecutionQueueManager(max_concurrent=3)
        mgr.enqueue(workflow_id="wf-1", workflow_name="A")
        mgr.enqueue(workflow_id="wf-2", workflow_name="B")
        c = mgr.enqueue(workflow_id="wf-3", workflow_name="C")
        mgr.cancel(c.item_id)

        stats = mgr.get_stats()
        assert stats["pending"] == 2
        assert stats["running"] == 0
        assert stats["max_concurrent"] == 3

    def test_get_status_unknown(self):
        mgr = ExecutionQueueManager(max_concurrent=5)
        assert mgr.get_status("no-such-id") is None

    async def test_real_processing_loop_executes_items(self):
        """Start the queue, enqueue items, verify they are actually executed."""
        executed = []

        async def real_executor(**kwargs):
            executed.append(kwargs["workflow_id"])
            await asyncio.sleep(0.01)  # simulate real work
            return {"ok": True, "wf": kwargs["workflow_id"]}

        mgr = ExecutionQueueManager(max_concurrent=2, on_execute=real_executor)

        # Start the processing loop
        await mgr.start()

        # Enqueue 3 items
        item1 = mgr.enqueue(workflow_id="wf-1", workflow_name="First")
        item2 = mgr.enqueue(workflow_id="wf-2", workflow_name="Second")
        item3 = mgr.enqueue(workflow_id="wf-3", workflow_name="Third")

        # Wait for all to complete (with a real timeout)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            await asyncio.sleep(0.05)
            statuses = [mgr.get_status(i.item_id).status for i in [item1, item2, item3]]
            if all(s == "completed" for s in statuses):
                break

        await mgr.stop()

        # All 3 were really executed
        assert set(executed) == {"wf-1", "wf-2", "wf-3"}
        assert mgr.get_status(item1.item_id).status == "completed"
        assert mgr.get_status(item2.item_id).status == "completed"
        assert mgr.get_status(item3.item_id).status == "completed"

        stats = mgr.get_stats()
        assert stats["completed"] == 3
        assert stats["failed"] == 0

    async def test_processing_loop_handles_failures(self):
        """Items that raise exceptions are marked as failed, not crashed."""
        async def failing_executor(**kwargs):
            if kwargs["workflow_id"] == "wf-fail":
                raise RuntimeError("Intentional failure")
            return {"ok": True}

        mgr = ExecutionQueueManager(max_concurrent=2, on_execute=failing_executor)
        await mgr.start()

        ok_item = mgr.enqueue(workflow_id="wf-ok", workflow_name="OK")
        fail_item = mgr.enqueue(workflow_id="wf-fail", workflow_name="Fail")

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            await asyncio.sleep(0.05)
            ok_status = mgr.get_status(ok_item.item_id).status
            fail_status = mgr.get_status(fail_item.item_id).status
            if ok_status != "pending" and fail_status != "pending":
                break

        await mgr.stop()

        assert mgr.get_status(ok_item.item_id).status == "completed"
        assert mgr.get_status(fail_item.item_id).status == "failed"
        assert "Intentional failure" in mgr.get_status(fail_item.item_id).error

    async def test_processing_loop_respects_priority(self):
        """Higher priority items are picked up first."""
        execution_order = []

        async def order_tracker(**kwargs):
            execution_order.append(kwargs["workflow_id"])
            await asyncio.sleep(0.01)

        # max_concurrent=1 so items execute sequentially
        mgr = ExecutionQueueManager(max_concurrent=1, on_execute=order_tracker)

        # Enqueue LOW first, then CRITICAL — CRITICAL should execute first
        mgr.enqueue(workflow_id="low", workflow_name="Low", priority=QueuePriority.LOW)
        mgr.enqueue(workflow_id="critical", workflow_name="Critical", priority=QueuePriority.CRITICAL)
        mgr.enqueue(workflow_id="normal", workflow_name="Normal", priority=QueuePriority.NORMAL)

        await mgr.start()

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            await asyncio.sleep(0.05)
            if len(execution_order) == 3:
                break

        await mgr.stop()

        assert len(execution_order) == 3
        assert execution_order[0] == "critical"

    async def test_cancelled_items_are_not_executed(self):
        executed = []

        async def track(**kwargs):
            executed.append(kwargs["workflow_id"])

        mgr = ExecutionQueueManager(max_concurrent=1, on_execute=track)

        item = mgr.enqueue(workflow_id="wf-cancel", workflow_name="Cancel")
        mgr.cancel(item.item_id)
        mgr.enqueue(workflow_id="wf-run", workflow_name="Run")

        await mgr.start()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            await asyncio.sleep(0.05)
            if "wf-run" in executed:
                break
        await mgr.stop()

        assert "wf-cancel" not in executed
        assert "wf-run" in executed

    def test_free_tier_raises_license_error(self, free_tier_license):
        with pytest.raises(LicenseError):
            ExecutionQueueManager(max_concurrent=5)


# =========================================================================
# 4. WorkflowVersionManager — real versioning operations
# =========================================================================


class TestWorkflowVersionManager:

    def _def(self, steps=None):
        if steps is None:
            steps = [
                {"id": "s1", "module": "http.get", "params": {"url": "https://example.com"}},
                {"id": "s2", "module": "json.parse", "params": {"path": "$.data"}},
            ]
        return {"name": "test-workflow", "steps": steps}

    def test_save_and_get_version(self):
        mgr = WorkflowVersionManager()
        ver = mgr.save_version(
            workflow_id="wf-1", name="Initial", definition=self._def(),
            version="1.0.0", created_by="alice",
        )
        assert isinstance(ver, WorkflowVersion)
        assert ver.workflow_id == "wf-1"
        assert ver.version == "1.0.0"
        assert ver.parent_version is None

        fetched = mgr.get_version(ver.version_id)
        assert fetched.version_id == ver.version_id

    def test_parent_linking(self):
        mgr = WorkflowVersionManager()
        v1 = mgr.save_version(workflow_id="wf-1", name="V1", definition=self._def(), version="1.0.0")
        v2 = mgr.save_version(workflow_id="wf-1", name="V2", definition=self._def(), version="1.1.0")
        assert v2.parent_version == v1.version_id

    def test_get_latest(self):
        mgr = WorkflowVersionManager()
        mgr.save_version(workflow_id="wf-1", name="V1", definition=self._def(), version="1.0.0")
        v2 = mgr.save_version(workflow_id="wf-1", name="V2", definition=self._def(), version="2.0.0")

        latest = mgr.get_latest("wf-1")
        assert latest.version_id == v2.version_id

    def test_get_latest_nonexistent(self):
        mgr = WorkflowVersionManager()
        assert mgr.get_latest("no-such") is None

    def test_list_versions_newest_first(self):
        mgr = WorkflowVersionManager()
        v1 = mgr.save_version(workflow_id="wf-1", name="V1", definition=self._def(), version="1.0.0")
        v2 = mgr.save_version(workflow_id="wf-1", name="V2", definition=self._def(), version="1.1.0")
        v3 = mgr.save_version(workflow_id="wf-1", name="V3", definition=self._def(), version="2.0.0")

        versions = mgr.list_versions("wf-1")
        assert [v.version_id for v in versions] == [v3.version_id, v2.version_id, v1.version_id]

    def test_diff_detects_added_removed_modified(self):
        mgr = WorkflowVersionManager()
        def_a = {"steps": [
            {"id": "s1", "module": "http.get", "params": {"url": "https://a.com"}},
            {"id": "s2", "module": "json.parse", "params": {"path": "$.data"}},
            {"id": "s3", "module": "log", "params": {"msg": "done"}},
        ]}
        def_b = {"steps": [
            {"id": "s1", "module": "http.get", "params": {"url": "https://b.com"}},  # modified url
            # s2 removed
            {"id": "s3", "module": "log", "params": {"msg": "done"}},  # unchanged
            {"id": "s4", "module": "email.send", "params": {"to": "a@b.com"}},  # added
        ]}

        v1 = mgr.save_version(workflow_id="wf-1", name="V1", definition=def_a, version="1.0.0")
        v2 = mgr.save_version(workflow_id="wf-1", name="V2", definition=def_b, version="1.1.0")

        diff = mgr.diff(v1.version_id, v2.version_id)
        assert isinstance(diff, VersionDiff)
        assert "s4" in diff.steps_added
        assert "s2" in diff.steps_removed
        assert "s1" in diff.steps_modified
        assert "s3" not in diff.steps_modified

        # Verify params_changed captures the actual old/new values
        # The diff compares top-level step keys (id, module, params)
        assert "s1" in diff.params_changed
        s1_changes = diff.params_changed["s1"]
        assert "params" in s1_changes
        assert s1_changes["params"]["old"] == {"url": "https://a.com"}
        assert s1_changes["params"]["new"] == {"url": "https://b.com"}

    def test_diff_no_changes(self):
        mgr = WorkflowVersionManager()
        defn = self._def()
        v1 = mgr.save_version(workflow_id="wf-1", name="V1", definition=defn, version="1.0.0")
        v2 = mgr.save_version(workflow_id="wf-1", name="V2", definition=defn, version="1.0.1")

        diff = mgr.diff(v1.version_id, v2.version_id)
        assert diff.steps_added == []
        assert diff.steps_removed == []
        assert diff.steps_modified == []

    def test_rollback(self):
        mgr = WorkflowVersionManager()
        def_v1 = self._def([{"id": "s1", "module": "http.get", "params": {}}])
        def_v2 = self._def([
            {"id": "s1", "module": "http.get", "params": {}},
            {"id": "s2", "module": "email.send", "params": {}},
        ])

        v1 = mgr.save_version(workflow_id="wf-1", name="V1", definition=def_v1, version="1.0.0")
        v2 = mgr.save_version(workflow_id="wf-1", name="V2", definition=def_v2, version="1.1.0")

        rolled = mgr.rollback("wf-1", v1.version_id)

        # Rollback creates a NEW version with the old definition
        assert rolled.version_id != v1.version_id
        assert rolled.definition == def_v1
        assert rolled.parent_version == v2.version_id
        assert "Rollback" in rolled.description

        # It's now the latest
        assert mgr.get_latest("wf-1").version_id == rolled.version_id

    def test_publish(self):
        mgr = WorkflowVersionManager()
        ver = mgr.save_version(workflow_id="wf-1", name="V1", definition=self._def(), version="1.0.0")
        assert ver.is_published is False

        published = mgr.publish(ver.version_id)
        assert published.is_published is True

    def test_delete_published_raises(self):
        mgr = WorkflowVersionManager()
        ver = mgr.save_version(workflow_id="wf-1", name="V1", definition=self._def(), version="1.0.0")
        mgr.publish(ver.version_id)

        with pytest.raises(ValueError, match="Cannot delete published"):
            mgr.delete_version(ver.version_id)

    def test_delete_unpublished(self):
        mgr = WorkflowVersionManager()
        ver = mgr.save_version(workflow_id="wf-1", name="V1", definition=self._def(), version="1.0.0")
        assert mgr.delete_version(ver.version_id) is True
        assert mgr.get_version(ver.version_id) is None

    def test_delete_nonexistent(self):
        mgr = WorkflowVersionManager()
        assert mgr.delete_version("no-such") is False

    def test_get_history(self):
        mgr = WorkflowVersionManager()
        mgr.save_version(workflow_id="wf-1", name="V1", definition=self._def(), version="1.0.0")
        mgr.save_version(workflow_id="wf-1", name="V2", definition=self._def(), version="1.1.0")

        history = mgr.get_history("wf-1")
        assert len(history) == 2

    def test_free_tier_raises_license_error(self, free_tier_license):
        mgr = WorkflowVersionManager()
        with pytest.raises(LicenseError):
            mgr.save_version(workflow_id="wf-1", name="V1", definition={})


# =========================================================================
# 5. WebhookTriggerManager — real HMAC crypto, real payload mapping
# =========================================================================


class TestWebhookTriggerManager:

    def test_register_webhook(self):
        mgr = WebhookTriggerManager()
        cfg = mgr.register_webhook(
            workflow_id="wf-deploy", name="GitHub Push",
            secret="my-secret-key", allowed_methods=["POST"],
            payload_mapping={"repo": "repository.full_name"},
        )
        assert isinstance(cfg, WebhookConfig)
        assert cfg.workflow_id == "wf-deploy"
        assert cfg.secret == "my-secret-key"
        assert cfg.status == TriggerStatus.ACTIVE

    def test_hmac_verification_valid_signature(self):
        """Real HMAC-SHA256 verification with real crypto."""
        mgr = WebhookTriggerManager()
        secret = "webhook-secret-2026"
        cfg = mgr.register_webhook(workflow_id="wf-1", name="Signed", secret=secret)

        payload = b'{"event":"push","ref":"main"}'
        real_sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

        assert mgr.verify_signature(cfg.trigger_id, payload, real_sig) is True

    def test_hmac_verification_github_sha256_prefix(self):
        """GitHub sends signatures as 'sha256=<hex>' — verify prefix is handled."""
        mgr = WebhookTriggerManager()
        secret = "github-secret"
        cfg = mgr.register_webhook(workflow_id="wf-1", name="GitHub", secret=secret)

        payload = b'{"action":"completed"}'
        raw_sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

        assert mgr.verify_signature(cfg.trigger_id, payload, "sha256=" + raw_sig) is True

    def test_hmac_verification_invalid_signature(self):
        mgr = WebhookTriggerManager()
        cfg = mgr.register_webhook(workflow_id="wf-1", name="Test", secret="correct-secret")

        payload = b'{"data": 1}'
        assert mgr.verify_signature(cfg.trigger_id, payload, "wrong-signature") is False

    def test_hmac_no_secret_always_passes(self):
        mgr = WebhookTriggerManager()
        cfg = mgr.register_webhook(workflow_id="wf-1", name="Open", secret="")
        assert mgr.verify_signature(cfg.trigger_id, b"anything", "anything") is True

    def test_hmac_unknown_trigger(self):
        mgr = WebhookTriggerManager()
        assert mgr.verify_signature("nonexistent", b"data", "sig") is False

    def test_process_webhook_valid_request(self):
        mgr = WebhookTriggerManager()
        cfg = mgr.register_webhook(
            workflow_id="wf-deploy", name="Deploy",
            allowed_methods=["POST"],
            payload_mapping={"branch": "ref", "repo": "repository.name"},
        )

        event = mgr.process_webhook(
            trigger_id=cfg.trigger_id, method="POST",
            headers={"Content-Type": "application/json"},
            payload={"ref": "main", "repository": {"name": "flyto-core"}},
        )

        assert event is not None
        assert event.workflow_id == "wf-deploy"
        assert event.trigger_type == TriggerType.WEBHOOK
        assert event.payload["branch"] == "main"
        assert event.payload["repo"] == "flyto-core"

    def test_process_webhook_rejects_wrong_method(self):
        mgr = WebhookTriggerManager()
        cfg = mgr.register_webhook(workflow_id="wf-1", name="POST", allowed_methods=["POST"])

        event = mgr.process_webhook(cfg.trigger_id, method="GET", headers={}, payload={})
        assert event is None

    def test_process_webhook_rejects_paused_trigger(self):
        mgr = WebhookTriggerManager()
        cfg = mgr.register_webhook(workflow_id="wf-1", name="Paused")
        mgr.pause(cfg.trigger_id)

        event = mgr.process_webhook(cfg.trigger_id, method="POST", headers={}, payload={})
        assert event is None

    def test_process_webhook_nonexistent_trigger(self):
        mgr = WebhookTriggerManager()
        event = mgr.process_webhook("no-such-id", method="POST", headers={}, payload={})
        assert event is None

    def test_map_payload_nested_dot_path(self):
        """Real dot-path traversal into nested dicts."""
        cfg = WebhookConfig(
            trigger_id="t1", trigger_type="webhook", workflow_id="wf-1", name="Test",
            payload_mapping={
                "repo_name": "repository.full_name",
                "branch": "ref",
                "sender": "sender.login",
            },
        )
        payload = {
            "repository": {"full_name": "flytohub/flyto-core", "id": 12345},
            "ref": "refs/heads/main",
            "sender": {"login": "alice", "id": 42},
        }

        result = WebhookTriggerManager.map_payload(cfg, payload)
        assert result["repo_name"] == "flytohub/flyto-core"
        assert result["branch"] == "refs/heads/main"
        assert result["sender"] == "alice"

    def test_map_payload_no_mapping_returns_full(self):
        cfg = WebhookConfig(
            trigger_id="t1", trigger_type="webhook",
            workflow_id="wf-1", name="Test", payload_mapping={},
        )
        payload = {"key": "value", "num": 42}
        assert WebhookTriggerManager.map_payload(cfg, payload) == payload

    def test_map_payload_missing_path_skipped(self):
        cfg = WebhookConfig(
            trigger_id="t1", trigger_type="webhook",
            workflow_id="wf-1", name="Test",
            payload_mapping={"exists": "a.b", "missing": "x.y.z"},
        )
        result = WebhookTriggerManager.map_payload(cfg, {"a": {"b": "found"}})
        assert result["exists"] == "found"
        assert "missing" not in result

    def test_pause_and_resume(self):
        mgr = WebhookTriggerManager()
        cfg = mgr.register_webhook(workflow_id="wf-1", name="Toggle")
        assert cfg.status == TriggerStatus.ACTIVE

        mgr.pause(cfg.trigger_id)
        assert mgr.get(cfg.trigger_id).status == TriggerStatus.PAUSED

        mgr.resume(cfg.trigger_id)
        assert mgr.get(cfg.trigger_id).status == TriggerStatus.ACTIVE

    def test_unregister(self):
        mgr = WebhookTriggerManager()
        cfg = mgr.register_webhook(workflow_id="wf-1", name="Remove")
        assert mgr.unregister(cfg.trigger_id) is True
        assert mgr.get(cfg.trigger_id) is None

    def test_list_triggers(self):
        mgr = WebhookTriggerManager()
        mgr.register_webhook(workflow_id="wf-1", name="A")
        mgr.register_webhook(workflow_id="wf-1", name="B")
        mgr.register_webhook(workflow_id="wf-2", name="C")

        all_triggers = mgr.list_triggers()
        assert len(all_triggers) == 3

        wf1_triggers = mgr.list_triggers(workflow_id="wf-1")
        assert len(wf1_triggers) == 2

    def test_free_tier_raises_license_error(self, free_tier_license):
        with pytest.raises(LicenseError):
            WebhookTriggerManager()


# =========================================================================
# 6. CronTriggerManager — real cron parsing and real scheduler loop
# =========================================================================


class TestCronTriggerManager:

    # --- Registration & parsing ---

    def test_register_schedule(self):
        mgr = CronTriggerManager()
        cfg = mgr.register_schedule(
            workflow_id="wf-daily", name="Daily Report",
            expression="0 9 * * 1-5", params={"type": "daily"},
        )
        assert isinstance(cfg, CronConfig)
        assert cfg.expression == "0 9 * * 1-5"
        assert cfg.params == {"type": "daily"}
        assert cfg.next_run is not None
        assert cfg.run_count == 0
        assert cfg.status == TriggerStatus.ACTIVE

    def test_register_rejects_bad_expression(self):
        mgr = CronTriggerManager()
        with pytest.raises(ValueError):
            mgr.register_schedule(workflow_id="wf-1", name="Bad", expression="not valid cron")

    # --- Real cron expression parsing ---

    def test_parse_weekday_mornings(self):
        fields = CronTriggerManager.parse_expression("0 9 * * 1-5")
        assert fields["minute"] == {0}
        assert fields["hour"] == {9}
        assert fields["day_of_month"] == set(range(1, 32))
        assert fields["month"] == set(range(1, 13))
        assert fields["day_of_week"] == {1, 2, 3, 4, 5}

    def test_parse_every_5_minutes(self):
        fields = CronTriggerManager.parse_expression("*/5 * * * *")
        assert fields["minute"] == {0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}

    def test_parse_specific_values(self):
        fields = CronTriggerManager.parse_expression("30 14 1 6 0")
        assert fields["minute"] == {30}
        assert fields["hour"] == {14}
        assert fields["day_of_month"] == {1}
        assert fields["month"] == {6}
        assert fields["day_of_week"] == {0}  # Sunday

    def test_parse_list(self):
        fields = CronTriggerManager.parse_expression("0 8,12,18 * * *")
        assert fields["hour"] == {8, 12, 18}

    def test_parse_range_with_step(self):
        fields = CronTriggerManager.parse_expression("0 0 1-15/3 * *")
        assert fields["day_of_month"] == {1, 4, 7, 10, 13}

    def test_parse_too_few_fields(self):
        with pytest.raises(ValueError, match="5 fields"):
            CronTriggerManager.parse_expression("0 9 *")

    def test_parse_too_many_fields(self):
        with pytest.raises(ValueError, match="5 fields"):
            CronTriggerManager.parse_expression("0 9 * * 1 extra")

    def test_parse_out_of_range(self):
        with pytest.raises(ValueError):
            CronTriggerManager.parse_expression("60 9 * * *")  # minute 60 invalid

    # --- Real next-run calculation ---

    def test_calculate_next_run_same_day(self):
        after = datetime(2026, 2, 19, 8, 0, 0)  # Thursday 08:00
        next_run = CronTriggerManager.calculate_next_run("0 9 * * *", after=after)
        assert next_run == datetime(2026, 2, 19, 9, 0, 0)

    def test_calculate_next_run_wraps_to_next_day(self):
        after = datetime(2026, 2, 19, 10, 0, 0)  # past 09:00
        next_run = CronTriggerManager.calculate_next_run("0 9 * * *", after=after)
        assert next_run == datetime(2026, 2, 20, 9, 0, 0)

    def test_calculate_next_run_weekday_only(self):
        # Friday 2026-02-20, expression "0 9 * * 1-5" (Mon-Fri)
        after = datetime(2026, 2, 20, 10, 0, 0)  # Friday past 09:00
        next_run = CronTriggerManager.calculate_next_run("0 9 * * 1-5", after=after)
        # Next weekday 09:00 is Monday 2026-02-23
        assert next_run == datetime(2026, 2, 23, 9, 0, 0)
        assert next_run.weekday() == 0  # Monday

    def test_calculate_next_run_every_5_minutes(self):
        after = datetime(2026, 2, 19, 10, 12, 0)
        next_run = CronTriggerManager.calculate_next_run("*/5 * * * *", after=after)
        assert next_run == datetime(2026, 2, 19, 10, 15, 0)

    # --- should_run / record_run ---

    def test_should_run_when_due(self):
        mgr = CronTriggerManager()
        cfg = mgr.register_schedule(workflow_id="wf-1", name="Due", expression="* * * * *")
        cfg.next_run = datetime.utcnow() - timedelta(minutes=1)

        assert mgr.should_run(cfg.trigger_id) is True

    def test_should_run_not_due(self):
        mgr = CronTriggerManager()
        cfg = mgr.register_schedule(workflow_id="wf-1", name="Future", expression="* * * * *")
        cfg.next_run = datetime.utcnow() + timedelta(hours=1)

        assert mgr.should_run(cfg.trigger_id) is False

    def test_should_run_paused(self):
        mgr = CronTriggerManager()
        cfg = mgr.register_schedule(workflow_id="wf-1", name="Paused", expression="* * * * *")
        cfg.next_run = datetime.utcnow() - timedelta(minutes=1)
        mgr.pause(cfg.trigger_id)

        assert mgr.should_run(cfg.trigger_id) is False

    def test_should_run_max_runs_exhausted(self):
        mgr = CronTriggerManager()
        cfg = mgr.register_schedule(workflow_id="wf-1", name="Limited", expression="* * * * *", max_runs=3)
        cfg.next_run = datetime.utcnow() - timedelta(minutes=1)
        cfg.run_count = 3

        assert mgr.should_run(cfg.trigger_id) is False

    def test_record_run_updates_state(self):
        mgr = CronTriggerManager()
        cfg = mgr.register_schedule(workflow_id="wf-1", name="Test", expression="* * * * *")

        updated = mgr.record_run(cfg.trigger_id)
        assert updated.run_count == 1
        assert updated.last_run is not None
        assert updated.next_run is not None
        assert updated.next_run > updated.last_run

    def test_record_run_disables_at_max(self):
        mgr = CronTriggerManager()
        cfg = mgr.register_schedule(workflow_id="wf-1", name="Once", expression="* * * * *", max_runs=1)

        updated = mgr.record_run(cfg.trigger_id)
        assert updated.run_count == 1
        assert updated.status == TriggerStatus.DISABLED
        assert updated.next_run is None

    def test_record_run_unknown_raises(self):
        mgr = CronTriggerManager()
        with pytest.raises(KeyError):
            mgr.record_run("nonexistent")

    def test_get_due_triggers(self):
        mgr = CronTriggerManager()
        due_cfg = mgr.register_schedule(workflow_id="wf-due", name="Due", expression="* * * * *")
        due_cfg.next_run = datetime.utcnow() - timedelta(minutes=1)

        future_cfg = mgr.register_schedule(workflow_id="wf-future", name="Future", expression="* * * * *")
        future_cfg.next_run = datetime.utcnow() + timedelta(hours=1)

        paused_cfg = mgr.register_schedule(workflow_id="wf-paused", name="Paused", expression="* * * * *")
        paused_cfg.next_run = datetime.utcnow() - timedelta(minutes=1)
        mgr.pause(paused_cfg.trigger_id)

        due = mgr.get_due_triggers()
        due_ids = {c.trigger_id for c in due}
        assert due_cfg.trigger_id in due_ids
        assert future_cfg.trigger_id not in due_ids
        assert paused_cfg.trigger_id not in due_ids

    # --- Real scheduler loop ---

    async def test_scheduler_loop_fires_due_trigger(self):
        """Start real scheduler, set a trigger as due, verify callback fires."""
        mgr = CronTriggerManager()
        cfg = mgr.register_schedule(
            workflow_id="wf-scheduled", name="Fire Me",
            expression="* * * * *", params={"report": "daily"},
        )
        # Force next_run to the past so it fires immediately
        cfg.next_run = datetime.utcnow() - timedelta(minutes=1)

        fired_events = []

        async def on_trigger(event):
            fired_events.append(event)

        await mgr.start_scheduler(on_trigger)

        # Wait for the scheduler to tick and fire
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            await asyncio.sleep(0.05)
            if len(fired_events) > 0:
                break

        await mgr.stop_scheduler()

        assert len(fired_events) >= 1
        event = fired_events[0]
        assert event.workflow_id == "wf-scheduled"
        assert event.trigger_type == TriggerType.CRON
        assert event.payload == {"report": "daily"}

        # run_count should have been incremented
        updated = mgr.get(cfg.trigger_id)
        assert updated.run_count >= 1

    async def test_scheduler_loop_stop_gracefully(self):
        """Start and stop the scheduler — no hanging."""
        mgr = CronTriggerManager()
        mgr.register_schedule(workflow_id="wf-1", name="Idle", expression="0 0 1 1 *")

        async def noop(event):
            pass

        await mgr.start_scheduler(noop)
        # Immediately stop
        await mgr.stop_scheduler()
        assert mgr._running is False

    async def test_scheduler_respects_max_runs(self):
        """A one-shot trigger fires once then gets disabled."""
        mgr = CronTriggerManager()
        cfg = mgr.register_schedule(
            workflow_id="wf-oneshot", name="One Shot",
            expression="* * * * *", max_runs=1,
        )
        cfg.next_run = datetime.utcnow() - timedelta(minutes=1)

        fired = []

        async def on_trigger(event):
            fired.append(event)

        await mgr.start_scheduler(on_trigger)

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            await asyncio.sleep(0.05)
            if len(fired) > 0:
                break

        await mgr.stop_scheduler()

        assert len(fired) == 1
        assert mgr.get(cfg.trigger_id).status == TriggerStatus.DISABLED

    def test_free_tier_raises_license_error(self, free_tier_license):
        with pytest.raises(LicenseError):
            CronTriggerManager()
