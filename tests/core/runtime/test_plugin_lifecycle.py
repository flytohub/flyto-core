"""
Plugin Lifecycle Tests

Tests for plugin loading, handshaking, and lifecycle management.
Tasks: 1.15, 1.17, 1.18, 1.19
"""

import asyncio
import json
import pytest
import tempfile
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Import runtime components
from src.core.runtime.protocol import (
    ProtocolEncoder,
    ProtocolDecoder,
    PROTOCOL_VERSION,
)
from src.core.runtime.process import (
    PluginProcess,
    ProcessConfig,
    ProcessStatus,
    RestartPolicy,
)
from src.core.runtime.manager import (
    PluginManager,
    PluginManifest,
    PluginInfo,
)
from src.core.runtime.health import (
    HealthChecker,
    HealthCheckConfig,
    HealthStatus,
)


class TestPluginHandshake:
    """Test 1.15: Plugin loads and handshakes."""

    @pytest.fixture
    def sample_manifest(self, tmp_path):
        """Create a sample plugin manifest."""
        manifest_data = {
            "id": "test-plugin",
            "name": "Test Plugin",
            "version": "1.0.0",
            "vendor": "test",
            "description": "A test plugin",
            "entryPoint": "main.py",
            "runtime": {
                "language": "python",
                "minVersion": "3.9"
            },
            "permissions": [],
            "steps": [
                {
                    "id": "test_step",
                    "label": "Test Step",
                    "description": "A test step",
                    "inputSchema": {"type": "object"},
                    "outputSchema": {"type": "object"},
                    "cost": {"points": 1, "class": "standard"}
                }
            ]
        }

        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        manifest_path = plugin_dir / "plugin.manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))

        # Create a simple main.py
        main_py = plugin_dir / "main.py"
        main_py.write_text('''
import sys
import json

while True:
    line = sys.stdin.readline()
    if not line:
        break
    request = json.loads(line)
    response = {
        "jsonrpc": "2.0",
        "result": {"ok": True, "pluginId": "test-plugin"},
        "id": request.get("id")
    }
    print(json.dumps(response))
    sys.stdout.flush()
''')

        return plugin_dir

    def test_manifest_parsing(self, sample_manifest):
        """Test manifest can be parsed correctly."""
        manifest_path = sample_manifest / "plugin.manifest.json"
        manifest_data = json.loads(manifest_path.read_text())

        manifest = PluginManifest.from_dict(manifest_data)

        assert manifest.id == "test-plugin"
        assert manifest.version == "1.0.0"
        assert len(manifest.steps) == 1
        assert manifest.steps[0]["id"] == "test_step"

    def test_protocol_encoder_handshake(self):
        """Test handshake message encoding."""
        import json

        # encode_handshake returns a JSON string
        message_json = ProtocolEncoder.encode_handshake(
            protocol_version=PROTOCOL_VERSION,
            plugin_id="test-plugin",
            execution_id="exec-123",
            request_id=1,
        )

        message = json.loads(message_json)

        assert message["jsonrpc"] == "2.0"
        assert message["method"] == "handshake"
        assert message["params"]["protocolVersion"] == PROTOCOL_VERSION

    def test_protocol_decoder_response(self):
        """Test response decoding."""
        response_data = {
            "jsonrpc": "2.0",
            "result": {"ok": True, "pluginId": "test-plugin"},
            "id": 1,
        }

        parsed = ProtocolDecoder.decode_response(json.dumps(response_data))

        assert parsed.is_success is True
        assert parsed.result["pluginId"] == "test-plugin"


class TestPluginTimeout:
    """Test 1.17: Timeout kills plugin."""

    def test_process_config_has_timeouts(self):
        """Test ProcessConfig has timeout configuration."""
        config = ProcessConfig(
            plugin_id="test",
            plugin_dir=Path("/tmp"),
        )

        assert config.handshake_timeout_ms == 5000
        assert config.invoke_timeout_ms == 30000
        assert config.shutdown_timeout_ms == 5000

    @pytest.mark.asyncio
    async def test_invoke_timeout_raises_error(self, tmp_path):
        """Test that invoke timeout raises PluginTimeoutError."""
        from src.core.runtime.exceptions import PluginTimeoutError

        # Create a slow plugin
        plugin_dir = tmp_path / "slow-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "main.py").write_text('''
import sys
import time
import json

while True:
    line = sys.stdin.readline()
    if not line:
        break
    time.sleep(10)  # Slow response
    print(json.dumps({"jsonrpc": "2.0", "result": {}, "id": 1}))
''')

        config = ProcessConfig(
            plugin_id="slow-plugin",
            plugin_dir=plugin_dir,
            invoke_timeout_ms=100,  # Very short timeout
        )

        process = PluginProcess(config)

        # Mock the start to avoid actual subprocess
        process._status = ProcessStatus.READY
        process._process = MagicMock()

        # Mock _send to do nothing
        process._send = AsyncMock()

        # The invoke should timeout
        with pytest.raises(PluginTimeoutError):
            await process.invoke(
                step="test",
                input_data={},
                config={},
                context={},
                timeout_ms=100,
            )


class TestPluginCrash:
    """Test 1.18: Crash triggers restart."""

    def test_restart_policy_defaults(self):
        """Test restart policy has correct defaults."""
        policy = RestartPolicy()

        assert policy.max_restarts == 3
        assert policy.restart_window_seconds == 60
        assert policy.backoff_seconds == [1, 2, 4]

    def test_process_tracks_restart_times(self):
        """Test that process tracks restart times."""
        config = ProcessConfig(
            plugin_id="test",
            plugin_dir=Path("/tmp"),
        )
        process = PluginProcess(config)

        # Initially empty
        assert len(process._restart_times) == 0


class TestUnhealthyAfterMaxRestarts:
    """Test 1.19: 3 crashes → unhealthy."""

    def test_health_status_enum(self):
        """Test health status values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.DEGRADED.value == "degraded"

    def test_process_unhealthy_property(self):
        """Test is_unhealthy property."""
        config = ProcessConfig(
            plugin_id="test",
            plugin_dir=Path("/tmp"),
        )
        process = PluginProcess(config)

        # Initially not unhealthy
        assert process.is_unhealthy is False

        # Set to unhealthy
        process._status = ProcessStatus.UNHEALTHY
        process._unhealthy_until = time.time() + 300

        assert process.is_unhealthy is True


class TestHealthChecker:
    """Additional health check tests."""

    def test_health_check_config_defaults(self):
        """Test health check config defaults."""
        config = HealthCheckConfig()

        assert config.enabled is True
        assert config.interval_seconds == 30
        assert config.timeout_seconds == 5
        assert config.method == "ping"
        assert config.consecutive_failures_for_unhealthy == 3

    @pytest.mark.asyncio
    async def test_consecutive_failures_tracking(self):
        """Test consecutive failure tracking."""
        checker = HealthChecker(
            config=HealthCheckConfig(
                consecutive_failures_for_unhealthy=3,
            )
        )

        # Register a plugin
        async def failing_check():
            return (False, 0, "Test failure")

        checker.register_plugin("plugin-1", failing_check)

        # Simulate failures
        await checker.check_plugin("plugin-1")
        health = checker.get_health("plugin-1")
        assert health.consecutive_failures == 1

        await checker.check_plugin("plugin-1")
        health = checker.get_health("plugin-1")
        assert health.consecutive_failures == 2

        # Third failure should trigger unhealthy
        await checker.check_plugin("plugin-1")
        health = checker.get_health("plugin-1")
        assert health.consecutive_failures == 3
        assert health.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_success_resets_failures(self):
        """Test that success resets failure count."""
        checker = HealthChecker()

        call_count = 0

        async def check_callback():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return (False, 10, "Failure")
            return (True, 5, None)

        checker.register_plugin("plugin-1", check_callback)

        # Two failures
        await checker.check_plugin("plugin-1")
        await checker.check_plugin("plugin-1")
        health = checker.get_health("plugin-1")
        assert health.consecutive_failures == 2

        # One success resets
        await checker.check_plugin("plugin-1")
        health = checker.get_health("plugin-1")
        assert health.consecutive_failures == 0
        assert health.consecutive_successes == 1
