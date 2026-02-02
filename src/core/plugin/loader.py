"""
Plugin Loader

Discovers, loads, and manages Flyto plugins.

The loader uses Python's entry_points mechanism to discover plugins
installed via pip. Plugins must be published as Python packages with
the appropriate entry point configuration.

Usage:
    loader = PluginLoader()
    plugins = loader.discover_plugins()
    loader.install_plugin("flyto-plugin-slack")
    loader.uninstall_plugin("flyto-plugin-slack")
"""

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from importlib.metadata import distributions, entry_points
from pathlib import Path
from typing import Any, Dict, List, Optional

from .manifest import PluginManifest, PluginModule, PluginStatus

logger = logging.getLogger(__name__)


@dataclass
class InstalledPlugin:
    """Information about an installed plugin."""
    name: str
    version: str
    manifest: PluginManifest
    loaded: bool = False
    load_error: Optional[str] = None
    installed_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "manifest": self.manifest.to_dict(),
            "loaded": self.loaded,
            "load_error": self.load_error,
            "installed_at": self.installed_at.isoformat(),
        }


class PluginLoader:
    """
    Manages plugin discovery, loading, and lifecycle.

    The loader discovers plugins through Python's entry_points system
    and can install/uninstall plugins via pip.
    """

    PLUGIN_PREFIX = "flyto-plugin-"
    ENTRY_POINT_GROUP = "flyto.plugins"

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

    def discover_plugins(self, force: bool = False) -> Dict[str, InstalledPlugin]:
        """
        Discover installed Flyto plugins.

        Scans installed packages for flyto-plugin-* prefixed packages
        and loads their manifests.

        Args:
            force: If True, re-scan even if already initialized

        Returns:
            Dict mapping plugin name to InstalledPlugin
        """
        if self._initialized and not force:
            return self._plugins

        self._plugins = {}

        # Scan installed distributions
        for dist in distributions():
            name = dist.metadata.get("Name", "")
            if not name.startswith(self.PLUGIN_PREFIX):
                continue

            version = dist.metadata.get("Version", "0.0.0")

            try:
                # Try to load manifest from package
                manifest = self._load_manifest_from_dist(dist)
                if not manifest:
                    manifest = self._create_default_manifest(name, version, dist)

                manifest.status = PluginStatus.INSTALLED
                manifest.installed_version = version

                plugin = InstalledPlugin(
                    name=name,
                    version=version,
                    manifest=manifest,
                    loaded=False,
                )
                self._plugins[name] = plugin
                logger.info(f"Discovered plugin: {name} v{version}")

            except Exception as e:
                logger.warning(f"Failed to load plugin {name}: {e}")
                # Create a minimal entry for failed plugins
                manifest = PluginManifest(
                    name=name,
                    version=version,
                    description=f"Plugin {name} (failed to load manifest)",
                    status=PluginStatus.FAILED,
                )
                self._plugins[name] = InstalledPlugin(
                    name=name,
                    version=version,
                    manifest=manifest,
                    loaded=False,
                    load_error=str(e),
                )

        self._initialized = True
        logger.info(f"Discovered {len(self._plugins)} plugins")
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
            module = __import__(f"{package_name}.manifest", fromlist=["MANIFEST"])
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
            name: Plugin name

        Returns:
            True if loaded successfully
        """
        if name not in self._plugins:
            logger.warning(f"Plugin not found: {name}")
            return False

        plugin = self._plugins[name]
        if plugin.loaded:
            return True

        try:
            # Use entry points to load plugin modules
            eps = entry_points(group=self.ENTRY_POINT_GROUP)
            for ep in eps:
                if ep.name == name or ep.value.startswith(name.replace("-", "_")):
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
        if name not in self._plugins:
            return False

        plugin = self._plugins[name]
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

    def install_plugin(
        self,
        name: str,
        version: Optional[str] = None,
        upgrade: bool = False,
    ) -> bool:
        """
        Install a plugin from PyPI.

        Args:
            name: Plugin name (with or without flyto-plugin- prefix)
            version: Optional specific version
            upgrade: If True, upgrade existing installation

        Returns:
            True if installation successful
        """
        if not name.startswith(self.PLUGIN_PREFIX):
            name = f"{self.PLUGIN_PREFIX}{name}"

        package_spec = name
        if version:
            package_spec = f"{name}=={version}"

        cmd = [sys.executable, "-m", "pip", "install", package_spec]
        if upgrade:
            cmd.append("--upgrade")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                logger.info(f"Installed plugin: {name}")
                # Re-discover plugins
                self.discover_plugins(force=True)
                return True
            else:
                logger.error(f"Failed to install {name}: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"Installation timed out for {name}")
            return False
        except Exception as e:
            logger.error(f"Installation failed for {name}: {e}")
            return False

    def uninstall_plugin(self, name: str) -> bool:
        """
        Uninstall a plugin.

        Args:
            name: Plugin name

        Returns:
            True if uninstallation successful
        """
        if not name.startswith(self.PLUGIN_PREFIX):
            name = f"{self.PLUGIN_PREFIX}{name}"

        # First unload the plugin
        if name in self._plugins:
            self.unload_plugin(name)

        cmd = [sys.executable, "-m", "pip", "uninstall", "-y", name]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                logger.info(f"Uninstalled plugin: {name}")
                # Remove from plugins dict
                if name in self._plugins:
                    del self._plugins[name]
                return True
            else:
                logger.error(f"Failed to uninstall {name}: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"Uninstallation timed out for {name}")
            return False
        except Exception as e:
            logger.error(f"Uninstallation failed for {name}: {e}")
            return False

    def get_plugin(self, name: str) -> Optional[InstalledPlugin]:
        """Get plugin by name."""
        if not self._initialized:
            self.discover_plugins()
        return self._plugins.get(name)

    def get_all_plugins(self) -> List[InstalledPlugin]:
        """Get all installed plugins."""
        if not self._initialized:
            self.discover_plugins()
        return list(self._plugins.values())

    def get_plugin_modules(self, name: str) -> List[PluginModule]:
        """Get modules provided by a plugin."""
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
        updates = {}

        for name, plugin in self._plugins.items():
            try:
                # Use pip to check latest version
                cmd = [
                    sys.executable, "-m", "pip", "index", "versions", name
                ]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    # Parse output for latest version
                    # Output format: "package (X.Y.Z)"
                    output = result.stdout.strip()
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


def get_plugin_loader() -> PluginLoader:
    """Get the singleton plugin loader instance."""
    global _loader
    if _loader is None:
        _loader = PluginLoader()
    return _loader
