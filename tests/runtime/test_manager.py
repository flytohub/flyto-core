"""
Tests for PluginManager with multi-language manifest support.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.runtime.manager import (
    PluginManifest,
    PluginManager,
    PluginInfo,
    RuntimeConfig,
)


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
            "author": "developer@example.com",  # 'author' instead of 'vendor'
        }
        manifest = PluginManifest.from_dict(data)
        assert manifest.vendor == "developer@example.com"


class TestPluginManagerDiscovery:
    """Tests for PluginManager plugin discovery."""

    @pytest.fixture
    def plugin_dir(self):
        """Create temporary plugin directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_discover_json_manifest(self, plugin_dir):
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
        import asyncio
        manager = PluginManager(plugin_dir)
        discovered = asyncio.get_event_loop().run_until_complete(
            manager.discover_plugins()
        )

        assert "test-plugin" in discovered

    def test_discover_yaml_manifest(self, plugin_dir):
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
        import asyncio
        manager = PluginManager(plugin_dir)
        discovered = asyncio.get_event_loop().run_until_complete(
            manager.discover_plugins()
        )

        assert "node-plugin" in discovered

    def test_discover_multiple_languages(self, plugin_dir):
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
        import asyncio
        manager = PluginManager(plugin_dir)
        discovered = asyncio.get_event_loop().run_until_complete(
            manager.discover_plugins()
        )

        assert "py-plugin" in discovered
        assert "node-plugin" in discovered
        assert len(discovered) == 2


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
