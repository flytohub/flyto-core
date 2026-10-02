# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Extension (Plugin) Loader

Discovers, loads, and manages Flyto2 Core extensions.

An *extension* is a pip-installable Python distribution that Core is willing to
manage. Exactly two shapes are supported, and the pair is the whole contract —
there is no third kind, and no per-extension special case anywhere in this file:

    flyto-modules-*   declaring entry points in group ``flyto.modules``
    flyto-plugin-*    declaring entry points in group ``flyto.plugins``

Everything downstream (naming, install, entry-point proof, registry refresh) is
driven off the ``EXTENSION_KINDS`` table, so a new module pack such as
``flyto-modules-robotics`` is managed by the generic path the day it is
published: nothing here names it, and nothing here has to change for it.

The loader uses Python's entry_points mechanism to discover extensions
installed via pip. Extensions must be published as Python packages with
the appropriate entry point configuration.

Usage:
    loader = PluginLoader()
    plugins = loader.discover_plugins()
    loader.install_extension("flyto-modules-robotics")
    loader.uninstall_extension("flyto-modules-robotics")

    # Historical plugin-only API, preserved:
    loader.install_plugin("flyto-plugin-slack")
    loader.uninstall_plugin("flyto-plugin-slack")
"""

import importlib
import json
import logging
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from importlib.metadata import PackageNotFoundError, distributions, entry_points
from importlib.metadata import version as _dist_version
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .manifest import PluginManifest, PluginModule, PluginStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Extension kinds — the entire supported surface, as data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtensionKind:
    """One supported extension shape: a name prefix and its entry-point group.

    Frozen because this table is process-global and read on every install: a
    caller that could rewrite ``prefix`` or ``entry_point_group`` in place would
    be redefining what Core is willing to install from, everywhere at once.
    """

    kind: str
    prefix: str
    entry_point_group: str


#: Module packs: contribute modules to ``ModuleRegistry`` via ``flyto.modules``.
MODULES_KIND = ExtensionKind("modules", "flyto-modules-", "flyto.modules")
#: Plugins: contribute integrations via ``flyto.plugins``.
PLUGINS_KIND = ExtensionKind("plugins", "flyto-plugin-", "flyto.plugins")

#: The supported set. Ordered longest-prefix-first so classification is
#: unambiguous even if a future prefix is a prefix of another.
EXTENSION_KINDS: Tuple[ExtensionKind, ...] = (MODULES_KIND, PLUGINS_KIND)


class ExtensionErrorCode:
    """Stable, machine-readable failure codes.

    These are part of the API contract: callers (CLI, HTTP clients, the desktop
    app) branch on them. The human-readable message that travels with a code is
    fixed too — see ``EXTENSION_ERROR_MESSAGES`` — so that no failure ever
    returns interpreter paths, index URLs, or pip stderr to a caller. Diagnostic
    detail is logged locally instead.
    """

    UNSUPPORTED_EXTENSION = "unsupported_extension"
    INVALID_NAME = "invalid_name"
    INVALID_VERSION = "invalid_version"
    NOT_INSTALLED = "not_installed"
    INSTALL_FAILED = "install_failed"
    UNINSTALL_FAILED = "uninstall_failed"
    ENTRYPOINT_MISSING = "entrypoint_missing"
    ROLLBACK_FAILED = "rollback_failed"
    TIMEOUT = "timeout"


EXTENSION_ERROR_MESSAGES: Dict[str, str] = {
    ExtensionErrorCode.UNSUPPORTED_EXTENSION: (
        "Unsupported extension name. Supported: flyto-modules-* and flyto-plugin-*."
    ),
    ExtensionErrorCode.INVALID_NAME: "Extension name is not a valid package name.",
    ExtensionErrorCode.INVALID_VERSION: "Requested version is not a valid version string.",
    ExtensionErrorCode.NOT_INSTALLED: "Extension is not installed.",
    ExtensionErrorCode.INSTALL_FAILED: "Extension install failed; see server logs.",
    ExtensionErrorCode.UNINSTALL_FAILED: "Extension uninstall failed; see server logs.",
    ExtensionErrorCode.ENTRYPOINT_MISSING: (
        "Package installed but declares no Flyto2 entry point; it is not an extension."
    ),
    ExtensionErrorCode.ROLLBACK_FAILED: (
        "Package installed but declares no Flyto2 entry point, and rollback failed; "
        "see server logs."
    ),
    ExtensionErrorCode.TIMEOUT: "Package manager timed out; see server logs.",
}


def classify_extension(name: str) -> Optional[ExtensionKind]:
    """The kind ``name`` belongs to, or None if Core will not manage it.

    Matching is done on the PEP 503 normalised name so ``Flyto_Modules_Robotics``
    and ``flyto-modules-robotics`` classify identically — pip treats them as one
    project, and a gate that disagreed with pip about that would be a gate with a
    bypass rather than a gate.
    """
    normalized = normalize_extension_name(name)
    for kind in EXTENSION_KINDS:
        if normalized.startswith(kind.prefix) and len(normalized) > len(kind.prefix):
            return kind
    return None


def normalize_extension_name(name: str) -> str:
    """PEP 503 normalised distribution name (lowercase, runs of ._- → -)."""
    return re.sub(r"[-_.]+", "-", (name or "").strip()).lower()


@dataclass
class ExtensionResult:
    """Outcome of one install/uninstall attempt.

    Every field here is safe to serialise to an API client: there is
    deliberately no place to put subprocess output.
    """

    ok: bool
    name: str
    kind: Optional[str] = None
    code: Optional[str] = None
    message: str = ""
    version: Optional[str] = None
    previous_version: Optional[str] = None
    entry_points: List[str] = field(default_factory=list)
    restart_required: bool = False
    rolled_back: bool = False
    #: True when pip did what it was asked but Core could not rebuild what it
    #: believes is installed. The package on disk and the running process have
    #: diverged, and only a restart closes the gap — so this never travels
    #: alone: every path that sets it also sets ``restart_required``.
    refresh_failed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "name": self.name,
            "kind": self.kind,
            "code": self.code,
            "message": self.message,
            "version": self.version,
            "previous_version": self.previous_version,
            "entry_points": list(self.entry_points),
            "restart_required": self.restart_required,
            "rolled_back": self.rolled_back,
            "refresh_failed": self.refresh_failed,
        }


@dataclass
class _PipRun:
    """Result of one pip subprocess. ``stderr`` never leaves this process."""

    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


def _iter_entry_points(group: str) -> List[Any]:
    """Entry points in ``group``, as a list.

    Materialised rather than lazy: entry-point proof walks the group and then
    reports what it found, and an exhausted iterator would make the second read
    conclude the package declared nothing. Read through the module-level
    ``entry_points`` name so a test can substitute a group without building and
    installing a distribution to do it.
    """
    if sys.version_info >= (3, 10):
        return list(entry_points(group=group))
    return list(entry_points().get(group, []))


def _entry_point_dist_name(ep: Any) -> Optional[str]:
    """Normalised distribution name that published ``ep``, if it can be read.

    ``EntryPoint.dist`` only exists from Python 3.10; on 3.9 it is None and the
    caller falls back to matching the entry point's module root. The fallback is
    deliberately second: the distribution name is the fact, and the module root
    is a convention a package is free to break.
    """
    dist = getattr(ep, "dist", None)
    if dist is None:
        return None
    try:
        return normalize_extension_name(dist.metadata["Name"])
    except Exception:  # pragma: no cover - malformed metadata
        return None


@dataclass
class InstalledPlugin:
    """Information about an installed extension.

    ``kind`` defaults to the plugin kind so every pre-existing construction site
    — this file's own discovery pass included, before it learned about module
    packs — keeps producing exactly the record it produced before.
    """
    name: str
    version: str
    manifest: PluginManifest
    loaded: bool = False
    load_error: Optional[str] = None
    installed_at: datetime = field(default_factory=datetime.utcnow)
    kind: str = PLUGINS_KIND.kind

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "manifest": self.manifest.to_dict(),
            "loaded": self.loaded,
            "load_error": self.load_error,
            "installed_at": self.installed_at.isoformat(),
            "kind": self.kind,
        }


class PluginLoader:
    """
    Manages extension discovery, loading, and lifecycle.

    The loader discovers extensions through Python's entry_points system
    and can install/uninstall them via pip. Both supported kinds go through
    one code path; ``EXTENSION_KINDS`` is the only place the kinds are named.
    """

    # Retained as the plugin-kind defaults so existing callers of the
    # plugin-only API (CLI, PluginService) keep resolving bare names the way
    # they always have. Generic code reads EXTENSION_KINDS, not these.
    PLUGIN_PREFIX = PLUGINS_KIND.prefix
    ENTRY_POINT_GROUP = PLUGINS_KIND.entry_point_group

    #: Bounded so a hung index cannot pin a request thread forever.
    INSTALL_TIMEOUT = 120
    UNINSTALL_TIMEOUT = 60
    # PEP 503 normalised package name: starts and ends with alnum, can
    # contain ._- in between. Mirrors what pip itself accepts so we don't
    # build a spec string that fails validation later.
    _VALID_PACKAGE_NAME = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?$")
    # PEP 440 version core — refuses junk like "1.0; rm -rf /" or
    # "1.0 --extra-index-url=http://evil" even though subprocess list-form
    # would treat the whole thing as one positional arg. Defensive: keeps
    # pip from seeing anything pip wasn't built to handle.
    _VALID_VERSION = re.compile(r"^[a-zA-Z0-9_.+!*-]{1,64}$")

    # IMPORTANT — supply-chain risk:
    # install_extension shells out to `pip install <name>`. pip resolves
    # the package from PyPI and executes its setup.py / pyproject build
    # backend, which is arbitrary code. The prefix gate limits what
    # attacker-supplied `name` values reach pip, and entry-point proof
    # limits what a *successful* install is allowed to be called, but
    # neither defends against a hostile publisher of an otherwise-
    # legitimate `flyto-modules-foo` / `flyto-plugin-foo` name — build
    # hooks run before any proof can be taken. Operators should:
    #   - run flyto-core under an unprivileged user
    #   - mount only what extensions legitimately need
    #   - consider an index allowlist (--index-url to a private mirror)
    # The HTTP surface (/v1/extensions) is authenticated and, for the
    # mutating routes, additionally gated behind an explicit operator
    # opt-in env var — see core.api.routes.extensions.

    def __init__(self, plugins_dir: Optional[Path] = None):
        """
        Initialize plugin loader.

        Args:
            plugins_dir: Optional directory for plugin configuration
        """
        self._plugins: Dict[str, InstalledPlugin] = {}
        self._plugins_dir = plugins_dir or Path.home() / ".flyto" / "plugins"
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
        self._initialized = False
        # One lock over every read *and* every mutation of this loader. It is a
        # process-wide singleton reached from every API worker thread, so both
        # halves need it:
        #
        # * pip is not safe to run twice at once against one environment — two
        #   installs interleaving can leave a half-written distribution, and the
        #   entry-point proof of one can read the other's files;
        # * a read taken while a mutation is between pip and its refresh is a
        #   read of records that describe neither the old install nor the new
        #   one, and a read taken *during* the refresh would iterate a mapping
        #   another thread is rebuilding.
        #
        # Reentrant, and that is load-bearing rather than a convenience: a
        # mutation holds this lock and then calls the public reads under it —
        # ``_refresh_after_change`` calls ``discover_plugins``, and an uninstall
        # calls ``unload_plugin``. With a plain Lock the very first install would
        # deadlock against itself. Reentrancy is therefore only ever exercised
        # by a read nested inside a mutation; no path re-enters install or
        # uninstall, so no nested pip run is reachable through it.
        self._lock = threading.RLock()

    def discover_plugins(self, force: bool = False) -> Dict[str, InstalledPlugin]:
        """
        Discover installed Flyto2 extensions.

        Scans installed packages for every supported extension prefix
        (flyto-modules-* and flyto-plugin-*) and loads their manifests. The
        method name is historical; it is the manifest-refresh pass for both
        kinds, and a module pack nobody has heard of yet is picked up here by
        prefix alone.

        Args:
            force: If True, re-scan even if already initialized

        Returns:
            Dict mapping PEP 503 normalised extension name to InstalledPlugin
        """
        with self._lock:
            if self._initialized and not force:
                return self._plugins

            # Built to the side and swapped in at the end. A scan that raises
            # part-way — a distribution with unreadable metadata, an importer
            # error — must not leave the loader holding a half-populated map
            # that it would then report as the truth: the previous records are
            # stale but coherent, a truncated rebuild is neither.
            discovered: Dict[str, InstalledPlugin] = {}

            # Scan installed distributions
            for dist in distributions():
                name = dist.metadata.get("Name", "")
                kind = classify_extension(name)
                if kind is None:
                    continue

                version = dist.metadata.get("Version", "0.0.0")
                # Keyed *and named* by the PEP 503 normalised name, never by the
                # spelling the distribution happens to declare. pip, the
                # entry-point proof and every caller-supplied name already
                # normalise; a record filed under "Flyto_Modules_Robotics" sits
                # under a key no lookup in this class ever forms again, so an
                # uninstall would leave it behind and the API would keep
                # reporting a pack that is no longer on disk. The name is
                # normalised too, so the id a client reads back from
                # ``list_extensions`` is one it can hand straight to uninstall;
                # the on-disk spelling stays available on the manifest.
                key = normalize_extension_name(name)

                try:
                    # Try to load manifest from package
                    manifest = self._load_manifest_from_dist(dist)
                    if not manifest:
                        manifest = self._create_default_manifest(name, version, dist)

                    manifest.status = PluginStatus.INSTALLED
                    manifest.installed_version = version

                    plugin = InstalledPlugin(
                        name=key,
                        version=version,
                        manifest=manifest,
                        loaded=False,
                        kind=kind.kind,
                    )
                    discovered[key] = plugin
                    logger.info(f"Discovered {kind.kind} extension: {name} v{version}")

                except Exception as e:
                    logger.warning(f"Failed to load extension {name}: {e}")
                    # Create a minimal entry for failed extensions
                    manifest = PluginManifest(
                        name=name,
                        version=version,
                        description=f"Extension {name} (failed to load manifest)",
                        status=PluginStatus.FAILED,
                    )
                    discovered[key] = InstalledPlugin(
                        name=key,
                        version=version,
                        manifest=manifest,
                        loaded=False,
                        load_error=str(e),
                        kind=kind.kind,
                    )

            self._plugins = discovered
            self._initialized = True
            logger.info(f"Discovered {len(self._plugins)} extensions")
            return self._plugins

    def _load_manifest_from_dist(self, dist) -> Optional[PluginManifest]:
        """Load manifest from installed distribution."""
        # Try to find plugin.manifest.json in package files
        try:
            files = dist.files or []
            for file in files:
                if file.name == "plugin.manifest.json":
                    content = file.read_text()
                    data = json.loads(content)
                    return PluginManifest.from_dict(data)
        except Exception as e:
            logger.debug(f"Could not load manifest from files: {e}")

        # Try to import manifest from package
        try:
            package_name = dist.metadata.get("Name", "").replace("-", "_")
            module = importlib.import_module(f"{package_name}.manifest")
            if hasattr(module, "MANIFEST"):
                return PluginManifest.from_dict(module.MANIFEST)
        except ImportError:
            pass

        return None

    def _create_default_manifest(self, name: str, version: str, dist) -> PluginManifest:
        """Create default manifest from distribution metadata."""
        metadata = dist.metadata

        return PluginManifest(
            name=name,
            version=version,
            description=metadata.get("Summary", f"Plugin {name}"),
            author=metadata.get("Author", ""),
            author_email=metadata.get("Author-email"),
            homepage=metadata.get("Home-page"),
            license=metadata.get("License", ""),
            keywords=metadata.get_all("Keyword") or [],
        )

    def load_plugin(self, name: str) -> bool:
        """
        Load a plugin's modules into the registry.

        Args:
            name: Plugin name, in any spelling pip would accept for it

        Returns:
            True if loaded successfully
        """
        with self._lock:
            return self._load_plugin_locked(name)

    def _load_plugin_locked(self, name: str) -> bool:
        """Body of ``load_plugin``; callers must hold ``_lock``."""
        key = normalize_extension_name(name)
        if key not in self._plugins:
            logger.warning(f"Plugin not found: {name}")
            return False

        plugin = self._plugins[key]
        if plugin.loaded:
            return True

        try:
            # Use entry points to load the extension's modules. The group comes
            # from the extension's own kind, so a module pack is loaded from
            # flyto.modules rather than searched for in flyto.plugins and
            # silently found to contribute nothing.
            kind = classify_extension(name) or PLUGINS_KIND
            eps = _iter_entry_points(kind.entry_point_group)
            module_root = key.replace("-", "_")
            for ep in eps:
                if ep.name in (name, key) or ep.value.startswith(module_root):
                    # Load the entry point
                    register_func = ep.load()
                    if callable(register_func):
                        register_func()
                        logger.info(f"Loaded plugin entry point: {ep.name}")

            plugin.loaded = True
            plugin.load_error = None
            return True

        except Exception as e:
            logger.error(f"Failed to load plugin {name}: {e}")
            plugin.load_error = str(e)
            return False

    def unload_plugin(self, name: str) -> bool:
        """
        Unload a plugin's modules from the registry.

        Note: This does not uninstall the package, just removes
        modules from the active registry.

        Args:
            name: Plugin name

        Returns:
            True if unloaded successfully
        """
        with self._lock:
            return self._unload_plugin_locked(name)

    def _unload_plugin_locked(self, name: str) -> bool:
        """Body of ``unload_plugin``; callers must hold ``_lock``."""
        key = normalize_extension_name(name)
        if key not in self._plugins:
            return False

        plugin = self._plugins[key]
        if not plugin.loaded:
            return True

        try:
            # Remove modules from registry
            from core.modules.registry import ModuleRegistry

            for module in plugin.manifest.modules:
                if ModuleRegistry.has(module.module_id):
                    ModuleRegistry.unregister(module.module_id)

            plugin.loaded = False
            return True

        except Exception as e:
            logger.error(f"Failed to unload plugin {name}: {e}")
            return False

    @staticmethod
    def _pip_env() -> Dict[str, str]:
        """Scrubbed environment for pip subprocesses.

        Starts from the shared sandbox allowlist (PATH/HOME/locale/SSL certs) and
        re-injects only the pip/proxy variables pip legitimately needs, so a
        malicious package's build hooks cannot harvest host secrets from
        os.environ. FLYTO_SANDBOX_INHERIT_ENV=1 restores full inheritance.
        """
        import os as _os

        from core.safe_env import build_sandbox_env

        passthrough = {}
        for key, value in _os.environ.items():
            upper = key.upper()
            if (
                upper.startswith("PIP_")
                or upper.startswith("PYTHON")
                or upper in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                             "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
                             "VIRTUAL_ENV")
            ):
                passthrough[key] = value
        return build_sandbox_env(passthrough)

    def _run_pip(self, args: List[str], timeout: int) -> _PipRun:
        """Run one pip subprocess with a fixed argv vector and a scrubbed env.

        Two properties this function exists to hold:

        * **argv, never a shell.** ``args`` is a list and ``shell`` is left at
          its default False, so no element of it is ever word-split, glob
          expanded, or read as a redirection — a version string containing
          ``;`` reaches pip as one positional argument rather than a second
          command. The name/version regexes upstream are a second wall, not this
          one.
        * **environment, never inherited wholesale.** install runs the package's
          build hooks (setup.py / PEP 517 backend) as host code; ``_pip_env``
          hands it PATH, locale, certs and pip/proxy variables and nothing else,
          so a hostile package cannot read host secrets out of ``os.environ``.

        ``--no-input`` and ``--disable-pip-version-check`` are prepended to every
        vector: a pip that pauses for a prompt inside a request handler is a hung
        request, and the version-check network call is not work anyone asked for.
        """
        cmd = [sys.executable, "-m", "pip", args[0], "--no-input",
               "--disable-pip-version-check", *args[1:]]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._pip_env(),
            )
            return _PipRun(
                returncode=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
            )
        except subprocess.TimeoutExpired:
            return _PipRun(returncode=-1, timed_out=True)
        except Exception as e:  # pragma: no cover - defensive
            return _PipRun(returncode=-1, stderr=str(e))

    @staticmethod
    def installed_version(name: str) -> Optional[str]:
        """Installed version of ``name``, or None if it is not installed.

        Asked *before* an install so the caller can tell a first install from an
        upgrade, and that distinction drives two decisions that must not be
        guessed: whether a failed entry-point proof may roll the package back,
        and whether the process must be restarted for the change to take effect.
        """
        try:
            return _dist_version(name)
        except PackageNotFoundError:
            return None
        except Exception:  # pragma: no cover - defensive
            return None

    @staticmethod
    def entry_points_for(kind: ExtensionKind, name: str) -> List[str]:
        """Entry-point names ``name`` publishes into its kind's group.

        This is the *proof* that a package pip happily installed is actually an
        extension. pip will install any project whose name matches the prefix —
        including a typosquat, an empty placeholder, or a package that simply
        forgot its ``[project.entry-points]`` block — and every one of those
        leaves Core with a package it will never load and a caller who was told
        the install succeeded. An empty list here means "not an extension".

        Caches are invalidated first: the distribution was written to disk
        seconds ago by a subprocess, and the importer in this process still
        remembers the directory listing from before it existed.
        """
        importlib.invalidate_caches()
        target = normalize_extension_name(name)
        module_root = target.replace("-", "_")
        found: List[str] = []
        for ep in _iter_entry_points(kind.entry_point_group):
            dist_name = _entry_point_dist_name(ep)
            if dist_name is not None:
                if dist_name == target:
                    found.append(str(getattr(ep, "name", "")))
                continue
            # Python 3.9: no ep.dist. Fall back to the module root the entry
            # point resolves through, which is the convention module packs
            # follow (flyto-modules-robotics -> flyto_modules_robotics.*).
            value = str(getattr(ep, "value", ""))
            if value.split(":")[0].split(".")[0] == module_root:
                found.append(str(getattr(ep, "name", "")))
        return sorted({name_ for name_ in found if name_})

    def _refresh_after_change(self, kind: ExtensionKind) -> bool:
        """Rebuild what Core believes is installed, after pip changed it.

        Returns True when Core's records are consistent with disk again, and
        False when they are not — a registry that could not be rebuilt is a
        process serving stale answers, and the caller turns that into
        ``refresh_failed``/``restart_required`` rather than logging it and
        reporting an unqualified success.

        Two records go stale on every install/uninstall and neither rebuilds
        itself: this loader's manifest map, and — for the kind whose entry-point
        group the module registry reads — the registry's own plugin/module
        tables. Refreshing only the first leaves ``/v1/extensions`` reporting a
        module pack that ``/v1/modules`` has never heard of.

        Which kind touches the registry is decided by comparing entry-point
        groups with the registry itself, not by naming a kind here: the registry
        owns the definition of the group it loads from.

        Nothing in here is allowed to raise. It runs *after* pip has already
        changed the environment, so an exception escaping would abandon a
        completed install half-reported — the caller would see a 500 for a
        package that is on disk, with no ``restart_required`` telling anyone how
        to recover. Every failure is caught, logged with its traceback, and
        turned into a False that the caller renders as
        ``refresh_failed``/``restart_required``.
        """
        refreshed = True

        try:
            self.discover_plugins(force=True)
        except Exception:
            # The manifest scan reads every installed distribution's metadata;
            # one unreadable distribution must not cost the caller its result.
            logger.exception("Manifest refresh failed after %s change", kind.kind)
            refreshed = False

        try:
            from core.modules.registry import ModuleRegistry
            from core.modules.registry.core import ENTRY_POINT_GROUP as REGISTRY_GROUP
        except Exception:  # pragma: no cover - registry always importable in-tree
            logger.exception("Module registry unavailable; manifests refreshed only")
            return False

        if kind.entry_point_group != REGISTRY_GROUP:
            # Nothing further to rebuild: this kind does not contribute to the
            # module registry, so the manifest pass above is the whole refresh.
            return refreshed

        try:
            ModuleRegistry.refresh()
        except Exception:
            # A refresh that raises must not turn a completed install into a
            # reported failure — the package is on disk either way. Restart
            # recovers the registry; the log says why one is needed, and the
            # returned False makes the caller say so in its result too.
            logger.exception("Module registry refresh failed after %s change", kind.kind)
            return False

        return refreshed

    @staticmethod
    def _failure(
        name: str,
        code: str,
        kind: Optional[ExtensionKind] = None,
        **extra: Any,
    ) -> ExtensionResult:
        """An ExtensionResult carrying a stable code and its fixed message."""
        return ExtensionResult(
            ok=False,
            name=name,
            kind=kind.kind if kind else None,
            code=code,
            message=EXTENSION_ERROR_MESSAGES[code],
            **extra,
        )

    def install_extension(
        self,
        name: str,
        version: Optional[str] = None,
        upgrade: bool = False,
    ) -> ExtensionResult:
        """Install (or upgrade) one extension under the loader lock.

        The lock is taken here rather than around pip alone: proof, rollback and
        refresh all read the environment pip just wrote, so a second install
        admitted between any two of those steps would have the first one drawing
        conclusions about the second one's files.
        """
        with self._lock:
            return self._install_extension_locked(name, version=version, upgrade=upgrade)

    def _install_extension_locked(
        self,
        name: str,
        version: Optional[str] = None,
        upgrade: bool = False,
    ) -> ExtensionResult:
        """Install (or upgrade) one extension, and prove it is one.

        Callers must hold ``_lock``; ``install_extension`` is the entry point
        that takes it.

        Every id this returns is the PEP 503 normalised name, whatever spelling
        the caller used. A client that installs ``Flyto_Modules_Robotics`` and
        reads ``name`` back off the result gets the same id ``list_extensions``
        reports and the same id ``uninstall_extension`` matches on — one name
        for one package, across every surface.

        The sequence is: classify → validate → remember the prior version →
        pip → prove an entry point exists → refresh Core's records. A failure at
        the proof step of a *first* install is rolled back, because the only
        thing on disk is a package Core cannot use and did not have before; a
        failure at the proof step of an upgrade is not, because rolling back
        would uninstall the working version the operator already had.

        Args:
            name: Full extension name (``flyto-modules-*`` / ``flyto-plugin-*``).
                Unprefixed names are rejected rather than guessed: a bare
                ``robotics`` is ambiguous between the two kinds, and picking one
                would install a different package than the caller named.
            version: Optional exact version to pin.
            upgrade: If True, allow pip to replace an existing installation.

        Returns:
            ExtensionResult. Never raises for an install failure, and never
            carries subprocess output.
        """
        key = normalize_extension_name(name)

        kind = classify_extension(name)
        if kind is None:
            logger.warning("Refusing to install unsupported extension: %r", name)
            return self._failure(key, ExtensionErrorCode.UNSUPPORTED_EXTENSION)

        if not self._VALID_PACKAGE_NAME.match(name):
            logger.warning("Refusing invalid package name: %r", name)
            return self._failure(key, ExtensionErrorCode.INVALID_NAME, kind)

        package_spec = name
        if version:
            if not self._VALID_VERSION.match(version):
                logger.warning("Refusing invalid version for %s: %r", name, version)
                return self._failure(key, ExtensionErrorCode.INVALID_VERSION, kind)
            package_spec = f"{name}=={version}"

        previous_version = self.installed_version(name)
        was_installed = previous_version is not None

        args = ["install", package_spec]
        if upgrade:
            args.append("--upgrade")

        run = self._run_pip(args, timeout=self.INSTALL_TIMEOUT)
        if run.timed_out:
            logger.error("pip install timed out for %s after %ss", name, self.INSTALL_TIMEOUT)
            return self._failure(key, ExtensionErrorCode.TIMEOUT, kind,
                                 previous_version=previous_version)
        if run.returncode != 0:
            # stderr is logged, never returned: it carries interpreter paths,
            # index URLs and occasionally credentials embedded in an index URL.
            logger.error("pip install failed for %s (rc=%s): %s",
                         name, run.returncode, run.stderr.strip())
            return self._failure(key, ExtensionErrorCode.INSTALL_FAILED, kind,
                                 previous_version=previous_version)

        eps = self.entry_points_for(kind, name)
        if not eps:
            logger.error(
                "%s installed but declares no %s entry point; not an extension",
                name, kind.entry_point_group,
            )
            if was_installed:
                # An upgrade that landed a broken version. Uninstalling here
                # would leave the operator with nothing where they used to have
                # a working extension, so the package stays and the caller is
                # told the truth about it.
                return self._failure(key, ExtensionErrorCode.ENTRYPOINT_MISSING, kind,
                                     previous_version=previous_version,
                                     version=self.installed_version(name),
                                     restart_required=True)

            rollback = self._run_pip(["uninstall", "-y", name], timeout=self.UNINSTALL_TIMEOUT)
            if rollback.timed_out or rollback.returncode != 0:
                logger.error("Rollback of %s failed (rc=%s, timed_out=%s): %s",
                             name, rollback.returncode, rollback.timed_out,
                             rollback.stderr.strip())
                return self._failure(key, ExtensionErrorCode.ROLLBACK_FAILED, kind)
            logger.info("Rolled back non-extension package: %s", name)
            refreshed = self._refresh_after_change(kind)
            return self._failure(key, ExtensionErrorCode.ENTRYPOINT_MISSING, kind,
                                 rolled_back=True,
                                 refresh_failed=not refreshed,
                                 restart_required=not refreshed)

        refreshed = self._refresh_after_change(kind)
        installed = self.installed_version(name) or version

        # An upgrade replaces code this process has already imported, and Python
        # does not un-import. discover/refresh updates what Core *reports*; only
        # a restart changes what it is *running*. A first install has nothing
        # already imported, so it takes effect immediately — unless the refresh
        # itself failed, in which case even a first install is not live in this
        # process and saying otherwise would send the operator looking for a
        # module that is on disk but unreachable.
        restart_required = was_installed or not refreshed

        message = "Extension upgraded." if was_installed else "Extension installed."
        if not refreshed:
            message += " Core could not reload it; restart to pick it up."

        logger.info("Installed %s extension %s v%s (restart_required=%s, refresh_failed=%s)",
                    kind.kind, name, installed, restart_required, not refreshed)
        return ExtensionResult(
            ok=True,
            name=key,
            kind=kind.kind,
            version=installed,
            previous_version=previous_version,
            entry_points=eps,
            restart_required=restart_required,
            refresh_failed=not refreshed,
            message=message,
        )

    def uninstall_extension(self, name: str) -> ExtensionResult:
        """Uninstall one extension under the loader lock.

        Same reason as ``install_extension``: unload, pip and refresh are one
        transaction as far as Core's records are concerned.
        """
        with self._lock:
            return self._uninstall_extension_locked(name)

    def _uninstall_extension_locked(self, name: str) -> ExtensionResult:
        """Uninstall one extension.

        Always reports ``restart_required``: the extension's modules are already
        imported into this interpreter and removing the files on disk does not
        remove them from ``sys.modules``. Callers must hold ``_lock``;
        ``uninstall_extension`` is the entry point that takes it.

        As with install, every id returned is the PEP 503 normalised name, so
        uninstalling ``Flyto_Modules_Robotics`` reports the same id the listing
        used for it.
        """
        key = normalize_extension_name(name)

        kind = classify_extension(name)
        if kind is None:
            logger.warning("Refusing to uninstall unsupported extension: %r", name)
            return self._failure(key, ExtensionErrorCode.UNSUPPORTED_EXTENSION)

        if not self._VALID_PACKAGE_NAME.match(name):
            logger.warning("Refusing invalid package name: %r", name)
            return self._failure(key, ExtensionErrorCode.INVALID_NAME, kind)

        previous_version = self.installed_version(name)
        if previous_version is None:
            return self._failure(key, ExtensionErrorCode.NOT_INSTALLED, kind)

        if key in self._plugins:
            self.unload_plugin(key)

        run = self._run_pip(["uninstall", "-y", name], timeout=self.UNINSTALL_TIMEOUT)
        if run.timed_out:
            logger.error("pip uninstall timed out for %s after %ss",
                         name, self.UNINSTALL_TIMEOUT)
            return self._failure(key, ExtensionErrorCode.TIMEOUT, kind,
                                 previous_version=previous_version)
        if run.returncode != 0:
            logger.error("pip uninstall failed for %s (rc=%s): %s",
                         name, run.returncode, run.stderr.strip())
            return self._failure(key, ExtensionErrorCode.UNINSTALL_FAILED, kind,
                                 previous_version=previous_version)

        self._plugins.pop(key, None)
        refreshed = self._refresh_after_change(kind)
        message = "Extension uninstalled."
        if not refreshed:
            message += " Core could not rebuild its registry; restart to clear it."
        logger.info("Uninstalled %s extension: %s (refresh_failed=%s)",
                    kind.kind, name, not refreshed)
        return ExtensionResult(
            ok=True,
            name=key,
            kind=kind.kind,
            previous_version=previous_version,
            restart_required=True,
            refresh_failed=not refreshed,
            message=message,
        )

    def list_extensions(self) -> List[Dict[str, Any]]:
        """Every installed extension, of both kinds, as plain dicts.

        Entry points are reported per extension so a caller can see the same
        proof the installer checked — an extension listed with an empty
        ``entry_points`` is installed but contributes nothing.

        Held under the loader lock for the whole walk: a listing taken while an
        install is between pip and its refresh describes neither the old state
        nor the new one, and one taken during the refresh would iterate a
        mapping another thread is rebuilding.
        """
        with self._lock:
            return self._list_extensions_locked()

    def _list_extensions_locked(self) -> List[Dict[str, Any]]:
        """Body of ``list_extensions``; callers must hold ``_lock``."""
        extensions = []
        for plugin in self.get_all_plugins():
            kind = classify_extension(plugin.name)
            manifest = plugin.manifest
            status = getattr(manifest, "status", None) if manifest else None
            extensions.append({
                "name": plugin.name,
                "kind": plugin.kind,
                "version": plugin.version,
                "loaded": plugin.loaded,
                "load_error": plugin.load_error,
                # A manifest read from JSON may carry status as a bare string
                # rather than the enum; report either without raising.
                "status": getattr(status, "value", status),
                "description": manifest.description if manifest else "",
                "module_count": manifest.module_count if manifest else 0,
                "entry_points": self.entry_points_for(kind, plugin.name) if kind else [],
            })
        return sorted(extensions, key=lambda e: e["name"])

    def install_plugin(
        self,
        name: str,
        version: Optional[str] = None,
        upgrade: bool = False,
    ) -> bool:
        """
        Install a plugin from PyPI.

        Preserved plugin-kind API: a bare name is still resolved against the
        plugin prefix, and the return value is still a bool. The work is done by
        ``install_extension``, so this path gained entry-point proof and rollback
        rather than keeping a second, weaker installer beside it.

        Args:
            name: Plugin name (with or without flyto-plugin- prefix)
            version: Optional specific version
            upgrade: If True, upgrade existing installation

        Returns:
            True if installation successful
        """
        if classify_extension(name) is None:
            name = f"{self.PLUGIN_PREFIX}{name}"
        return self.install_extension(name, version=version, upgrade=upgrade).ok

    def uninstall_plugin(self, name: str) -> bool:
        """
        Uninstall a plugin.

        Preserved plugin-kind API; see ``install_plugin``.

        Args:
            name: Plugin name

        Returns:
            True if uninstallation successful
        """
        if classify_extension(name) is None:
            name = f"{self.PLUGIN_PREFIX}{name}"
        return self.uninstall_extension(name).ok

    def get_plugin(self, name: str) -> Optional[InstalledPlugin]:
        """Get plugin by name, in any spelling pip would accept for it."""
        with self._lock:
            if not self._initialized:
                self.discover_plugins()
            return self._plugins.get(normalize_extension_name(name))

    def get_all_plugins(self) -> List[InstalledPlugin]:
        """Get all installed plugins."""
        with self._lock:
            if not self._initialized:
                self.discover_plugins()
            return list(self._plugins.values())

    def get_plugin_modules(self, name: str) -> List[PluginModule]:
        """Get modules provided by a plugin."""
        with self._lock:
            plugin = self.get_plugin(name)
            if plugin:
                return plugin.manifest.modules
            return []

    def check_updates(self) -> Dict[str, str]:
        """
        Check for available updates for installed plugins.

        Returns:
            Dict mapping plugin name to latest available version
        """
        with self._lock:
            return self._check_updates_locked()

    def _check_updates_locked(self) -> Dict[str, str]:
        """Body of ``check_updates``; callers must hold ``_lock``.

        This is the one read that talks to the index, so it is also the one read
        that must not overlap an install: ``pip index`` and ``pip install``
        against a single environment are not safe to interleave. It is never
        reached from inside a mutation, so the pip run it performs is always a
        top-level one — the lock never nests a pip run inside another.
        """
        updates = {}

        for name, plugin in self._plugins.items():
            try:
                # Same argv-only, scrubbed-env path as install/uninstall: this
                # one talks to the index too, and an update check is not a
                # reason to hand a subprocess the host environment.
                run = self._run_pip(["index", "versions", name], timeout=30)

                if run.returncode == 0:
                    # Parse output for latest version
                    # Output format: "package (X.Y.Z)"
                    output = run.stdout.strip()
                    if "(" in output and ")" in output:
                        latest = output.split("(")[1].split(")")[0]
                        if latest != plugin.version:
                            updates[name] = latest
                            plugin.manifest.status = PluginStatus.UPDATE_AVAILABLE

            except Exception as e:
                logger.debug(f"Failed to check updates for {name}: {e}")

        return updates

    def save_state(self) -> None:
        """Save plugin state to disk."""
        state_file = self._plugins_dir / "state.json"
        with self._lock:
            state = {
                name: plugin.to_dict()
                for name, plugin in self._plugins.items()
            }
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

    def load_state(self) -> None:
        """Load plugin state from disk."""
        state_file = self._plugins_dir / "state.json"
        if not state_file.exists():
            return

        try:
            with open(state_file) as f:
                state = json.load(f)
            # State loading is informational; actual plugins come from pip
            logger.debug(f"Loaded plugin state: {len(state)} entries")
        except Exception as e:
            logger.warning(f"Failed to load plugin state: {e}")


# Singleton instance
_loader: Optional[PluginLoader] = None

#: Guards construction of the singleton above. Separate from the loader's own
#: lock for the obvious reason: the instance that owns that lock is what this
#: one is protecting the creation of.
_loader_lock = threading.Lock()


def get_plugin_loader() -> PluginLoader:
    """Get the singleton plugin loader instance.

    Double-checked under ``_loader_lock`` because every API worker thread
    reaches this function and an unguarded ``if _loader is None`` is a race that
    defeats the loader's own locking outright: two threads that both see None
    build two loaders with two different ``_lock`` objects, and two pip runs
    against one environment then proceed in parallel — exactly what the loader
    lock exists to prevent. One thread would also be left mutating an instance
    the other has already replaced in this global.
    """
    global _loader
    if _loader is None:
        with _loader_lock:
            if _loader is None:
                _loader = PluginLoader()
    return _loader
