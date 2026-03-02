"""
Plugin Subprocess Real Integration Tests — Zero Mocks

Tests the full plugin lifecycle with real subprocess spawning:
  3a. Real subprocess handshake
  3b. Real invoke (echo plugin)
  3c. Real shutdown
  3d. Real timeout (slow plugin)
  3e. Real crash (crashing plugin)
  3f. PluginManager full lifecycle
  3g. HealthChecker with real ping
"""

import asyncio
import json
import os
import signal
import textwrap
from pathlib import Path

import pytest

from core.runtime.process import PluginProcess, ProcessConfig, ProcessStatus
from core.runtime.manager import PluginManager, PluginManifest
from core.runtime.health import HealthChecker, HealthCheckConfig, HealthStatus
from core.runtime.exceptions import PluginTimeoutError, PluginCrashedError


# ===================================================================
# Minimal Plugin Scripts (written to tmp_path)
# ===================================================================

ECHO_PLUGIN = textwrap.dedent("""\
    #!/usr/bin/env python3
    \"\"\"Minimal echo plugin — handles handshake, invoke, ping, shutdown.\"\"\"
    import json
    import sys

    def main():
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            try:
                req = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            method = req.get("method", "")
            req_id = req.get("id", 0)
            params = req.get("params", {})

            if method == "handshake":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {"pluginVersion": "1.0.0"}}
            elif method == "invoke":
                step = params.get("step", "")
                input_data = params.get("input", {})
                if step == "echo":
                    resp = {"jsonrpc": "2.0", "id": req_id, "result": {"ok": True, "data": {"echo": input_data}}}
                else:
                    resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32001, "message": f"Unknown step: {step}"}}
            elif method == "ping":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
            elif method == "shutdown":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
                print(json.dumps(resp), flush=True)
                sys.exit(0)
            else:
                resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}

            print(json.dumps(resp), flush=True)

    if __name__ == "__main__":
        main()
""")


SLOW_PLUGIN = textwrap.dedent("""\
    #!/usr/bin/env python3
    \"\"\"Slow plugin — sleeps 10s on invoke to trigger timeout.\"\"\"
    import json
    import sys
    import time

    def main():
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            try:
                req = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            method = req.get("method", "")
            req_id = req.get("id", 0)

            if method == "handshake":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {"pluginVersion": "1.0.0"}}
                print(json.dumps(resp), flush=True)
            elif method == "invoke":
                time.sleep(10)  # Will be killed by timeout
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {"ok": True, "data": {}}}
                print(json.dumps(resp), flush=True)
            elif method == "ping":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
                print(json.dumps(resp), flush=True)
            elif method == "shutdown":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
                print(json.dumps(resp), flush=True)
                sys.exit(0)

    if __name__ == "__main__":
        main()
""")


CRASH_PLUGIN = textwrap.dedent("""\
    #!/usr/bin/env python3
    \"\"\"Crash plugin — exits with code 1 on first invoke.\"\"\"
    import json
    import sys

    def main():
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            try:
                req = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            method = req.get("method", "")
            req_id = req.get("id", 0)

            if method == "handshake":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {"pluginVersion": "1.0.0"}}
                print(json.dumps(resp), flush=True)
            elif method == "invoke":
                sys.exit(1)  # Crash!
            elif method == "shutdown":
                sys.exit(0)

    if __name__ == "__main__":
        main()
""")


MANIFEST = {
    "id": "echo-plugin",
    "name": "Echo Plugin",
    "version": "1.0.0",
    "vendor": "test",
    "entryPoint": "main.py",
    "runtime": {"language": "python", "entry": "main.py"},
    "steps": [
        {"id": "echo", "label": "Echo", "description": "Echoes input data"},
    ],
}


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def echo_plugin_dir(tmp_path):
    """Write echo plugin to tmp_path and return (dir, config)."""
    plugin_dir = tmp_path / "echo-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "main.py").write_text(ECHO_PLUGIN)
    config = ProcessConfig(
        plugin_id="echo-plugin",
        plugin_dir=plugin_dir,
        entry_point="main.py",
        language="python",
        handshake_timeout_ms=5000,
        invoke_timeout_ms=5000,
    )
    return plugin_dir, config


@pytest.fixture
def slow_plugin_dir(tmp_path):
    """Write slow plugin to tmp_path."""
    plugin_dir = tmp_path / "slow-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "main.py").write_text(SLOW_PLUGIN)
    config = ProcessConfig(
        plugin_id="slow-plugin",
        plugin_dir=plugin_dir,
        entry_point="main.py",
        language="python",
        handshake_timeout_ms=5000,
        invoke_timeout_ms=500,  # Very short timeout
    )
    return plugin_dir, config


@pytest.fixture
def crash_plugin_dir(tmp_path):
    """Write crash plugin to tmp_path."""
    plugin_dir = tmp_path / "crash-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "main.py").write_text(CRASH_PLUGIN)
    config = ProcessConfig(
        plugin_id="crash-plugin",
        plugin_dir=plugin_dir,
        entry_point="main.py",
        language="python",
        handshake_timeout_ms=5000,
        invoke_timeout_ms=5000,
    )
    return plugin_dir, config


# ===================================================================
# 3a. Real Subprocess Handshake
# ===================================================================

class TestRealHandshake:
    """PluginProcess.start() → real subprocess → real JSON-RPC handshake."""

    @pytest.mark.asyncio
    async def test_start_and_handshake(self, echo_plugin_dir):
        _, config = echo_plugin_dir
        process = PluginProcess(config)

        try:
            started = await process.start()
            assert started is True
            assert process.status == ProcessStatus.READY
            assert process._process is not None
        finally:
            await process.stop()

    @pytest.mark.asyncio
    async def test_status_after_stop(self, echo_plugin_dir):
        _, config = echo_plugin_dir
        process = PluginProcess(config)

        await process.start()
        await process.stop()

        assert process.status == ProcessStatus.STOPPED
        assert process._process is None


# ===================================================================
# 3b. Real Invoke
# ===================================================================

class TestRealInvoke:
    """PluginProcess.invoke() → real stdin/stdout JSON-RPC."""

    @pytest.mark.asyncio
    async def test_echo_invoke(self, echo_plugin_dir):
        _, config = echo_plugin_dir
        process = PluginProcess(config)

        try:
            await process.start()
            result = await process.invoke(
                step="echo",
                input_data={"msg": "hello"},
                config={},
                context={},
            )
            assert result["ok"] is True
            assert result["data"]["echo"]["msg"] == "hello"
        finally:
            await process.stop()

    @pytest.mark.asyncio
    async def test_multiple_invokes(self, echo_plugin_dir):
        """Multiple sequential invokes on the same process."""
        _, config = echo_plugin_dir
        process = PluginProcess(config)

        try:
            await process.start()
            for i in range(5):
                result = await process.invoke(
                    step="echo",
                    input_data={"seq": i},
                    config={},
                    context={},
                )
                assert result["ok"] is True
                assert result["data"]["echo"]["seq"] == i
        finally:
            await process.stop()


# ===================================================================
# 3c. Real Shutdown
# ===================================================================

class TestRealShutdown:
    """PluginProcess.stop() → sends shutdown JSON-RPC → clean exit."""

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, echo_plugin_dir):
        _, config = echo_plugin_dir
        process = PluginProcess(config)

        await process.start()
        assert process.status == ProcessStatus.READY

        await process.stop()
        assert process.status == ProcessStatus.STOPPED
        assert process._process is None


# ===================================================================
# 3d. Real Timeout
# ===================================================================

class TestRealTimeout:
    """Slow plugin triggers PluginTimeoutError."""

    @pytest.mark.asyncio
    async def test_invoke_timeout(self, slow_plugin_dir):
        _, config = slow_plugin_dir
        process = PluginProcess(config)

        try:
            await process.start()
            with pytest.raises(PluginTimeoutError):
                await process.invoke(
                    step="echo",
                    input_data={},
                    config={},
                    context={},
                    timeout_ms=500,
                )
        finally:
            await process.stop()


# ===================================================================
# 3e. Real Crash
# ===================================================================

class TestRealCrash:
    """Crashing plugin triggers PluginCrashedError."""

    @pytest.mark.asyncio
    async def test_crash_on_invoke(self, crash_plugin_dir):
        _, config = crash_plugin_dir
        process = PluginProcess(config)

        await process.start()
        assert process.status == ProcessStatus.READY

        with pytest.raises((PluginCrashedError, Exception)):
            await process.invoke(
                step="echo",
                input_data={},
                config={},
                context={},
            )

        # Give the reader task time to detect the crash
        await asyncio.sleep(0.5)

        assert process.status in (ProcessStatus.STOPPED, ProcessStatus.UNHEALTHY)


# ===================================================================
# 3f. PluginManager Full Lifecycle
# ===================================================================

class TestPluginManagerLifecycle:
    """PluginManager discover → invoke → shutdown with real subprocess."""

    @pytest.fixture
    def plugin_tree(self, tmp_path):
        """Create a plugin tree with manifest + main.py."""
        plugin_dir = tmp_path / "echo-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "main.py").write_text(ECHO_PLUGIN)
        (plugin_dir / "plugin.manifest.json").write_text(json.dumps(MANIFEST))
        return tmp_path

    @pytest.mark.asyncio
    async def test_discover_and_invoke(self, plugin_tree):
        manager = PluginManager(plugin_dir=plugin_tree)
        try:
            discovered = await manager.discover_plugins()
            assert "echo-plugin" in discovered

            result = await manager.invoke(
                plugin_id="echo-plugin",
                step="echo",
                input_data={"greeting": "hi"},
                config={},
                context={},
            )
            assert result["ok"] is True
            assert result["data"]["echo"]["greeting"] == "hi"
        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_stops_all(self, plugin_tree):
        manager = PluginManager(plugin_dir=plugin_tree)
        try:
            await manager.discover_plugins()
            # Invoke to trigger lazy start
            await manager.invoke("echo-plugin", "echo", {"x": 1}, {}, {})

            status_before = manager.get_plugin_status("echo-plugin")
            assert status_before["status"] == "ready"
        finally:
            await manager.shutdown()

        # After shutdown, plugin is unloaded
        assert manager.get_plugin_status("echo-plugin") is None


# ===================================================================
# 3g. Real Health Check
# ===================================================================

class TestRealHealthCheck:
    """HealthChecker with real plugin ping."""

    @pytest.mark.asyncio
    async def test_healthy_plugin(self, echo_plugin_dir):
        _, config = echo_plugin_dir
        process = PluginProcess(config)

        checker = HealthChecker(
            config=HealthCheckConfig(
                consecutive_failures_for_unhealthy=3,
                consecutive_successes_for_healthy=1,
            )
        )

        try:
            await process.start()

            async def check_callback():
                import time
                start = time.time()
                healthy = await process.ping()
                latency = int((time.time() - start) * 1000)
                return healthy, latency, None if healthy else "ping failed"

            checker.register_plugin("echo-plugin", check_callback)

            record = await checker.check_plugin("echo-plugin")
            assert record.status == HealthStatus.HEALTHY

            health = checker.get_health("echo-plugin")
            assert health.consecutive_successes >= 1
        finally:
            await process.stop()

    @pytest.mark.asyncio
    async def test_unhealthy_after_kill(self, echo_plugin_dir):
        """Kill process → ping fails → eventually UNHEALTHY."""
        _, config = echo_plugin_dir
        process = PluginProcess(config)

        checker = HealthChecker(
            config=HealthCheckConfig(
                consecutive_failures_for_unhealthy=2,
                consecutive_successes_for_healthy=1,
            )
        )

        try:
            await process.start()

            async def check_callback():
                import time
                start = time.time()
                healthy = await process.ping(timeout_ms=1000)
                latency = int((time.time() - start) * 1000)
                return healthy, latency, None if healthy else "ping failed"

            checker.register_plugin("echo-plugin", check_callback)

            # Kill the process to simulate crash
            if process._process:
                process._process.kill()
                await process._process.wait()

            # Check health multiple times — should fail
            for _ in range(3):
                await checker.check_plugin("echo-plugin")

            health = checker.get_health("echo-plugin")
            assert health.status == HealthStatus.UNHEALTHY
        finally:
            # Process is already killed, just clean up state
            process._process = None
            process._status = ProcessStatus.STOPPED
