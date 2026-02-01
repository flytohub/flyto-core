"""
Plugin Manager

Manages multiple plugin processes and their lifecycle.

Security:
- Validates plugin manifests before loading
- Enforces entry point path safety
- Checks for dangerous permissions
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .process import PluginProcess, ProcessConfig, ProcessStatus, RestartPolicy
from .exceptions import (
    PluginNotFoundError,
    PluginUnhealthyError,
    SecurityError,
    PathTraversalError,
    ValidationError,
)
from .languages import get_language_config, detect_language, validate_entry_point

logger = logging.getLogger(__name__)


# Security: Regex pattern for valid plugin IDs
# Allows alphanumeric, hyphens, underscores, and forward slashes (for namespacing)
# Does not allow: .., leading/trailing slashes, spaces, special chars
VALID_PLUGIN_ID_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_\-/]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$')

# Security: Dangerous permissions that require extra scrutiny
DANGEROUS_PERMISSIONS = frozenset([
    "filesystem:*",
    "filesystem:write:*",
    "network:*",
    "shell:execute",
    "system:*",
    "secrets:*",
    "browser:*",
])

# Security: Maximum lengths for manifest fields
MAX_PLUGIN_ID_LENGTH = 128
MAX_VERSION_LENGTH = 32
MAX_ENTRY_POINT_LENGTH = 256
MAX_PERMISSIONS_COUNT = 50


def validate_plugin_id(plugin_id: str) -> None:
    """
    Validate plugin ID format.

    Security checks:
    - No path traversal patterns
    - Only allowed characters
    - Reasonable length

    Raises:
        ValidationError: If plugin ID is invalid
    """
    if not plugin_id:
        raise ValidationError("Plugin ID cannot be empty", field="id")

    if len(plugin_id) > MAX_PLUGIN_ID_LENGTH:
        raise ValidationError(
            f"Plugin ID too long (max {MAX_PLUGIN_ID_LENGTH} chars)",
            field="id"
        )

    # Security: Check for path traversal
    if ".." in plugin_id:
        raise SecurityError(
            "Plugin ID contains path traversal pattern",
            violation_type="PATH_TRAVERSAL",
            details={"plugin_id": plugin_id}
        )

    if not VALID_PLUGIN_ID_PATTERN.match(plugin_id):
        raise ValidationError(
            "Plugin ID contains invalid characters. "
            "Allowed: alphanumeric, hyphens, underscores, forward slashes",
            field="id"
        )


def validate_version(version: str) -> None:
    """
    Validate version string format.

    Raises:
        ValidationError: If version is invalid
    """
    if not version:
        return  # Version is optional

    if len(version) > MAX_VERSION_LENGTH:
        raise ValidationError(
            f"Version too long (max {MAX_VERSION_LENGTH} chars)",
            field="version"
        )

    # Basic semver-ish pattern (allow some flexibility)
    version_pattern = re.compile(r'^[0-9]+(\.[0-9]+)*(-[a-zA-Z0-9._-]+)?(\+[a-zA-Z0-9._-]+)?$')
    if not version_pattern.match(version):
        raise ValidationError(
            "Invalid version format. Expected semver-like (e.g., 1.0.0, 1.0.0-beta)",
            field="version"
        )


def validate_permissions(permissions: List[str]) -> List[str]:
    """
    Validate and warn about dangerous permissions.

    Args:
        permissions: List of permission strings

    Returns:
        List of dangerous permissions found

    Raises:
        ValidationError: If permissions list is too large
    """
    if len(permissions) > MAX_PERMISSIONS_COUNT:
        raise ValidationError(
            f"Too many permissions (max {MAX_PERMISSIONS_COUNT})",
            field="permissions"
        )

    dangerous_found = []
    for perm in permissions:
        if perm in DANGEROUS_PERMISSIONS:
            dangerous_found.append(perm)
        # Check for wildcard permissions
        elif perm.endswith(":*") or perm == "*":
            dangerous_found.append(perm)

    if dangerous_found:
        logger.warning(
            f"Plugin requests dangerous permissions: {dangerous_found}"
        )

    return dangerous_found


@dataclass
class RuntimeConfig:
    """Runtime configuration from plugin manifest."""
    language: str = "python"
    entry: str = "main.py"
    min_flyto_version: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeConfig":
        """Create from runtime section of manifest."""
        if not data:
            return cls()
        return cls(
            language=data.get("language", "python"),
            entry=data.get("entry", data.get("entryPoint", "main.py")),
            min_flyto_version=data.get("minFlytoVersion", data.get("min_flyto_version")),
        )


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
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    # Modules (new format for marketplace plugins)
    modules: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], validate: bool = True) -> "PluginManifest":
        """
        Create from manifest dictionary.

        Args:
            data: Manifest dictionary
            validate: If True, perform security validation

        Raises:
            ValidationError: If manifest is invalid
            SecurityError: If security violation detected
        """
        # Get plugin ID early for validation
        plugin_id = data.get("id") or data.get("name")
        if not plugin_id:
            raise ValidationError("Plugin manifest must have 'id' or 'name' field")

        # Security: Validate plugin ID
        if validate:
            validate_plugin_id(plugin_id)

        # Parse runtime config
        runtime_data = data.get("runtime", {})
        runtime = RuntimeConfig.from_dict(runtime_data)

        # Determine entry point: runtime.entry > entryPoint > default based on language
        entry_point = runtime.entry
        if not entry_point or entry_point == "main.py":
            entry_point = data.get("entryPoint", runtime.entry)

        # If still default, use language-specific default
        if entry_point == "main.py" and runtime.language != "python":
            lang_config = get_language_config(runtime.language)
            entry_point = lang_config.entry_pattern

        # Security: Validate entry point length and basic format
        if validate:
            if len(entry_point) > MAX_ENTRY_POINT_LENGTH:
                raise ValidationError(
                    f"Entry point path too long (max {MAX_ENTRY_POINT_LENGTH} chars)",
                    field="entry"
                )

            # Basic check for path traversal (full validation happens at load time)
            if ".." in entry_point:
                raise SecurityError(
                    "Entry point contains path traversal pattern",
                    violation_type="PATH_TRAVERSAL",
                    details={"entry": entry_point}
                )

        # Get version
        version = data.get("version", "0.0.0")
        if validate:
            validate_version(version)

        # Get permissions
        permissions = data.get("permissions", [])
        if validate:
            dangerous = validate_permissions(permissions)
            if dangerous:
                logger.info(f"Plugin {plugin_id} has dangerous permissions: {dangerous}")

        return cls(
            id=plugin_id,
            name=data.get("name", plugin_id),
            version=version,
            vendor=data.get("vendor", data.get("author", "unknown")),
            entry_point=entry_point,
            steps=data.get("steps", []),
            permissions=permissions,
            required_secrets=data.get("requiredSecrets", data.get("required_secrets", [])),
            meta=data.get("meta", {}),
            runtime=runtime,
            modules=data.get("modules", []),
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

            # Try different manifest formats
            manifest_path = None
            manifest_format = None

            # Priority: plugin.yaml > plugin.manifest.json
            for filename, fmt in [
                ("plugin.yaml", "yaml"),
                ("plugin.yml", "yaml"),
                ("plugin.manifest.json", "json"),
                ("manifest.json", "json"),
            ]:
                path = entry / filename
                if path.exists():
                    manifest_path = path
                    manifest_format = fmt
                    break

            if not manifest_path:
                continue

            try:
                with open(manifest_path) as f:
                    if manifest_format == "yaml":
                        try:
                            import yaml
                            data = yaml.safe_load(f)
                        except ImportError:
                            logger.warning(f"PyYAML not installed, skipping {manifest_path}")
                            continue
                    else:
                        data = json.load(f)

                # Handle 'name' as 'id' for marketplace-style manifests
                if "id" not in data and "name" in data:
                    data["id"] = data["name"]

                manifest = PluginManifest.from_dict(data)
                self._manifests[manifest.id] = manifest
                discovered.append(manifest.id)

                logger.info(
                    f"Discovered plugin: {manifest.id} v{manifest.version} "
                    f"(language: {manifest.runtime.language})"
                )

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

        # Determine language: manifest > auto-detect
        language = manifest.runtime.language
        if language == "python":
            # Check if we should auto-detect (when manifest doesn't specify)
            detected = detect_language(plugin_path)
            if detected != "python":
                logger.info(f"Auto-detected language for {plugin_id}: {detected}")
                language = detected

        # Verify runtime is available
        lang_config = get_language_config(language)
        if not lang_config.is_available():
            from .languages import get_install_instructions
            logger.warning(
                f"Language runtime not available: {language}. "
                f"Install instructions: {get_install_instructions(language)}"
            )

        # Security: Validate entry point path before creating process
        # This prevents path traversal attacks
        try:
            validated_entry = validate_entry_point(manifest.entry_point, plugin_path)
            logger.debug(f"Validated entry point: {validated_entry}")
        except PathTraversalError as e:
            logger.error(f"Security violation in plugin {plugin_id}: {e}")
            raise

        # Create process config with language
        process_config = ProcessConfig(
            plugin_id=plugin_id,
            plugin_dir=plugin_path,
            entry_point=manifest.entry_point,
            language=language,
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
