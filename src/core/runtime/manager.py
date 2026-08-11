# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Plugin Manager

Manages multiple plugin processes and their lifecycle.

Security:
- Validates plugin manifests before loading
- Enforces entry point path safety
- Checks for dangerous permissions
"""

import asyncio
import contextlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import (
    PathTraversalError,
    PluginManagerShutdownError,
    PluginNotFoundError,
    PluginUnhealthyError,
    SecurityError,
    ValidationError,
)
from .languages import detect_language, get_language_config, validate_entry_point
from .process import PluginProcess, ProcessConfig, ProcessStatus, RestartPolicy

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
        if perm in DANGEROUS_PERMISSIONS or perm.endswith(":*") or perm == "*":
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


def _set_event() -> asyncio.Event:
    """A new ``asyncio.Event`` that starts set.

    A freshly loaded plugin has no invocation in flight, so its drain gate is
    already open; an Event that started clear would make the first ``unload``
    wait out the whole drain timeout for a call that never existed.
    """
    event = asyncio.Event()
    event.set()
    return event


@dataclass
class PluginInfo:
    """Information about a loaded plugin.

    ``last_invoke_time`` is a ``time.monotonic()`` reading, not wall clock. The
    idle sweep is the only consumer and it asks "how long since this ran", which
    a wall clock answers wrongly whenever the host clock steps: an NTP jump
    backwards makes every plugin look freshly used and idle stop never fires; a
    jump forwards makes a plugin that ran a second ago look abandoned and it is
    stopped underneath its own caller. ``None`` means "never invoked", which is
    distinct from "invoked at time 0".

    ``active_invocations`` is what keeps the idle sweep, ``stop_plugin``, and
    ``unload_plugin`` off a process that is mid-request; ``idle_event`` is the
    same fact in awaitable form, set whenever the count is zero, so a caller can
    wait for the process to drain instead of polling it. ``lock`` serializes the
    lifecycle transitions themselves — start, stop, unload — so two of them can
    never interleave.
    """
    plugin_id: str
    manifest: PluginManifest
    process: PluginProcess
    path: Path
    last_invoke_time: Optional[float] = None
    active_invocations: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)
    idle_event: asyncio.Event = field(
        default_factory=_set_event, repr=False, compare=False
    )

    def claim(self) -> None:
        """Mark one invocation as in flight."""
        self.active_invocations += 1
        self.idle_event.clear()
        self.last_invoke_time = time.monotonic()

    def release(self) -> None:
        """Mark one invocation as finished.

        The timestamp is refreshed *before* the count drops, and the order is
        the point. A sweep that observes ``active_invocations == 0`` must never
        also be able to observe the pre-call timestamp: that pairing says "not
        running and last used long ago", which is exactly the state idle reclaim
        stops a process on — so a long call could be followed by its own plugin
        being torn down as though it had been abandoned all along.
        """
        self.last_invoke_time = time.monotonic()
        self.active_invocations -= 1
        if self.active_invocations < 0:
            # Defensive: a count that has gone negative would keep the drain
            # gate shut forever. Clamp rather than assert — an unbalanced
            # release must not be able to wedge unload.
            logger.warning(
                f"Plugin {self.plugin_id} released more invocations than it claimed"
            )
            self.active_invocations = 0
        if self.active_invocations == 0:
            self.idle_event.set()


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
        # Manifest IDs are external-facing identifiers, not filesystem paths.
        # Keep the directory discovered for each validated manifest so later
        # API requests only select an already-confined path from this map.
        self._manifest_paths: Dict[str, Path] = {}

        # Configuration from runtime config
        self._start_policy = self.config.get("startPolicy", "lazy")
        self._idle_timeout_seconds = self.config.get("idleTimeoutSeconds", 300)
        self._max_processes = self.config.get("maxProcesses", 2)
        # How long an unload waits for accepted work to finish before stopping
        # the process anyway. Bounded on purpose: shutdown must not become
        # contingent on a plugin choosing to reply.
        self._drain_timeout_seconds = self.config.get("drainTimeoutSeconds", 30)

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

        # Guards the plugin registry itself: which ids are loaded, and which
        # PluginInfo (and therefore which per-plugin lock) each one maps to. Held
        # only across dict reads/writes, never across a start, stop, or invoke —
        # one slow plugin must not stall lifecycle work on every other plugin.
        self._registry_lock = asyncio.Lock()
        # Guards the background task handles so concurrent start/shutdown calls
        # cannot each create a sweeper, or cancel a handle the other replaced.
        self._task_lock = asyncio.Lock()
        self._shutting_down = False

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

        plugin_root = self.plugin_dir.resolve()
        for entry in self.plugin_dir.iterdir():
            try:
                plugin_path = entry.resolve(strict=True)
                plugin_path.relative_to(plugin_root)
            except (OSError, ValueError):
                logger.warning(f"Skipping plugin directory outside configured root: {entry}")
                continue

            if not plugin_path.is_dir():
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
                path = plugin_path / filename
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
                self._manifest_paths[manifest.id] = plugin_path
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
        # Validate at the trust boundary even though discovered manifests are
        # validated too. The route parameter must never become a path.
        validate_plugin_id(plugin_id)

        # Serialized so two concurrent first-invokes of the same plugin cannot
        # each build a PluginProcess and register it, which would leave one of
        # them orphaned: unreferenced by the registry, so never stopped by idle
        # sweep, unload, or shutdown, and still holding a subprocess.
        async with self._registry_lock:
            return await self._load_plugin_locked(plugin_id)

    async def _load_plugin_locked(self, plugin_id: str) -> PluginInfo:
        """``load_plugin`` body. Caller must hold ``_registry_lock``.

        Refuses once ``shutdown`` has begun. Shutdown cancels the sweepers and
        unloads everything; a load after that point registers a plugin nothing
        watches and starts a process nothing stops — the manager reports itself
        shut down while a subprocess it owns is still running.
        """
        if self._shutting_down:
            raise PluginManagerShutdownError(plugin_id, self.pool_id)

        if plugin_id in self._plugins:
            return self._plugins[plugin_id]

        # Find the manifest and its independently discovered directory.
        manifest = self._manifests.get(plugin_id)
        plugin_path = self._manifest_paths.get(plugin_id)
        if not manifest or not plugin_path:
            # Try to discover it
            await self.discover_plugins()
            manifest = self._manifests.get(plugin_id)
            plugin_path = self._manifest_paths.get(plugin_id)

        if not manifest or not plugin_path:
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

        The registry entry is removed first, so no further invoke can adopt this
        plugin, and only then is the process stopped — under the plugin's own
        lock, so an unload that lands mid-start waits for the start to finish
        instead of stopping a process that is still being spawned.

        In-flight invocations are then drained before the process is stopped.
        Deregistering is immediate and stopping is not: killing the subprocess
        under a caller that is waiting on a reply turns an orderly unload into a
        transport failure for work that had already been accepted. The wait is
        bounded by ``drainTimeoutSeconds`` so a plugin that never answers cannot
        hold shutdown open; past that bound the stop proceeds and says so.

        Args:
            plugin_id: Plugin ID to unload
        """
        async with self._registry_lock:
            info = self._plugins.pop(plugin_id, None)
        if not info:
            return

        async with info.lock:
            await self._drain(info)
            await info.process.stop()
        logger.info(f"Unloaded plugin: {plugin_id}")

    async def _drain(self, info: PluginInfo) -> bool:
        """Wait for ``info``'s in-flight invocations to finish.

        Returns True if the plugin drained, False if the bounded wait expired
        with work still outstanding — in which case the caller stops it anyway.
        A drain that could block forever would be a worse failure than a
        truncated call: it would make shutdown depend on plugin cooperation.
        """
        if not info.active_invocations:
            return True

        timeout = self._drain_timeout_seconds
        if timeout and timeout > 0:
            try:
                await asyncio.wait_for(info.idle_event.wait(), timeout=timeout)
                return True
            except asyncio.TimeoutError:
                pass

        logger.warning(
            f"Plugin {info.plugin_id} still has {info.active_invocations} "
            f"invocation(s) in flight after {timeout}s; stopping anyway"
        )
        return False

    async def stop_plugin(self, plugin_id: str) -> bool:
        """Stop a plugin's process without unloading the plugin.

        This is the idle path, and it is deliberately not ``unload_plugin``.
        Unloading drops the manifest, the validated path, and the PluginProcess,
        so the next call has to rediscover and revalidate; stopping keeps the
        registry entry so ``invoke`` restarts the process lazily, exactly as it
        does on the very first call. Idle reclaim is a resource decision, not a
        deregistration.

        Returns:
            True if a running process was stopped, False if the plugin is not
            loaded, is already stopped, or is currently serving an invoke.
        """
        info = self._plugins.get(plugin_id)
        if not info:
            return False

        async with info.lock:
            # Re-read under the lock: an unload may have completed while this
            # coroutine waited, and stopping a process the registry no longer
            # owns would race whoever loaded its replacement.
            if self._plugins.get(plugin_id) is not info:
                return False
            if info.active_invocations:
                logger.debug(
                    f"Not stopping plugin {plugin_id}: "
                    f"{info.active_invocations} invocation(s) in flight"
                )
                return False
            if info.process.status == ProcessStatus.STOPPED:
                return False
            await info.process.stop(reason="idle")

        logger.info(f"Stopped plugin process (still loaded): {plugin_id}")
        return True

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
        # Load plugin if not already loaded. load_plugin is itself serialized and
        # returns the already-registered entry when there is one, so a concurrent
        # first invoke of the same plugin cannot produce a second process.
        info = self._plugins.get(plugin_id)
        if info is None:
            info = await self.load_plugin(plugin_id)

        # Check if step exists
        step_def = info.manifest.get_step(step)
        if not step_def:
            raise PluginNotFoundError(plugin_id, step)

        # Check if plugin is unhealthy.
        #
        # ``_unhealthy_until`` is a ``time.time()`` deadline set by the process.
        # Reading it against the event loop's clock — an unrelated monotonic
        # origin — produced a cooldown of roughly "seconds since the epoch",
        # which every caller then reported back as the retry-after.
        if info.process.is_unhealthy:
            cooldown = int(info.process._unhealthy_until - time.time()) \
                if info.process._unhealthy_until else 0
            raise PluginUnhealthyError(plugin_id, max(cooldown, 0))

        async with info.lock:
            # Held across the lazy start and the in-flight bookkeeping, but not
            # across the invoke itself: the start must not race an idle stop or
            # an unload, while concurrent invokes of a started plugin must still
            # be able to run at the same time.
            if self._shutting_down:
                # Shutdown began while this call waited for the lock. Starting
                # now would outlive the shutdown that was supposed to end it.
                raise PluginManagerShutdownError(plugin_id, self.pool_id)

            if self._plugins.get(plugin_id) is not info:
                # Unloaded while this call waited for the lock. Restarting the
                # process now would resurrect a plugin the manager has dropped.
                raise PluginNotFoundError(plugin_id)

            # Start process if not running (lazy start)
            if not info.process.is_ready:
                started = await info.process.start()
                if not started:
                    raise PluginNotFoundError(plugin_id)

            # Claim the process before releasing the lock, so the idle sweep
            # cannot decide this plugin is unused between here and the invoke.
            info.claim()

        try:
            # Invoke the step
            return await info.process.invoke(
                step=step,
                input_data=input_data,
                config=config,
                context=context,
                timeout_ms=timeout_ms,
            )
        finally:
            # Stamps on the way out before dropping the count, so idleness is
            # measured from when the plugin stopped working and no sweep can see
            # "released" and "stale" at the same time. See PluginInfo.release.
            info.release()

    async def start_health_checks(self, interval_seconds: int = 30) -> bool:
        """Start periodic health checks.

        Idempotent: a second call while a sweeper is already running is a no-op.
        Overwriting the handle instead used to drop the reference to the running
        task, which then kept pinging plugins forever with nothing able to cancel
        it — including ``shutdown``, which could only cancel the newest one.

        Returns:
            True if this call started the sweeper, False if one was already
            running or the manager is shutting down.
        """
        return await self._start_sweeper(
            "_health_check_task", "health", interval_seconds, self._check_health
        )

    async def start_idle_checks(self, check_interval: int = 60) -> bool:
        """Start periodic idle checks. Idempotent, as for health checks."""
        return await self._start_sweeper(
            "_idle_check_task", "idle", check_interval, self._check_idle
        )

    async def _start_sweeper(self, attribute: str, label: str, interval_seconds: float,
                             sweep) -> bool:
        """Start one background sweeper if it is not already running.

        Returns True when this call started it, False when one was already
        running or the manager is shutting down. Refusing to start during
        shutdown closes the window where a sweeper is created after the cancel
        pass and outlives the manager it belongs to.
        """
        async def check_loop():
            while True:
                await asyncio.sleep(interval_seconds)
                try:
                    await sweep()
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001 - one bad sweep must not end the sweeper
                    # Without this, a single failing plugin ended the loop for
                    # every plugin, silently and permanently: the task finished,
                    # nothing restarted it, and the manager went on reporting
                    # that checks were running.
                    logger.exception(f"Plugin {label} sweep failed; continuing")

        async with self._task_lock:
            if self._shutting_down:
                logger.debug(f"Not starting {label} sweeper: manager is shutting down")
                return False
            existing: Optional[asyncio.Task] = getattr(self, attribute)
            if existing and not existing.done():
                logger.debug(f"Plugin {label} sweeper already running")
                return False
            setattr(self, attribute, asyncio.create_task(check_loop()))
            return True

    async def _check_health(self):
        """Check health of all running plugins."""
        # Snapshot first: pinging awaits, and the registry can gain or lose
        # plugins while it does, which mutating iteration would raise on.
        for plugin_id, info in list(self._plugins.items()):
            if info.process.status == ProcessStatus.READY:
                healthy = await info.process.ping()
                if not healthy:
                    logger.warning(f"Plugin {plugin_id} failed health check")

    async def _check_idle(self):
        """Stop idle plugins that haven't been invoked recently.

        Uses the configured ``idleTimeoutSeconds`` rather than a hardcoded five
        minutes; the setting was read in ``__init__`` and then ignored here, so
        every deployment got the default no matter what it configured. A
        non-positive timeout disables idle reclaim entirely.

        Plugins that have never been invoked are left alone: they hold no
        process until their first invoke starts one, and "never used" is not the
        same measurement as "used, then idle".
        """
        idle_timeout = self._idle_timeout_seconds
        if not idle_timeout or idle_timeout <= 0:
            return

        now = time.monotonic()
        for plugin_id, info in list(self._plugins.items()):
            last_invoke = info.last_invoke_time
            if (
                last_invoke is not None
                and (now - last_invoke) > idle_timeout
                and info.process.status == ProcessStatus.READY
                and not info.active_invocations
            ):
                logger.info(f"Stopping idle plugin: {plugin_id}")
                # stop_plugin re-checks under the plugin lock; the conditions
                # above are a cheap filter, not the decision.
                await self.stop_plugin(plugin_id)

    async def shutdown(self):
        """Shutdown all plugins and cleanup.

        Idempotent, and safe to call concurrently with itself: the handles are
        cleared under the task lock before being awaited, so a second caller
        cannot cancel-and-await a task the first is already awaiting.
        """
        async with self._task_lock:
            self._shutting_down = True
            tasks = [self._health_check_task, self._idle_check_task]
            self._health_check_task = None
            self._idle_check_task = None

        for task in tasks:
            if task is None:
                continue
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

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

    def get_manifest(self, plugin_id: str) -> Optional["PluginManifest"]:
        """Get the manifest for a specific plugin."""
        return self._manifests.get(plugin_id)
