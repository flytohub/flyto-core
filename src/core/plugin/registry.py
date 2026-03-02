# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Plugin Registry

Fetches and caches the community plugin index from a remote registry.
The registry is a JSON file hosted on GitHub (or any URL) that lists
available plugins with metadata.

Usage:
    registry = PluginRegistry()
    plugins = registry.list_available()
    info = registry.get_plugin_info("flyto-plugin-slack")
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)

# Default registry URL (GitHub raw file)
DEFAULT_REGISTRY_URL = (
    "https://raw.githubusercontent.com/flytohub/flyto-plugins/main/registry.json"
)

# Cache TTL in seconds
CACHE_TTL = 3600  # 1 hour


class PluginRegistryEntry:
    """A plugin entry from the registry."""

    def __init__(self, data: dict):
        self.name: str = data.get("name", "")
        self.version: str = data.get("version", "0.0.0")
        self.description: str = data.get("description", "")
        self.author: str = data.get("author", "")
        self.homepage: str = data.get("homepage", "")
        self.repository: str = data.get("repository", "")
        self.license: str = data.get("license", "")
        self.categories: List[str] = data.get("categories", [])
        self.keywords: List[str] = data.get("keywords", [])
        self.icon: str = data.get("icon", "")
        self.downloads: int = data.get("downloads", 0)
        self.pypi_name: str = data.get("pypi_name", self.name)
        self.min_flyto_version: str = data.get("min_flyto_version", "")
        self.modules: List[dict] = data.get("modules", [])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "homepage": self.homepage,
            "repository": self.repository,
            "license": self.license,
            "categories": self.categories,
            "keywords": self.keywords,
            "icon": self.icon,
            "downloads": self.downloads,
            "pypi_name": self.pypi_name,
            "min_flyto_version": self.min_flyto_version,
            "modules": self.modules,
        }


class PluginRegistry:
    """
    Remote plugin registry client.

    Fetches the community plugin index and caches it locally.
    """

    def __init__(
        self,
        registry_url: Optional[str] = None,
        cache_dir: Optional[Path] = None,
    ):
        self._url = registry_url or DEFAULT_REGISTRY_URL
        self._cache_dir = cache_dir or Path.home() / ".flyto" / "plugins"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = self._cache_dir / "registry_cache.json"
        self._entries: List[PluginRegistryEntry] = []
        self._loaded = False

    def list_available(self, force_refresh: bool = False) -> List[PluginRegistryEntry]:
        """List all available plugins from the registry."""
        self._ensure_loaded(force_refresh)
        return self._entries

    def get_plugin_info(self, name: str) -> Optional[PluginRegistryEntry]:
        """Get info about a specific plugin."""
        self._ensure_loaded()
        for entry in self._entries:
            if entry.name == name or entry.pypi_name == name:
                return entry
        return None

    def search(self, query: str) -> List[PluginRegistryEntry]:
        """Search plugins by keyword."""
        self._ensure_loaded()
        query_lower = query.lower()
        results = []
        for entry in self._entries:
            if (
                query_lower in entry.name.lower()
                or query_lower in entry.description.lower()
                or any(query_lower in k.lower() for k in entry.keywords)
                or any(query_lower in c.lower() for c in entry.categories)
            ):
                results.append(entry)
        return results

    def _ensure_loaded(self, force: bool = False) -> None:
        """Load registry data from cache or remote."""
        if self._loaded and not force:
            return

        # Try cache first
        if not force and self._cache_file.exists():
            try:
                cache_data = json.loads(self._cache_file.read_text())
                cache_time = cache_data.get("_cached_at", 0)
                if time.time() - cache_time < CACHE_TTL:
                    self._entries = [
                        PluginRegistryEntry(p)
                        for p in cache_data.get("plugins", [])
                    ]
                    self._loaded = True
                    return
            except Exception as e:
                logger.debug(f"Cache read failed: {e}")

        # Fetch from remote
        try:
            self._fetch_remote()
        except Exception as e:
            logger.warning(f"Failed to fetch plugin registry: {e}")
            # Fall back to stale cache
            if self._cache_file.exists():
                try:
                    cache_data = json.loads(self._cache_file.read_text())
                    self._entries = [
                        PluginRegistryEntry(p)
                        for p in cache_data.get("plugins", [])
                    ]
                except Exception:
                    self._entries = []

        self._loaded = True

    def _fetch_remote(self) -> None:
        """Fetch registry from remote URL."""
        req = Request(self._url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        plugins = data.get("plugins", [])
        self._entries = [PluginRegistryEntry(p) for p in plugins]

        # Cache the result
        try:
            cache = {"_cached_at": time.time(), "plugins": plugins}
            self._cache_file.write_text(json.dumps(cache, indent=2))
        except Exception as e:
            logger.debug(f"Cache write failed: {e}")

        logger.info(f"Fetched {len(self._entries)} plugins from registry")
