"""
Unit tests for core.session_reaper — the idle-timeout sweep shared by all
three transports (STDIO MCP, HTTP MCP, plain REST).

Pure async unit tests against fake session objects; no real browser, no
real sleeping (reap_stale_sessions is tested directly, not through the
interval loop).
"""
import asyncio
import time

import pytest

from core.session_reaper import (
    idle_timeout_s,
    reap_stale_sessions,
    reaper_loop,
    touch_session,
    untrack_session,
)


class FakeBrowser:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class FakeDebugger:
    def __init__(self):
        self.detached = False

    async def detach(self):
        self.detached = True


class TestTouchAndUntrack:
    def test_touch_session_records_timestamp(self):
        activity = {}
        before = time.time()
        touch_session(activity, "sess-1")
        after = time.time()
        assert before <= activity["sess-1"] <= after

    def test_touch_session_noop_for_falsy_id(self):
        activity = {}
        touch_session(activity, None)
        touch_session(activity, "")
        assert activity == {}

    def test_untrack_session_removes_entry(self):
        activity = {"sess-1": time.time()}
        untrack_session(activity, "sess-1")
        assert "sess-1" not in activity

    def test_untrack_session_noop_for_missing_id(self):
        activity = {}
        untrack_session(activity, "does-not-exist")  # must not raise
        assert activity == {}


class TestIdleTimeoutS:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("FLYTO_SESSION_IDLE_TIMEOUT_S", raising=False)
        assert idle_timeout_s() == 1800.0

    def test_reads_env_override(self, monkeypatch):
        monkeypatch.setenv("FLYTO_SESSION_IDLE_TIMEOUT_S", "120")
        assert idle_timeout_s() == 120.0

    def test_falls_back_on_invalid_value(self, monkeypatch):
        monkeypatch.setenv("FLYTO_SESSION_IDLE_TIMEOUT_S", "not-a-number")
        assert idle_timeout_s() == 1800.0


class TestReapStaleSessions:
    async def test_fresh_session_is_not_reaped(self):
        browser = FakeBrowser()
        browser_sessions = {"b1": browser}
        activity = {"b1": time.time()}

        await reap_stale_sessions(browser_sessions, {}, activity, timeout_s=1800)

        assert browser.closed is False
        assert "b1" in browser_sessions
        assert "b1" in activity

    async def test_stale_browser_session_is_closed_and_dropped(self):
        browser = FakeBrowser()
        browser_sessions = {"b1": browser}
        activity = {"b1": time.time() - 9999}

        await reap_stale_sessions(browser_sessions, {}, activity, timeout_s=1800)

        assert browser.closed is True
        assert "b1" not in browser_sessions
        assert "b1" not in activity

    async def test_stale_debugger_session_is_detached_and_dropped(self):
        debugger = FakeDebugger()
        debugger_sessions = {"d1": debugger}
        activity = {"d1": time.time() - 9999}

        await reap_stale_sessions({}, debugger_sessions, activity, timeout_s=1800)

        assert debugger.detached is True
        assert "d1" not in debugger_sessions
        assert "d1" not in activity

    async def test_session_with_no_activity_entry_is_left_alone(self):
        # Absence of activity data is not evidence of staleness.
        browser = FakeBrowser()
        browser_sessions = {"b1": browser}

        await reap_stale_sessions(browser_sessions, {}, {}, timeout_s=1800)

        assert browser.closed is False
        assert "b1" in browser_sessions

    async def test_close_failure_is_swallowed_and_session_still_dropped(self):
        class BrokenBrowser:
            async def close(self):
                raise RuntimeError("boom")

        browser_sessions = {"b1": BrokenBrowser()}
        activity = {"b1": time.time() - 9999}

        await reap_stale_sessions(browser_sessions, {}, activity, timeout_s=1800)  # must not raise

        assert "b1" not in browser_sessions
        assert "b1" not in activity

    async def test_mixed_fresh_and_stale_sessions(self):
        fresh_browser = FakeBrowser()
        stale_browser = FakeBrowser()
        browser_sessions = {"fresh": fresh_browser, "stale": stale_browser}
        activity = {"fresh": time.time(), "stale": time.time() - 9999}

        await reap_stale_sessions(browser_sessions, {}, activity, timeout_s=1800)

        assert fresh_browser.closed is False
        assert stale_browser.closed is True
        assert "fresh" in browser_sessions
        assert "stale" not in browser_sessions


class TestReaperLoop:
    async def test_loop_sweeps_on_interval_and_stops_on_cancel(self):
        browser = FakeBrowser()
        browser_sessions = {"b1": browser}
        activity = {"b1": time.time() - 9999}

        task = asyncio.create_task(
            reaper_loop(browser_sessions, {}, activity, interval_s=0.01, timeout_s=1800)
        )
        await asyncio.sleep(0.05)  # let at least one sweep run
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        assert browser.closed is True
        assert browser_sessions == {}

    async def test_loop_exits_cleanly_on_cancel_with_no_sessions(self):
        # reaper_loop swallows CancelledError internally for a clean shutdown,
        # so the task completes normally rather than reporting cancelled().
        task = asyncio.create_task(reaper_loop({}, {}, {}, interval_s=0.01))
        await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert task.done()
        assert task.exception() is None
