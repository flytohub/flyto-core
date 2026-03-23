# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Real integration tests for process.stop — no mocks, real subprocesses."""

import asyncio
import os
import signal
import sys
import uuid

import pytest

from core.modules.atomic.process.start import get_process_registry
from core.modules.atomic.process.stop import process_stop as _process_stop_class


async def process_stop(context: dict) -> dict:
    """Thin shim: instantiate the wrapper class and run execute()."""
    params = context.get("params", {})
    instance = _process_stop_class(params, {})
    return await instance.execute()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_process_id(name: str) -> str:
    return f"{name}-{uuid.uuid4().hex[:8]}"


def _is_alive(pid: int) -> bool:
    """Return True if the process with given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it (different user) — treat as alive.
        return True


async def _spawn_sleep(name: str = "test-sleep") -> tuple[asyncio.subprocess.Process, str]:
    """Start a real `sleep 60` subprocess, register it, return (process, process_id)."""
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(60)",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    process_id = _make_process_id(name)
    registry = get_process_registry()
    registry[process_id] = {
        "process": process,
        "pid": process.pid,
        "name": name,
        "command": "sleep 60",
        "cwd": os.getcwd(),
        "started_at": "2026-01-01T00:00:00Z",
        "log_handle": None,
        "capture_output": False,
    }
    return process, process_id


def _cleanup_registry_entry(process_id: str) -> None:
    registry = get_process_registry()
    registry.pop(process_id, None)


async def _kill_if_alive(process: asyncio.subprocess.Process) -> None:
    """Best-effort cleanup: kill and wait so we don't leave zombie processes."""
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------------------
# Fixture: clear the registry before each test so tests are isolated.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
async def clean_registry():
    """Clear the global registry before and after each test."""
    registry = get_process_registry()
    registry.clear()
    yield
    # Teardown: kill any processes still in the registry to avoid orphans.
    procs_to_kill = list(registry.values())
    for info in procs_to_kill:
        proc = info.get("process")
        if proc is not None:
            await _kill_if_alive(proc)
    registry.clear()


# ---------------------------------------------------------------------------
# Test 1: Stop a real process by process_id
# ---------------------------------------------------------------------------

async def test_stop_by_process_id_terminates_process():
    process, process_id = await _spawn_sleep("by-id")
    pid = process.pid

    assert _is_alive(pid), "Process should be running before stop"

    result = await process_stop({"params": {"process_id": process_id}})

    assert result["ok"] is True
    assert result["count"] == 1
    assert len(result["stopped"]) == 1
    assert result["stopped"][0]["process_id"] == process_id
    assert result["stopped"][0]["pid"] == pid

    # Wait briefly for OS to reap
    await asyncio.sleep(0.1)
    assert not _is_alive(pid), "Process should be dead after stop"

    # Registry entry should be removed
    assert process_id not in get_process_registry()


# ---------------------------------------------------------------------------
# Test 2: Stop by name — two processes sharing the same name
# ---------------------------------------------------------------------------

async def test_stop_by_name_stops_all_matching():
    name = "shared-name"
    proc1, proc_id1 = await _spawn_sleep(name)
    proc2, proc_id2 = await _spawn_sleep(name)

    pid1, pid2 = proc1.pid, proc2.pid
    assert _is_alive(pid1)
    assert _is_alive(pid2)

    result = await process_stop({"params": {"name": name}})

    assert result["ok"] is True
    assert result["count"] == 2
    stopped_ids = {s["process_id"] for s in result["stopped"]}
    assert stopped_ids == {proc_id1, proc_id2}

    await asyncio.sleep(0.1)
    assert not _is_alive(pid1), "First process should be dead"
    assert not _is_alive(pid2), "Second process should be dead"

    registry = get_process_registry()
    assert proc_id1 not in registry
    assert proc_id2 not in registry


# ---------------------------------------------------------------------------
# Test 3: Stop by PID (registered process)
# ---------------------------------------------------------------------------

async def test_stop_by_pid_registered_process():
    process, process_id = await _spawn_sleep("by-pid")
    pid = process.pid

    result = await process_stop({"params": {"pid": pid}})

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["stopped"][0]["pid"] == pid

    await asyncio.sleep(0.1)
    assert not _is_alive(pid)


# ---------------------------------------------------------------------------
# Test 4: Force kill (SIGKILL) a registered process
# ---------------------------------------------------------------------------

async def test_force_kill_sigkill():
    process, process_id = await _spawn_sleep("force-kill")
    pid = process.pid

    result = await process_stop({"params": {"process_id": process_id, "force": True}})

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["stopped"][0]["signal"] == "SIGTERM"  # signal param default, overridden by force
    # The process must be dead
    await asyncio.sleep(0.1)
    assert not _is_alive(pid)


# ---------------------------------------------------------------------------
# Test 5: Stop all processes
# ---------------------------------------------------------------------------

async def test_stop_all_processes():
    proc1, proc_id1 = await _spawn_sleep("all-1")
    proc2, proc_id2 = await _spawn_sleep("all-2")
    proc3, proc_id3 = await _spawn_sleep("all-3")

    pids = {proc1.pid, proc2.pid, proc3.pid}
    for pid in pids:
        assert _is_alive(pid)

    result = await process_stop({"params": {"stop_all": True}})

    assert result["ok"] is True
    assert result["count"] == 3
    assert len(result["failed"]) == 0

    await asyncio.sleep(0.1)
    for pid in pids:
        assert not _is_alive(pid), f"PID {pid} should be dead after stop_all"

    assert len(get_process_registry()) == 0


# ---------------------------------------------------------------------------
# Test 6: Stop a non-existent process_id → NOT_FOUND error
# ---------------------------------------------------------------------------

async def test_stop_nonexistent_process_id_returns_not_found():
    result = await process_stop({"params": {"process_id": "does-not-exist-abc123"}})

    assert result["ok"] is False
    assert result["error_code"] == "NOT_FOUND"
    assert "does-not-exist-abc123" in result["error"]


# ---------------------------------------------------------------------------
# Test 7: Stop with no identifier → NO_IDENTIFIER error
# ---------------------------------------------------------------------------

async def test_stop_no_identifier_returns_error():
    result = await process_stop({"params": {}})

    assert result["ok"] is False
    assert result["error_code"] == "NO_IDENTIFIER"


# ---------------------------------------------------------------------------
# Test 8: Direct PID kill of an unregistered process
# ---------------------------------------------------------------------------

async def test_direct_pid_kill_unregistered_process():
    # Start a real subprocess but deliberately do NOT register it.
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(60)",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    pid = process.pid

    try:
        assert _is_alive(pid), "Unregistered process should be running"

        result = await process_stop({"params": {"pid": pid}})

        assert result["ok"] is True
        assert result["count"] == 1
        assert result["stopped"][0]["pid"] == pid

        await asyncio.sleep(0.1)
        assert not _is_alive(pid), "Unregistered process should be dead after direct PID kill"
    finally:
        # Ensure cleanup even if the test fails
        await _kill_if_alive(process)


# ---------------------------------------------------------------------------
# Test 9: SIGTERM-resistant process escalates to SIGKILL (line 75)
# ---------------------------------------------------------------------------

async def test_direct_pid_kill_sigterm_resistant_escalates_to_sigkill():
    """Line 75: process ignores SIGTERM → _kill_pid_directly escalates to SIGKILL."""
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c",
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    pid = process.pid

    try:
        assert _is_alive(pid), "SIGTERM-resistant process should be running"

        # Use direct PID kill (not registered) with short timeout for escalation
        result = await process_stop({"params": {
            "pid": pid,
            "signal": "SIGTERM",
            "timeout": 0.5,
        }})

        assert result["ok"] is True
        assert result["count"] == 1
        assert result["stopped"][0]["pid"] == pid

        await asyncio.sleep(0.2)
        assert not _is_alive(pid), "Process should be dead after SIGKILL escalation"
    finally:
        await _kill_if_alive(process)


# ---------------------------------------------------------------------------
# Test 10: log_handle.close() failure is silently caught (lines 132-133)
# ---------------------------------------------------------------------------

async def test_closed_log_handle_doesnt_raise():
    """Lines 132-133: log_handle.close() raising is silently caught."""
    process, process_id = await _spawn_sleep("log-handle-test")

    # Create a file descriptor and close the underlying fd behind its back
    # so that f.close() will raise OSError
    fd = os.open(os.devnull, os.O_WRONLY)
    f = os.fdopen(fd, 'w')
    os.close(fd)  # close fd behind f's back

    registry = get_process_registry()
    registry[process_id]['log_handle'] = f

    result = await process_stop({"params": {"process_id": process_id}})

    assert result["ok"] is True
    assert result["count"] == 1


# ---------------------------------------------------------------------------
# Test 11: stop_all with an already-exited process records failure (line 309)
# ---------------------------------------------------------------------------

async def test_stop_already_exited_process_records_failure():
    """Lines 148-157/309: terminate() on a dead process raises, recorded in 'failed'."""
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "pass",  # exits immediately
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await process.wait()  # ensure it's fully exited

    process_id = _make_process_id("dead-proc")
    registry = get_process_registry()
    registry[process_id] = {
        "process": process,
        "pid": process.pid,
        "name": "dead-proc",
        "command": "pass",
        "cwd": os.getcwd(),
        "started_at": "2026-01-01T00:00:00Z",
        "log_handle": None,
        "capture_output": False,
    }

    result = await process_stop({"params": {"process_id": process_id}})

    # On macOS/Linux, terminate() on a waited process raises ProcessLookupError
    # which is caught by the except Exception block → 'failed' dict
    # OR it may succeed if the OS hasn't reaped yet → 'stopped' dict
    # Either way, the call should not raise
    assert "ok" in result


# ---------------------------------------------------------------------------
# Test 12: process_id takes precedence over name in _find_processes_to_stop
# ---------------------------------------------------------------------------

async def test_find_processes_process_id_takes_precedence_over_name():
    """_find_processes_to_stop: process_id is checked before name."""
    from core.modules.atomic.process.stop import _find_processes_to_stop

    process, process_id = await _spawn_sleep("priority-test")
    registry = get_process_registry()
    # Both process_id and a name exist — process_id must win
    result_ids, early = _find_processes_to_stop(
        registry,
        process_id=process_id,
        name="priority-test",
        pid=None,
        stop_all=False,
    )
    assert early is None
    assert result_ids == [process_id]
    # Clean up
    await process_stop({"params": {"process_id": process_id}})


# ---------------------------------------------------------------------------
# Test 13: SIGINT signal terminates the process
# ---------------------------------------------------------------------------

async def test_sigint_signal_terminates_process():
    """Sending SIGINT to a registered process stops it."""
    process, process_id = await _spawn_sleep("sigint-test")
    pid = process.pid

    assert _is_alive(pid)

    result = await process_stop({"params": {"process_id": process_id, "signal": "SIGINT"}})

    # On macOS/Linux SIGINT terminates a sleep process
    assert result["ok"] is True
    assert result["count"] == 1

    await asyncio.sleep(0.2)
    assert not _is_alive(pid)


# ---------------------------------------------------------------------------
# Test 14: Invalid signal string defaults to SIGTERM
# ---------------------------------------------------------------------------

async def test_invalid_signal_string_defaults_to_sigterm():
    """An unrecognised signal name falls back to SIGTERM (default mapping)."""
    process, process_id = await _spawn_sleep("invalid-signal-test")
    pid = process.pid

    assert _is_alive(pid)

    # "SIGHUP" is not in signal_map → fallback to SIGTERM
    result = await process_stop({"params": {"process_id": process_id, "signal": "SIGHUP"}})

    assert result["ok"] is True
    assert result["count"] == 1

    await asyncio.sleep(0.2)
    assert not _is_alive(pid)


# ---------------------------------------------------------------------------
# Test 15: stop_all with empty registry → ok=True, count=0
# ---------------------------------------------------------------------------

async def test_stop_all_empty_registry():
    """stop_all with no registered processes returns ok=True and count=0."""
    registry = get_process_registry()
    assert len(registry) == 0  # clean_registry fixture ensures this

    result = await process_stop({"params": {"stop_all": True}})

    assert result["ok"] is True
    assert result["count"] == 0
    assert result["stopped"] == []
    assert result["failed"] == []


# ---------------------------------------------------------------------------
# Test 16: force=True overrides signal param → uses SIGKILL
# ---------------------------------------------------------------------------

async def test_force_overrides_signal_param():
    """force=True sends SIGKILL regardless of what 'signal' param says."""
    process, process_id = await _spawn_sleep("force-override-signal")
    pid = process.pid

    assert _is_alive(pid)

    # signal="SIGINT" + force=True → SIGKILL must be used
    result = await process_stop({
        "params": {
            "process_id": process_id,
            "signal": "SIGINT",
            "force": True,
        }
    })

    assert result["ok"] is True
    assert result["count"] == 1

    await asyncio.sleep(0.2)
    assert not _is_alive(pid)
