"""
Tests for PluginManager with multi-language manifest support.
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path

import pytest

from core.runtime.exceptions import (
    PluginManagerShutdownError,
    PluginNotFoundError,
    SecurityError,
)
from core.runtime.manager import (
    PluginManager,
    PluginManifest,
    RuntimeConfig,
)
from core.runtime.process import ProcessStatus


class TestRuntimeConfig:
    """Tests for RuntimeConfig dataclass."""

    def test_default_values(self):
        """Test default values."""
        config = RuntimeConfig()
        assert config.language == "python"
        assert config.entry == "main.py"
        assert config.min_flyto_version is None

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "language": "node",
            "entry": "index.js",
            "minFlytoVersion": "2.0.0",
        }
        config = RuntimeConfig.from_dict(data)

        assert config.language == "node"
        assert config.entry == "index.js"
        assert config.min_flyto_version == "2.0.0"

    def test_from_dict_empty(self):
        """Test creating from empty dictionary."""
        config = RuntimeConfig.from_dict({})
        assert config.language == "python"
        assert config.entry == "main.py"

    def test_from_dict_none(self):
        """Test creating from None."""
        config = RuntimeConfig.from_dict(None)
        assert config.language == "python"


class TestPluginManifest:
    """Tests for PluginManifest with runtime section."""

    def test_basic_manifest(self):
        """Test basic manifest parsing."""
        data = {
            "id": "test-plugin",
            "name": "Test Plugin",
            "version": "1.0.0",
            "vendor": "test-vendor",
        }
        manifest = PluginManifest.from_dict(data)

        assert manifest.id == "test-plugin"
        assert manifest.name == "Test Plugin"
        assert manifest.version == "1.0.0"
        assert manifest.runtime.language == "python"

    def test_manifest_with_runtime_section(self):
        """Test manifest with runtime section."""
        data = {
            "id": "node-plugin",
            "name": "Node Plugin",
            "version": "1.0.0",
            "runtime": {
                "language": "node",
                "entry": "dist/index.js",
                "minFlytoVersion": "2.0.0",
            },
        }
        manifest = PluginManifest.from_dict(data)

        assert manifest.runtime.language == "node"
        assert manifest.runtime.entry == "dist/index.js"
        assert manifest.entry_point == "dist/index.js"

    def test_manifest_go_language(self):
        """Test manifest for Go plugin."""
        data = {
            "id": "go-plugin",
            "runtime": {
                "language": "go",
            },
        }
        manifest = PluginManifest.from_dict(data)

        assert manifest.runtime.language == "go"
        # Entry point should be language-specific default
        assert manifest.entry_point == "plugin"

    def test_manifest_java_language(self):
        """Test manifest for Java plugin."""
        data = {
            "id": "java-plugin",
            "runtime": {
                "language": "java",
            },
        }
        manifest = PluginManifest.from_dict(data)

        assert manifest.runtime.language == "java"
        assert manifest.entry_point == "plugin.jar"

    def test_manifest_modules_section(self):
        """Test manifest with modules section (marketplace format)."""
        data = {
            "id": "marketplace-plugin",
            "name": "my-awesome-scraper",
            "version": "1.0.0",
            "runtime": {
                "language": "go",
                "entry": "scraper",
            },
            "modules": [
                {
                    "id": "mycompany.scraper",
                    "label": "Web Scraper",
                    "description": "Scrape any website",
                    "category": "browser",
                },
            ],
        }
        manifest = PluginManifest.from_dict(data)

        assert len(manifest.modules) == 1
        assert manifest.modules[0]["id"] == "mycompany.scraper"

    def test_manifest_name_as_id(self):
        """Test using 'name' field as 'id' for marketplace manifests."""
        data = {
            "name": "my-plugin",  # 'name' instead of 'id'
            "version": "1.0.0",
        }
        # This needs to be handled in discover_plugins, but manifest requires id
        # So we simulate the transformation
        if "id" not in data and "name" in data:
            data["id"] = data["name"]

        manifest = PluginManifest.from_dict(data)
        assert manifest.id == "my-plugin"

    def test_manifest_with_author_as_vendor(self):
        """Test using 'author' field as 'vendor'."""
        data = {
            "id": "test-plugin",
            "author": "dev@flyto2.com",  # 'author' instead of 'vendor'
        }
        manifest = PluginManifest.from_dict(data)
        assert manifest.vendor == "dev@flyto2.com"


class TestPluginManagerDiscovery:
    """Tests for PluginManager plugin discovery."""

    @pytest.fixture
    def plugin_dir(self):
        """Create temporary plugin directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.asyncio
    async def test_discover_json_manifest(self, plugin_dir):
        """Test discovering plugin with JSON manifest."""
        # Create plugin directory
        test_plugin = plugin_dir / "test-plugin"
        test_plugin.mkdir()

        # Create JSON manifest
        manifest = {
            "id": "test-plugin",
            "name": "Test Plugin",
            "version": "1.0.0",
            "entryPoint": "main.py",
        }
        with open(test_plugin / "plugin.manifest.json", "w") as f:
            json.dump(manifest, f)

        # Create entry point
        (test_plugin / "main.py").touch()

        # Discover
        manager = PluginManager(plugin_dir)
        discovered = await manager.discover_plugins()

        assert "test-plugin" in discovered

    @pytest.mark.asyncio
    async def test_discover_yaml_manifest(self, plugin_dir):
        """Test discovering plugin with YAML manifest."""
        pytest.importorskip("yaml")  # Skip if PyYAML not installed

        import yaml

        # Create plugin directory
        node_plugin = plugin_dir / "node-plugin"
        node_plugin.mkdir()

        # Create YAML manifest
        manifest = {
            "id": "node-plugin",
            "name": "Node Plugin",
            "version": "1.0.0",
            "runtime": {
                "language": "node",
                "entry": "index.js",
            },
        }
        with open(node_plugin / "plugin.yaml", "w") as f:
            yaml.dump(manifest, f)

        # Create entry point
        (node_plugin / "index.js").touch()

        # Discover
        manager = PluginManager(plugin_dir)
        discovered = await manager.discover_plugins()

        assert "node-plugin" in discovered

    @pytest.mark.asyncio
    async def test_discover_multiple_languages(self, plugin_dir):
        """Test discovering plugins in multiple languages."""
        # Python plugin
        py_plugin = plugin_dir / "py-plugin"
        py_plugin.mkdir()
        with open(py_plugin / "plugin.manifest.json", "w") as f:
            json.dump({"id": "py-plugin", "entryPoint": "main.py"}, f)
        (py_plugin / "main.py").touch()

        # Node.js plugin
        node_plugin = plugin_dir / "node-plugin"
        node_plugin.mkdir()
        with open(node_plugin / "plugin.manifest.json", "w") as f:
            json.dump({
                "id": "node-plugin",
                "runtime": {"language": "node", "entry": "index.js"},
            }, f)
        (node_plugin / "index.js").touch()

        # Discover
        manager = PluginManager(plugin_dir)
        discovered = await manager.discover_plugins()

        assert "py-plugin" in discovered
        assert "node-plugin" in discovered
        assert len(discovered) == 2

    @pytest.mark.asyncio
    async def test_discovery_rejects_symlink_outside_plugin_root(self, tmp_path):
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        with open(outside / "plugin.manifest.json", "w") as f:
            json.dump({"id": "outside-plugin", "entryPoint": "main.py"}, f)
        (outside / "main.py").touch()
        (plugin_dir / "linked-plugin").symlink_to(outside, target_is_directory=True)

        manager = PluginManager(plugin_dir)

        assert await manager.discover_plugins() == []
        assert manager.get_manifest("outside-plugin") is None


class TestPluginManagerLoading:
    """Tests for PluginManager plugin loading."""

    @pytest.fixture
    def plugin_dir_with_plugins(self):
        """Create plugin directory with test plugins."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)

            # Create Python plugin
            py_plugin = plugin_dir / "py-plugin"
            py_plugin.mkdir()
            with open(py_plugin / "plugin.manifest.json", "w") as f:
                json.dump({
                    "id": "py-plugin",
                    "version": "1.0.0",
                    "entryPoint": "main.py",
                    "steps": [{"id": "execute"}],
                }, f)
            (py_plugin / "main.py").touch()

            # Create Node.js plugin
            node_plugin = plugin_dir / "node-plugin"
            node_plugin.mkdir()
            with open(node_plugin / "plugin.manifest.json", "w") as f:
                json.dump({
                    "id": "node-plugin",
                    "version": "2.0.0",
                    "runtime": {"language": "node", "entry": "index.js"},
                    "steps": [{"id": "scrape"}],
                }, f)
            (node_plugin / "index.js").touch()

            yield plugin_dir

    @pytest.mark.asyncio
    async def test_load_python_plugin(self, plugin_dir_with_plugins):
        """Test loading Python plugin."""
        manager = PluginManager(plugin_dir_with_plugins)
        await manager.discover_plugins()

        info = await manager.load_plugin("py-plugin")

        assert info.plugin_id == "py-plugin"
        assert info.manifest.runtime.language == "python"
        assert info.process.config.language == "python"

    @pytest.mark.asyncio
    async def test_load_uses_discovered_path_for_namespaced_id(self, tmp_path):
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        physical_dir = plugin_dir / "physical-directory"
        physical_dir.mkdir()
        with open(physical_dir / "plugin.manifest.json", "w") as f:
            json.dump({"id": "vendor/plugin", "entryPoint": "main.py"}, f)
        (physical_dir / "main.py").touch()

        manager = PluginManager(plugin_dir)
        await manager.discover_plugins()

        info = await manager.load_plugin("vendor/plugin")

        assert info.path == physical_dir.resolve()

    @pytest.mark.asyncio
    async def test_load_rejects_untrusted_plugin_id_before_path_selection(self, tmp_path):
        manager = PluginManager(tmp_path)

        with pytest.raises(SecurityError):
            await manager.load_plugin("../outside")

    @pytest.mark.asyncio
    async def test_load_node_plugin(self, plugin_dir_with_plugins):
        """Test loading Node.js plugin."""
        manager = PluginManager(plugin_dir_with_plugins)
        await manager.discover_plugins()

        info = await manager.load_plugin("node-plugin")

        assert info.plugin_id == "node-plugin"
        assert info.manifest.runtime.language == "node"
        assert info.process.config.language == "node"
        assert info.process.config.entry_point == "index.js"

    @pytest.mark.asyncio
    async def test_auto_detect_language(self, plugin_dir_with_plugins):
        """Test auto-detection of language for manifest without runtime section."""
        # Add a plugin with no runtime section but TypeScript files
        ts_plugin = plugin_dir_with_plugins / "ts-plugin"
        ts_plugin.mkdir()
        with open(ts_plugin / "plugin.manifest.json", "w") as f:
            json.dump({
                "id": "ts-plugin",
                "version": "1.0.0",
                "steps": [],
            }, f)
        (ts_plugin / "index.ts").touch()  # TypeScript file

        manager = PluginManager(plugin_dir_with_plugins)
        await manager.discover_plugins()

        info = await manager.load_plugin("ts-plugin")

        # Should auto-detect TypeScript
        assert info.process.config.language == "typescript"

    @pytest.mark.asyncio
    async def test_get_plugin_status(self, plugin_dir_with_plugins):
        """Test getting plugin status."""
        manager = PluginManager(plugin_dir_with_plugins)
        await manager.discover_plugins()
        await manager.load_plugin("py-plugin")

        status = manager.get_plugin_status("py-plugin")

        assert status["pluginId"] == "py-plugin"
        assert status["version"] == "1.0.0"
        assert status["status"] == "stopped"


# ---------------------------------------------------------------------------
# Lifecycle: idle reclaim, stop-without-unload, sweeper tasks, and the locking
# that keeps invoke, start, idle stop, and unload from interleaving.
# ---------------------------------------------------------------------------


class _FakeProcess:
    """A PluginProcess stand-in that records lifecycle calls.

    The real process spawns an interpreter and speaks the wire protocol, so the
    manager's own ordering — who stops what, and when — is unobservable through
    it without a plugin fixture per case. This exposes exactly the surface the
    manager touches.
    """

    def __init__(self):
        self.status = ProcessStatus.STOPPED
        self.start_count = 0
        self.stop_reasons = []
        self.ping_count = 0
        self.start_fails = False
        self._unhealthy_until = None
        # When set, invoke blocks until the test releases it, so a call can be
        # held in flight while another lifecycle operation is attempted.
        self.hold = None
        self.entered_invoke = asyncio.Event()

    @property
    def is_ready(self):
        return self.status == ProcessStatus.READY

    @property
    def is_unhealthy(self):
        return self.status == ProcessStatus.UNHEALTHY

    async def start(self):
        self.start_count += 1
        # Yield, so a concurrent caller really does get a chance to interleave
        # here rather than the test proving something about an atomic block.
        await asyncio.sleep(0)
        if self.start_fails:
            return False
        self.status = ProcessStatus.READY
        return True

    async def stop(self, reason="shutdown", grace_period_ms=5000):
        self.stop_reasons.append(reason)
        self.status = ProcessStatus.STOPPED

    async def ping(self, timeout_ms=5000):
        self.ping_count += 1
        return True

    async def invoke(self, step, input_data, config, context, timeout_ms=None):
        self.entered_invoke.set()
        if self.hold is not None:
            await self.hold.wait()
        return {"ok": True, "data": {"step": step}}


@pytest.fixture
def lifecycle_plugin_dir(tmp_path):
    """One discoverable plugin declaring a single step."""
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    plugin = plugin_dir / "worker"
    plugin.mkdir()
    (plugin / "plugin.manifest.json").write_text(
        json.dumps(
            {
                "id": "worker",
                "version": "1.0.0",
                "entryPoint": "main.py",
                "steps": [{"id": "run"}],
            }
        )
    )
    (plugin / "main.py").touch()
    return plugin_dir


async def _loaded(plugin_dir, **config):
    """A manager with ``worker`` loaded and its process replaced by a fake."""
    manager = PluginManager(plugin_dir, config=config or None)
    await manager.discover_plugins()
    info = await manager.load_plugin("worker")
    process = _FakeProcess()
    info.process = process
    return manager, info, process


async def _invoke(manager, step="run"):
    return await manager.invoke(
        plugin_id="worker", step=step, input_data={}, config={}, context={}
    )


class TestPluginManagerIdleReclaim:
    """Idle stop must honor configuration and measure time monotonically."""

    @pytest.mark.asyncio
    async def test_invoke_stamps_a_monotonic_last_invoke_time(self, lifecycle_plugin_dir):
        manager, info, _ = await _loaded(lifecycle_plugin_dir)
        assert info.last_invoke_time is None  # never invoked is not "invoked at 0"

        before = time.monotonic()
        await _invoke(manager)
        after = time.monotonic()

        # On the monotonic timeline, not the wall clock: an idle sweep that
        # compared a wall-clock stamp would misfire across any clock step.
        assert before <= info.last_invoke_time <= after

    @pytest.mark.asyncio
    async def test_idle_sweep_uses_the_configured_timeout(self, lifecycle_plugin_dir):
        manager, info, process = await _loaded(lifecycle_plugin_dir, idleTimeoutSeconds=30)
        await _invoke(manager)

        info.last_invoke_time = time.monotonic() - 10
        await manager._check_idle()
        assert process.stop_reasons == []  # 10s idle, 30s timeout

        info.last_invoke_time = time.monotonic() - 31
        await manager._check_idle()
        assert process.stop_reasons == ["idle"]

    @pytest.mark.asyncio
    async def test_a_short_configured_timeout_is_not_overridden_by_the_default(
        self, lifecycle_plugin_dir
    ):
        """The setting was read and then ignored: everyone got five minutes."""
        manager, info, process = await _loaded(lifecycle_plugin_dir, idleTimeoutSeconds=1)
        await _invoke(manager)
        info.last_invoke_time = time.monotonic() - 2

        await manager._check_idle()

        assert process.stop_reasons == ["idle"]

    @pytest.mark.asyncio
    async def test_a_non_positive_timeout_disables_idle_reclaim(self, lifecycle_plugin_dir):
        manager, info, process = await _loaded(lifecycle_plugin_dir, idleTimeoutSeconds=0)
        await _invoke(manager)
        info.last_invoke_time = time.monotonic() - 10_000

        await manager._check_idle()

        assert process.stop_reasons == []

    @pytest.mark.asyncio
    async def test_a_never_invoked_plugin_is_left_alone(self, lifecycle_plugin_dir):
        manager, info, process = await _loaded(lifecycle_plugin_dir, idleTimeoutSeconds=1)
        process.status = ProcessStatus.READY

        await manager._check_idle()

        assert info.last_invoke_time is None
        assert process.stop_reasons == []

    @pytest.mark.asyncio
    async def test_idle_sweep_does_not_stop_a_plugin_mid_invoke(self, lifecycle_plugin_dir):
        manager, info, process = await _loaded(lifecycle_plugin_dir, idleTimeoutSeconds=1)
        process.hold = asyncio.Event()

        call = asyncio.create_task(_invoke(manager))
        await process.entered_invoke.wait()
        # Old enough to look abandoned, but a caller is inside it right now.
        info.last_invoke_time = time.monotonic() - 60

        await manager._check_idle()
        assert process.stop_reasons == []

        process.hold.set()
        assert (await call)["ok"] is True
        # And the stamp was refreshed on the way out, so the call's own duration
        # does not immediately count as idle time.
        assert time.monotonic() - info.last_invoke_time < 1

    @pytest.mark.asyncio
    async def test_a_failing_sweep_does_not_end_the_sweeper(self, lifecycle_plugin_dir):
        """One bad plugin used to silently retire health checking for all."""
        manager, _, _ = await _loaded(lifecycle_plugin_dir)
        sweeps = []

        async def boom():
            sweeps.append(1)
            raise RuntimeError("plugin exploded")

        assert await manager._start_sweeper("_health_check_task", "health", 0.01, boom)
        await asyncio.sleep(0.05)
        task = manager._health_check_task

        assert len(sweeps) > 1
        assert not task.done()
        await manager.shutdown()


class TestPluginManagerStopWithoutUnload:
    """Stopping reclaims the process; the plugin stays loaded and restarts."""

    @pytest.mark.asyncio
    async def test_stop_keeps_the_plugin_loaded_and_restarts_lazily(
        self, lifecycle_plugin_dir
    ):
        manager, info, process = await _loaded(lifecycle_plugin_dir)
        await _invoke(manager)
        assert process.start_count == 1

        assert await manager.stop_plugin("worker") is True

        # Still registered, still holding its validated manifest and path — the
        # difference between reclaiming a process and deregistering a plugin.
        assert manager.get_plugin_status("worker")["status"] == "stopped"
        assert manager.get_manifest("worker") is not None
        assert manager._plugins["worker"] is info

        await _invoke(manager)
        assert process.start_count == 2  # lazy restart, no rediscovery
        assert process.is_ready

    @pytest.mark.asyncio
    async def test_stop_is_a_no_op_when_not_loaded_or_already_stopped(
        self, lifecycle_plugin_dir
    ):
        manager, _, process = await _loaded(lifecycle_plugin_dir)

        assert await manager.stop_plugin("worker") is False  # never started
        assert await manager.stop_plugin("no-such-plugin") is False
        assert process.stop_reasons == []

    @pytest.mark.asyncio
    async def test_stop_refuses_while_an_invoke_is_in_flight(self, lifecycle_plugin_dir):
        manager, _, process = await _loaded(lifecycle_plugin_dir)
        process.hold = asyncio.Event()

        call = asyncio.create_task(_invoke(manager))
        await process.entered_invoke.wait()

        assert await manager.stop_plugin("worker") is False
        assert process.stop_reasons == []

        process.hold.set()
        await call
        assert await manager.stop_plugin("worker") is True


class TestPluginManagerLifecycleLocking:
    """invoke / start / idle-stop / unload must not interleave."""

    @pytest.mark.asyncio
    async def test_concurrent_first_invokes_start_one_process(self, lifecycle_plugin_dir):
        manager, _, process = await _loaded(lifecycle_plugin_dir)

        results = await asyncio.gather(*(_invoke(manager) for _ in range(5)))

        assert all(r["ok"] for r in results)
        # Without the per-plugin lock every caller saw "not ready" and started
        # its own subprocess; all but one were then unreferenced and unstoppable.
        assert process.start_count == 1

    @pytest.mark.asyncio
    async def test_concurrent_loads_register_one_plugin_info(self, lifecycle_plugin_dir):
        manager = PluginManager(lifecycle_plugin_dir)
        await manager.discover_plugins()

        infos = await asyncio.gather(*(manager.load_plugin("worker") for _ in range(5)))

        assert all(info is infos[0] for info in infos)
        assert manager._plugins["worker"] is infos[0]

    @pytest.mark.asyncio
    async def test_an_invoke_that_lost_its_plugin_does_not_resurrect_it(
        self, lifecycle_plugin_dir
    ):
        """Unload wins over a start that was waiting on the same lock."""
        manager, info, process = await _loaded(lifecycle_plugin_dir)

        async with info.lock:
            call = asyncio.create_task(_invoke(manager))
            await asyncio.sleep(0)  # the invoke is now queued on info.lock
            manager._plugins.pop("worker")

        with pytest.raises(PluginNotFoundError):
            await call
        assert process.start_count == 0

    @pytest.mark.asyncio
    async def test_unload_drains_an_in_flight_invoke_before_stopping(
        self, lifecycle_plugin_dir
    ):
        """Deregistering is immediate; killing the process is not.

        Stopping the subprocess under a caller that is waiting on its reply
        turns an orderly unload into a transport failure for work the manager
        had already accepted.
        """
        manager, _, process = await _loaded(lifecycle_plugin_dir)
        process.hold = asyncio.Event()

        call = asyncio.create_task(_invoke(manager))
        await process.entered_invoke.wait()

        unload = asyncio.create_task(manager.unload_plugin("worker"))
        await asyncio.sleep(0)

        # Already deregistered, so nothing new can reach it...
        assert manager.list_plugins() == []
        # ...but the running call still has its process.
        assert process.stop_reasons == []
        assert not unload.done()

        process.hold.set()
        assert (await call)["ok"] is True
        await unload
        assert process.stop_reasons == ["shutdown"]
        # The completed call must not re-register the plugin it outlived.
        assert manager.list_plugins() == []

    @pytest.mark.asyncio
    async def test_unload_stops_a_plugin_that_will_not_drain(self, lifecycle_plugin_dir):
        """The drain is bounded: shutdown must not depend on plugin cooperation."""
        manager, _, process = await _loaded(lifecycle_plugin_dir, drainTimeoutSeconds=0.05)
        process.hold = asyncio.Event()

        call = asyncio.create_task(_invoke(manager))
        await process.entered_invoke.wait()

        await manager.unload_plugin("worker")
        assert process.stop_reasons == ["shutdown"]

        process.hold.set()
        await call

    @pytest.mark.asyncio
    async def test_the_stamp_is_refreshed_before_the_call_is_released(
        self, lifecycle_plugin_dir
    ):
        """Order matters: released-and-stale is the state idle reclaim acts on.

        A sweep that could observe ``active_invocations == 0`` together with the
        pre-call timestamp would read a just-finished plugin as long abandoned
        and stop the process out from under its next caller.
        """
        manager, info, _ = await _loaded(lifecycle_plugin_dir)
        writes = []

        class _Recording(type(info)):
            def __setattr__(self, name, value):
                if name in ("last_invoke_time", "active_invocations"):
                    writes.append(name)
                super().__setattr__(name, value)

        manager._plugins["worker"] = _Recording(
            info.plugin_id, info.manifest, info.process, info.path
        )

        await _invoke(manager)

        assert writes[-2:] == ["last_invoke_time", "active_invocations"]


class TestPluginManagerSweeperTasks:
    """Sweeper startup and shutdown are both idempotent."""

    @pytest.mark.asyncio
    async def test_starting_twice_does_not_orphan_a_sweeper(self, lifecycle_plugin_dir):
        manager, _, _ = await _loaded(lifecycle_plugin_dir)

        await manager.start_health_checks(interval_seconds=60)
        await manager.start_idle_checks(check_interval=60)
        health, idle = manager._health_check_task, manager._idle_check_task

        await manager.start_health_checks(interval_seconds=60)
        await manager.start_idle_checks(check_interval=60)

        # Same handles: a second call must not leave a running task that nothing
        # holds a reference to and shutdown therefore cannot cancel.
        assert manager._health_check_task is health
        assert manager._idle_check_task is idle

        await manager.shutdown()
        assert health.cancelled() and idle.cancelled()

    @pytest.mark.asyncio
    async def test_shutdown_is_idempotent(self, lifecycle_plugin_dir):
        manager, _, process = await _loaded(lifecycle_plugin_dir)
        await _invoke(manager)
        await manager.start_health_checks(interval_seconds=60)

        await manager.shutdown()
        await manager.shutdown()

        assert manager._health_check_task is None
        assert manager.list_plugins() == []
        assert process.stop_reasons == ["shutdown"]

    @pytest.mark.asyncio
    async def test_a_sweeper_cannot_be_started_after_shutdown(self, lifecycle_plugin_dir):
        manager, _, _ = await _loaded(lifecycle_plugin_dir)
        await manager.shutdown()

        assert await manager.start_idle_checks(check_interval=60) is False
        assert manager._idle_check_task is None


class TestPluginManagerShutdownIsFinal:
    """Nothing may start a process after shutdown, or across it."""

    @pytest.mark.asyncio
    async def test_invoke_after_shutdown_starts_nothing(self, lifecycle_plugin_dir):
        manager, _, process = await _loaded(lifecycle_plugin_dir)
        await _invoke(manager)
        await manager.shutdown()
        started_before = process.start_count

        with pytest.raises(PluginManagerShutdownError):
            await _invoke(manager)

        # A plugin re-registered here would hold a process no sweeper watches,
        # no unload reaches, and no shutdown stops.
        assert manager.list_plugins() == []
        assert process.start_count == started_before

    @pytest.mark.asyncio
    async def test_load_after_shutdown_is_refused(self, lifecycle_plugin_dir):
        manager, _, _ = await _loaded(lifecycle_plugin_dir)
        await manager.shutdown()

        with pytest.raises(PluginManagerShutdownError):
            await manager.load_plugin("worker")

        assert manager._plugins == {}

    @pytest.mark.asyncio
    async def test_the_refusal_is_still_a_plugin_not_found_for_callers(
        self, lifecycle_plugin_dir
    ):
        """Existing handlers — including the invoker's legacy fallback — keep
        working, while the log still says which of the two conditions it was."""
        manager, _, _ = await _loaded(lifecycle_plugin_dir)
        await manager.shutdown()

        with pytest.raises(PluginNotFoundError) as raised:
            await _invoke(manager)

        assert raised.value.code == "PLUGIN_MANAGER_SHUTDOWN"
        assert "shut down" in str(raised.value)

    @pytest.mark.asyncio
    async def test_an_invoke_racing_shutdown_does_not_start_a_process(
        self, lifecycle_plugin_dir
    ):
        """The interleaving the flag alone does not cover: an invoke that passed
        the registry check before shutdown began and is queued on the plugin
        lock when it does."""
        manager, info, process = await _loaded(lifecycle_plugin_dir)

        async with info.lock:
            call = asyncio.create_task(_invoke(manager))
            await asyncio.sleep(0)  # queued on info.lock, past the registry read
            closing = asyncio.create_task(manager.shutdown())
            await asyncio.sleep(0)  # shutdown has flagged and is queued behind it

        with pytest.raises(PluginManagerShutdownError):
            await call
        await closing

        assert process.start_count == 0
        assert manager.list_plugins() == []

    @pytest.mark.asyncio
    async def test_shutdown_waits_for_a_call_it_did_not_start(self, lifecycle_plugin_dir):
        """Work already accepted finishes; shutdown stops the process after."""
        manager, _, process = await _loaded(lifecycle_plugin_dir)
        process.hold = asyncio.Event()

        call = asyncio.create_task(_invoke(manager))
        await process.entered_invoke.wait()

        closing = asyncio.create_task(manager.shutdown())
        await asyncio.sleep(0)
        assert process.stop_reasons == []

        process.hold.set()
        assert (await call)["ok"] is True
        await closing
        assert process.stop_reasons == ["shutdown"]
