"""
Plugin Manager

Manages multiple plugin processes and their lifecycle.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .process import PluginProcess, ProcessConfig, ProcessStatus, RestartPolicy
from .exceptions import PluginNotFoundError, PluginUnhealthyError

logger = logging.getLogger(__name__)


@dataclass
class PluginManifest:
    """Parsed plugin manifest."""
    id: str
    name: str
    version: str
    vendor: str
    entry_point: str
    steps: List[Dict[str, Any]]
    permissions: List[str] = field(default_factory=list)
    required_secrets: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginManifest":
        """Create from manifest dictionary."""
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            version=data.get("version", "0.0.0"),
            vendor=data.get("vendor", "unknown"),
            entry_point=data.get("entryPoint", "main.py"),
            steps=data.get("steps", []),
            permissions=data.get("permissions", []),
            required_secrets=data.get("requiredSecrets", []),
            meta=data.get("meta", {}),
        )

    def get_step(self, step_id: str) -> Optional[Dict[str, Any]]:
        """Get step definition by ID."""
        for step in self.steps:
            if step.get("id") == step_id:
                return step
        return None


@dataclass
class PluginInfo:
    """Information about a loaded plugin."""
    plugin_id: str
    manifest: PluginManifest
    process: PluginProcess
    path: Path


class PluginManager:
    """
    Manages plugin processes and routing.

    Responsibilities:
    - Load plugin manifests
    - Start/stop plugin processes
    - Route invoke requests to correct plugin
    - Handle plugin lifecycle (lazy start, idle timeout)
    """

    def __init__(
        self,
        plugin_dir: Path,
        config: Optional[Dict[str, Any]] = None,
        pool_id: str = "default",
    ):
        """
        Initialize plugin manager.

        Args:
            plugin_dir: Base directory containing plugins
            config: Runtime configuration
            pool_id: Identifier for this process pool
        """
        self.plugin_dir = Path(plugin_dir)
        self.config = config or {}
        self.pool_id = pool_id

        self._plugins: Dict[str, PluginInfo] = {}
        self._manifests: Dict[str, PluginManifest] = {}

        # Configuration from runtime config
        self._start_policy = self.config.get("startPolicy", "lazy")
        self._idle_timeout_seconds = self.config.get("idleTimeoutSeconds", 300)
        self._max_processes = self.config.get("maxProcesses", 2)

        # Restart policy
        restart_config = self.config.get("restartPolicy", {})
        self._restart_policy = RestartPolicy(
            max_restarts=restart_config.get("maxRestarts", 3),
            restart_window_seconds=restart_config.get("restartWindowSeconds", 60),
            backoff_seconds=restart_config.get("backoffSeconds", [1, 2, 4]),
            unhealthy_cooldown_seconds=restart_config.get("unhealthyCooldownSeconds", 300),
        )

        # Health check task
        self._health_check_task: Optional[asyncio.Task] = None
        self._idle_check_task: Optional[asyncio.Task] = None

    async def discover_plugins(self) -> List[str]:
        """
        Discover available plugins in the plugin directory.

        Returns:
            List of discovered plugin IDs
        """
        discovered = []

        if not self.plugin_dir.exists():
            logger.warning(f"Plugin directory does not exist: {self.plugin_dir}")
            return discovered

        for entry in self.plugin_dir.iterdir():
            if not entry.is_dir():
                continue

            manifest_path = entry / "plugin.manifest.json"
            if not manifest_path.exists():
                continue

            try:
                with open(manifest_path) as f:
                    data = json.load(f)

                manifest = PluginManifest.from_dict(data)
                self._manifests[manifest.id] = manifest
                discovered.append(manifest.id)

                logger.info(f"Discovered plugin: {manifest.id} v{manifest.version}")

            except Exception as e:
                logger.error(f"Failed to load manifest from {manifest_path}: {e}")

        return discovered

    async def load_plugin(self, plugin_id: str) -> PluginInfo:
        """
        Load a plugin (lazy start - doesn't start process yet).

        Args:
            plugin_id: Plugin ID to load

        Returns:
            PluginInfo object

        Raises:
            PluginNotFoundError: If plugin not found
        """
        if plugin_id in self._plugins:
            return self._plugins[plugin_id]

        # Find manifest
        manifest = self._manifests.get(plugin_id)
        if not manifest:
            # Try to discover it
            await self.discover_plugins()
            manifest = self._manifests.get(plugin_id)

        if not manifest:
            raise PluginNotFoundError(plugin_id)

        # Find plugin directory
        # Try different naming conventions
        possible_names = [
            plugin_id,
            plugin_id.replace("/", "_"),
            plugin_id.replace("-", "_"),
        ]

        plugin_path = None
        for name in possible_names:
            path = self.plugin_dir / name
            if path.exists():
                plugin_path = path
                break

        if not plugin_path:
            raise PluginNotFoundError(plugin_id)

        # Create process config
        process_config = ProcessConfig(
            plugin_id=plugin_id,
            plugin_dir=plugin_path,
            entry_point=manifest.entry_point,
        )

        # Create process (but don't start yet)
        process = PluginProcess(process_config, self._restart_policy)

        # Create plugin info
        info = PluginInfo(
            plugin_id=plugin_id,
            manifest=manifest,
            process=process,
            path=plugin_path,
        )

        self._plugins[plugin_id] = info
        logger.info(f"Loaded plugin: {plugin_id}")

        return info

    async def unload_plugin(self, plugin_id: str):
        """
        Unload a plugin and stop its process.

        Args:
            plugin_id: Plugin ID to unload
        """
        info = self._plugins.pop(plugin_id, None)
        if info:
            await info.process.stop()
            logger.info(f"Unloaded plugin: {plugin_id}")

    async def invoke(
        self,
        plugin_id: str,
        step: str,
        input_data: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any],
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Invoke a step on a plugin.

        Args:
            plugin_id: Plugin ID
            step: Step ID within plugin
            input_data: Input parameters
            config: Static configuration
            context: Execution context
            timeout_ms: Timeout in milliseconds

        Returns:
            Result dictionary

        Raises:
            PluginNotFoundError: If plugin or step not found
            PluginUnhealthyError: If plugin is unhealthy
        """
        # Load plugin if not already loaded
        if plugin_id not in self._plugins:
            await self.load_plugin(plugin_id)

        info = self._plugins.get(plugin_id)
        if not info:
            raise PluginNotFoundError(plugin_id)

        # Check if step exists
        step_def = info.manifest.get_step(step)
        if not step_def:
            raise PluginNotFoundError(plugin_id, step)

        # Check if plugin is unhealthy
        if info.process.is_unhealthy:
            cooldown = int(info.process._unhealthy_until - asyncio.get_event_loop().time()) \
                if info.process._unhealthy_until else 0
            raise PluginUnhealthyError(plugin_id, cooldown)

        # Start process if not running (lazy start)
        if not info.process.is_ready:
            started = await info.process.start()
            if not started:
                raise PluginNotFoundError(plugin_id)

        # Invoke the step
        return await info.process.invoke(
            step=step,
            input_data=input_data,
            config=config,
            context=context,
            timeout_ms=timeout_ms,
        )

    async def start_health_checks(self, interval_seconds: int = 30):
        """Start periodic health checks."""
        async def check_loop():
            while True:
                await asyncio.sleep(interval_seconds)
                await self._check_health()

        self._health_check_task = asyncio.create_task(check_loop())

    async def start_idle_checks(self, check_interval: int = 60):
        """Start periodic idle checks."""
        async def check_loop():
            while True:
                await asyncio.sleep(check_interval)
                await self._check_idle()

        self._idle_check_task = asyncio.create_task(check_loop())

    async def _check_health(self):
        """Check health of all running plugins."""
        for plugin_id, info in self._plugins.items():
            if info.process.status == ProcessStatus.READY:
                healthy = await info.process.ping()
                if not healthy:
                    logger.warning(f"Plugin {plugin_id} failed health check")

    async def _check_idle(self):
        """Stop idle plugins."""
        # TODO: Track last invoke time and stop idle plugins
        pass

    async def shutdown(self):
        """Shutdown all plugins and cleanup."""
        # Cancel health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Cancel idle check task
        if self._idle_check_task:
            self._idle_check_task.cancel()
            try:
                await self._idle_check_task
            except asyncio.CancelledError:
                pass

        # Stop all plugins
        for plugin_id in list(self._plugins.keys()):
            await self.unload_plugin(plugin_id)

        logger.info(f"Plugin manager {self.pool_id} shutdown complete")

    def get_plugin_status(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a plugin."""
        info = self._plugins.get(plugin_id)
        if not info:
            return None

        return {
            "pluginId": plugin_id,
            "version": info.manifest.version,
            "status": info.process.status.value,
            "steps": [s.get("id") for s in info.manifest.steps],
        }

    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all loaded plugins."""
        return [
            self.get_plugin_status(plugin_id)
            for plugin_id in self._plugins
        ]

    def list_available_plugins(self) -> List[str]:
        """List all discovered (available) plugins."""
        return list(self._manifests.keys())
