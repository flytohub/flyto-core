"""Tests for process.stop module helpers."""

import asyncio
import signal
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.modules.atomic.process.stop import (
    _find_processes_to_stop,
    _kill_pid_directly,
    _stop_registered_process,
)


# ── _find_processes_to_stop ──

class TestFindProcessesToStop:
    def setup_method(self):
        self.registry = {
            "proc-1": {"name": "server", "pid": 100},
            "proc-2": {"name": "worker", "pid": 200},
            "proc-3": {"name": "server", "pid": 300},
        }

    def test_stop_all(self):
        procs, early = _find_processes_to_stop(self.registry, None, None, None, True)
        assert set(procs) == {"proc-1", "proc-2", "proc-3"}
        assert early is None

    def test_by_process_id_found(self):
        procs, early = _find_processes_to_stop(self.registry, "proc-2", None, None, False)
        assert procs == ["proc-2"]
        assert early is None

    def test_by_process_id_not_found(self):
        procs, early = _find_processes_to_stop(self.registry, "proc-999", None, None, False)
        assert procs == []
        assert early is not None
        assert early["ok"] is False
        assert early["error_code"] == "NOT_FOUND"

    def test_by_name(self):
        procs, early = _find_processes_to_stop(self.registry, None, "server", None, False)
        assert set(procs) == {"proc-1", "proc-3"}
        assert early is None

    def test_by_name_not_found(self):
        procs, early = _find_processes_to_stop(self.registry, None, "nonexistent", None, False)
        assert procs == []
        assert early is None

    def test_by_pid(self):
        procs, early = _find_processes_to_stop(self.registry, None, None, 200, False)
        assert procs == ["proc-2"]
        assert early is None

    def test_by_pid_not_in_registry(self):
        procs, early = _find_processes_to_stop(self.registry, None, None, 999, False)
        assert procs == []
        assert early is None

    def test_no_identifier(self):
        procs, early = _find_processes_to_stop(self.registry, None, None, None, False)
        assert procs == []
        assert early is None


# ── _kill_pid_directly ──

class TestKillPidDirectly:
    async def test_successful_kill(self):
        with patch("core.modules.atomic.process.stop.os.kill") as mock_kill:
            mock_kill.side_effect = [None, ProcessLookupError()]  # kill, then check=dead
            result = await _kill_pid_directly(12345, signal.SIGTERM, "SIGTERM", 0.01)
        assert result["ok"] is True
        assert result["count"] == 1
        assert result["stopped"][0]["pid"] == 12345

    async def test_sigkill_no_wait(self):
        with patch("core.modules.atomic.process.stop.os.kill") as mock_kill:
            mock_kill.return_value = None
            result = await _kill_pid_directly(12345, signal.SIGKILL, "SIGKILL", 0.01)
        assert result["ok"] is True
        # SIGKILL should only call kill once (no graceful wait check)
        assert mock_kill.call_count == 1

    async def test_process_not_found(self):
        with patch("core.modules.atomic.process.stop.os.kill", side_effect=ProcessLookupError()):
            result = await _kill_pid_directly(99999, signal.SIGTERM, "SIGTERM", 0.01)
        assert result["ok"] is False
        assert result["error_code"] == "NOT_FOUND"

    async def test_permission_error(self):
        with patch("core.modules.atomic.process.stop.os.kill", side_effect=PermissionError("denied")):
            result = await _kill_pid_directly(1, signal.SIGTERM, "SIGTERM", 0.01)
        assert result["ok"] is False
        assert result["error_code"] == "KILL_FAILED"


# ── _stop_registered_process ──

class TestStopRegisteredProcess:
    def _make_mock_process(self, returncode=0):
        proc = AsyncMock()
        proc.pid = 42
        proc.returncode = returncode
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        proc.wait = AsyncMock()
        return proc

    async def test_graceful_stop(self):
        proc = self._make_mock_process()
        registry = {"p1": {"process": proc, "name": "test"}}

        result = await _stop_registered_process(
            "p1", registry["p1"], signal.SIGTERM, "SIGTERM", 5, registry,
        )
        assert "stopped" in result
        assert result["stopped"]["pid"] == 42
        assert result["stopped"]["name"] == "test"
        proc.terminate.assert_called_once()
        assert "p1" not in registry

    async def test_force_kill(self):
        proc = self._make_mock_process()
        registry = {"p1": {"process": proc, "name": "test"}}

        result = await _stop_registered_process(
            "p1", registry["p1"], signal.SIGKILL, "SIGKILL", 5, registry,
        )
        assert "stopped" in result
        proc.kill.assert_called_once()

    async def test_timeout_force_kills(self):
        proc = self._make_mock_process()
        proc.wait = AsyncMock(side_effect=[asyncio.TimeoutError(), None])
        registry = {"p1": {"process": proc, "name": "test"}}

        result = await _stop_registered_process(
            "p1", registry["p1"], signal.SIGTERM, "SIGTERM", 0.01, registry,
        )
        assert "stopped" in result
        proc.kill.assert_called_once()

    async def test_no_process_object(self):
        registry = {"p1": {"name": "test"}}
        result = await _stop_registered_process(
            "p1", registry["p1"], signal.SIGTERM, "SIGTERM", 5, registry,
        )
        assert "failed" in result
        assert "Process object not found" in result["failed"]["error"]

    async def test_exception_during_stop(self):
        proc = self._make_mock_process()
        proc.terminate = MagicMock(side_effect=OSError("broken"))
        registry = {"p1": {"process": proc, "pid": 42, "name": "test"}}

        result = await _stop_registered_process(
            "p1", registry["p1"], signal.SIGTERM, "SIGTERM", 5, registry,
        )
        assert "failed" in result
        assert "broken" in result["failed"]["error"]

    async def test_closes_log_handle(self):
        proc = self._make_mock_process()
        log_handle = MagicMock()
        registry = {"p1": {"process": proc, "name": "test", "log_handle": log_handle}}

        await _stop_registered_process(
            "p1", registry["p1"], signal.SIGTERM, "SIGTERM", 5, registry,
        )
        log_handle.close.assert_called_once()
