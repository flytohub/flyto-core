"""
Plugin Service

Business logic for plugin management operations.
Used by API routes and can be used directly by other services.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ...runtime.manager import PluginManager, PluginManifest, PluginInfo
from ...runtime.transformer import (
    transform_manifest_to_modules,
    merge_plugin_modules_with_core,
    transform_modules_for_tiered_response,
)

logger = logging.getLogger(__name__)


@dataclass
class PluginCatalogItem:
    """Plugin item for marketplace catalog."""
    id: str
    name: str
    version: str
    vendor: str
    description: str
    icon: str
    color: str
    category: str
    tags: List[str]
    steps: List[Dict[str, Any]]
    permissions: List[str]
    installed: bool = False
    status: str = "available"  # available, installed, deprecated


@dataclass
class PluginServiceConfig:
    """Configuration for plugin service."""
    plugins_dir: str = "/plugins"
    catalog_cache_ttl: int = 300  # 5 minutes
    enable_marketplace: bool = True


class PluginService:
    """
    Service for plugin management operations.

    Provides:
    - Plugin discovery and catalog
    - Plugin installation/uninstallation
    - Plugin loading/unloading
    - Module transformation for frontend
    """

    def __init__(
        self,
        plugin_manager: Optional[PluginManager] = None,
        config: Optional[PluginServiceConfig] = None,
    ):
        self.plugin_manager = plugin_manager
        self.config = config or PluginServiceConfig()

        # Cache for catalog
        self._catalog_cache: Optional[List[PluginCatalogItem]] = None
        self._catalog_etag: Optional[str] = None

        # Installed plugins
        self._installed_plugins: Dict[str, PluginManifest] = {}

    def set_plugin_manager(self, manager: PluginManager):
        """Set the plugin manager instance."""
        self.plugin_manager = manager

    # ==================== Catalog Operations ====================

    def get_catalog(self, include_installed: bool = True) -> List[Dict[str, Any]]:
        """
        Get plugin catalog for marketplace.

        Returns list of available plugins with their metadata.
        """
        catalog = []

        # Discover plugins from plugins directory
        plugins_path = Path(self.config.plugins_dir)
        if plugins_path.exists():
            for plugin_dir in plugins_path.iterdir():
                if not plugin_dir.is_dir():
                    continue

                manifest_path = plugin_dir / "plugin.manifest.json"
                if not manifest_path.exists():
                    continue

                try:
                    with open(manifest_path) as f:
                        manifest_data = json.load(f)

                    plugin_id = manifest_data.get("id", plugin_dir.name)
                    is_installed = plugin_id in self._installed_plugins

                    if not include_installed and is_installed:
                        continue

                    catalog_item = self._manifest_to_catalog_item(
                        manifest_data,
                        installed=is_installed,
                    )
                    catalog.append(catalog_item)

                except Exception as e:
                    logger.warning(f"Failed to load manifest from {plugin_dir}: {e}")

        return catalog

    def get_catalog_etag(self) -> str:
        """Generate ETag for catalog caching."""
        catalog = self.get_catalog()
        content = json.dumps(catalog, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()

    # ==================== Installed Plugins ====================

    def get_installed_plugins(self) -> List[Dict[str, Any]]:
        """
        Get list of installed plugins.

        Returns plugins in the exact format expected by frontend.
        """
        installed = []

        for plugin_id, manifest in self._installed_plugins.items():
            plugin_info = {
                "id": plugin_id,
                "name": manifest.name,
                "version": manifest.version,
                "vendor": manifest.vendor,
                "description": manifest.description,
                "status": "active",
                "steps": [s["id"] for s in manifest.steps],
            }
            installed.append(plugin_info)

        return installed

    def get_installed_modules(self) -> List[Dict[str, Any]]:
        """
        Get modules from installed plugins in frontend format.

        This is the key method for zero-frontend-change integration.
        Returns modules in exact ModuleItem format.
        """
        modules = []

        for plugin_id, manifest in self._installed_plugins.items():
            manifest_dict = manifest.to_dict() if hasattr(manifest, 'to_dict') else manifest.__dict__
            plugin_modules = transform_manifest_to_modules(
                manifest_dict,
                plugin_status="active",
            )
            modules.extend(plugin_modules)

        return modules

    # ==================== Plugin Installation ====================

    def install_plugin(self, plugin_id: str) -> Dict[str, Any]:
        """
        Install a plugin.

        Args:
            plugin_id: Plugin ID to install

        Returns:
            Installation result with status and details
        """
        # Find plugin in catalog
        plugins_path = Path(self.config.plugins_dir)
        plugin_dir = None

        for candidate in plugins_path.iterdir():
            if not candidate.is_dir():
                continue
            manifest_path = candidate / "plugin.manifest.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path) as f:
                        manifest_data = json.load(f)
                    if manifest_data.get("id") == plugin_id:
                        plugin_dir = candidate
                        break
                except Exception:
                    continue

        if not plugin_dir:
            return {
                "ok": False,
                "error": f"Plugin not found: {plugin_id}",
            }

        # Load manifest
        manifest_path = plugin_dir / "plugin.manifest.json"
        with open(manifest_path) as f:
            manifest_data = json.load(f)

        manifest = PluginManifest.from_dict(manifest_data)

        # Register as installed
        self._installed_plugins[plugin_id] = manifest

        # Load plugin if manager available
        if self.plugin_manager:
            try:
                self.plugin_manager.load_plugin(plugin_id, str(plugin_dir))
            except Exception as e:
                logger.warning(f"Failed to load plugin {plugin_id}: {e}")

        logger.info(f"Installed plugin: {plugin_id}")

        return {
            "ok": True,
            "plugin_id": plugin_id,
            "version": manifest.version,
            "steps": [s["id"] for s in manifest.steps],
        }

    def uninstall_plugin(self, plugin_id: str) -> Dict[str, Any]:
        """
        Uninstall a plugin.

        Args:
            plugin_id: Plugin ID to uninstall

        Returns:
            Uninstallation result
        """
        if plugin_id not in self._installed_plugins:
            return {
                "ok": False,
                "error": f"Plugin not installed: {plugin_id}",
            }

        # Unload plugin if manager available
        if self.plugin_manager:
            try:
                self.plugin_manager.unload_plugin(plugin_id)
            except Exception as e:
                logger.warning(f"Failed to unload plugin {plugin_id}: {e}")

        # Remove from installed
        del self._installed_plugins[plugin_id]

        logger.info(f"Uninstalled plugin: {plugin_id}")

        return {
            "ok": True,
            "plugin_id": plugin_id,
        }

    # ==================== Plugin Loading ====================

    def load_plugin(self, plugin_id: str) -> Dict[str, Any]:
        """
        Load (start) a plugin process.

        Args:
            plugin_id: Plugin ID to load

        Returns:
            Load result with status
        """
        if plugin_id not in self._installed_plugins:
            return {
                "ok": False,
                "error": f"Plugin not installed: {plugin_id}",
            }

        if not self.plugin_manager:
            return {
                "ok": False,
                "error": "Plugin manager not available",
            }

        try:
            # Find plugin directory
            plugins_path = Path(self.config.plugins_dir)
            plugin_dir = None

            for candidate in plugins_path.iterdir():
                manifest_path = candidate / "plugin.manifest.json"
                if manifest_path.exists():
                    try:
                        with open(manifest_path) as f:
                            manifest_data = json.load(f)
                        if manifest_data.get("id") == plugin_id:
                            plugin_dir = candidate
                            break
                    except Exception:
                        continue

            if not plugin_dir:
                return {
                    "ok": False,
                    "error": f"Plugin directory not found: {plugin_id}",
                }

            self.plugin_manager.load_plugin(plugin_id, str(plugin_dir))

            return {
                "ok": True,
                "plugin_id": plugin_id,
                "status": "loaded",
            }

        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_id}: {e}")
            return {
                "ok": False,
                "error": str(e),
            }

    def unload_plugin(self, plugin_id: str) -> Dict[str, Any]:
        """
        Unload (stop) a plugin process.

        Args:
            plugin_id: Plugin ID to unload

        Returns:
            Unload result with status
        """
        if not self.plugin_manager:
            return {
                "ok": False,
                "error": "Plugin manager not available",
            }

        try:
            self.plugin_manager.unload_plugin(plugin_id)

            return {
                "ok": True,
                "plugin_id": plugin_id,
                "status": "unloaded",
            }

        except Exception as e:
            logger.error(f"Failed to unload plugin {plugin_id}: {e}")
            return {
                "ok": False,
                "error": str(e),
            }

    # ==================== Module Integration ====================

    def get_merged_modules(
        self,
        core_modules: List[Dict[str, Any]],
        tier: str = "free",
    ) -> List[Dict[str, Any]]:
        """
        Get merged core + plugin modules for /modules/tiered endpoint.

        This enables zero-frontend-change plugin integration.

        Args:
            core_modules: List of core module items
            tier: User tier for filtering

        Returns:
            Merged module list
        """
        plugin_modules = self.get_installed_modules()

        merged = merge_plugin_modules_with_core(core_modules, plugin_modules)

        return transform_modules_for_tiered_response(merged, tier)

    # ==================== Helper Methods ====================

    def _manifest_to_catalog_item(
        self,
        manifest: Dict[str, Any],
        installed: bool = False,
    ) -> Dict[str, Any]:
        """Convert manifest to catalog item format."""
        meta = manifest.get("meta", {})

        return {
            "id": manifest.get("id"),
            "name": manifest.get("name"),
            "version": manifest.get("version"),
            "vendor": manifest.get("vendor"),
            "description": manifest.get("description"),
            "icon": meta.get("icon", "Box"),
            "color": meta.get("color", "#6B7280"),
            "category": meta.get("category", "other"),
            "tags": meta.get("tags", []),
            "steps": [
                {
                    "id": s.get("id"),
                    "label": s.get("label"),
                    "description": s.get("description"),
                }
                for s in manifest.get("steps", [])
            ],
            "permissions": manifest.get("permissions", []),
            "installed": installed,
            "status": "installed" if installed else "available",
        }

    def discover_and_install_all(self):
        """
        Discover and install all plugins from plugins directory.

        Called during startup to auto-load plugins.
        """
        plugins_path = Path(self.config.plugins_dir)
        if not plugins_path.exists():
            logger.info(f"Plugins directory not found: {plugins_path}")
            return

        for plugin_dir in plugins_path.iterdir():
            if not plugin_dir.is_dir():
                continue

            manifest_path = plugin_dir / "plugin.manifest.json"
            if not manifest_path.exists():
                continue

            try:
                with open(manifest_path) as f:
                    manifest_data = json.load(f)

                plugin_id = manifest_data.get("id")
                if plugin_id:
                    self.install_plugin(plugin_id)

            except Exception as e:
                logger.warning(f"Failed to auto-install plugin from {plugin_dir}: {e}")


# Global singleton
_plugin_service: Optional[PluginService] = None


def get_plugin_service(
    plugin_manager: Optional[PluginManager] = None,
    config: Optional[PluginServiceConfig] = None,
) -> PluginService:
    """Get global plugin service instance."""
    global _plugin_service
    if _plugin_service is None:
        _plugin_service = PluginService(plugin_manager, config)
    return _plugin_service
