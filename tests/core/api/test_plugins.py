"""
Plugin API Tests

Tests for Frontend Integration.
Tasks: F.10 - F.14
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.runtime.transformer import (
    transform_manifest_to_modules,
    transform_step_to_module,
    merge_plugin_modules_with_core,
    transform_modules_for_tiered_response,
)
from src.core.api.plugins.service import (
    PluginService,
    PluginServiceConfig,
    get_plugin_service,
)


class TestPluginsInstalledReturnsModuleItemShape:
    """Test F.10: /plugins/installed returns exact ModuleItem shape."""

    @pytest.fixture
    def sample_manifest(self):
        """Sample plugin manifest."""
        return {
            "id": "flyto-official_database",
            "name": "Database Operations",
            "version": "1.0.0",
            "vendor": "flyto-official",
            "description": "SQL database operations",
            "entryPoint": "main.py",
            "runtime": {"language": "python", "minVersion": "3.9"},
            "permissions": ["network", "secrets.read"],
            "meta": {
                "icon": "Database",
                "color": "#6366F1",
                "category": "database",
                "tags": ["database", "sql"],
            },
            "steps": [
                {
                    "id": "query",
                    "label": "Execute SQL Query",
                    "description": "Execute a SQL query on a database",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "SQL query"},
                            "params": {"type": "array", "description": "Query params"},
                        },
                        "required": ["query"],
                    },
                    "outputSchema": {
                        "type": "object",
                        "properties": {
                            "rows": {"type": "array"},
                            "rowCount": {"type": "integer"},
                        },
                    },
                    "cost": {"points": 1, "class": "standard"},
                    "ui": {"icon": "Database", "color": "#6366F1"},
                    "tags": ["sql", "query"],
                },
            ],
        }

    def test_transform_produces_module_item_shape(self, sample_manifest):
        """Test that transformer produces correct ModuleItem shape."""
        modules = transform_manifest_to_modules(sample_manifest)

        assert len(modules) == 1
        module = modules[0]

        # Required ModuleItem fields
        assert "module_id" in module
        assert module["module_id"] == "database.query"

        assert "label" in module
        assert module["label"] == "Execute SQL Query"

        assert "label_key" in module
        assert module["label_key"] == "modules.database.query.label"

        assert "description" in module
        assert "description_key" in module

        assert "category" in module
        assert module["category"] == "database"

        assert "icon" in module
        assert module["icon"] == "Database"

        assert "color" in module
        assert module["color"] == "#6366F1"

        assert "level" in module
        assert module["level"] == 2  # Plugin level

        assert "version" in module
        assert module["version"] == "1.0.0"

        assert "params_schema" in module
        assert "output_schema" in module

        assert "input_types" in module
        assert "output_types" in module
        assert "can_receive_from" in module
        assert "can_connect_to" in module

        assert "ui" in module
        assert "tags" in module

        # Plugin-specific fields
        assert "source" in module
        assert module["source"] == "plugin"

        assert "plugin_id" in module
        assert module["plugin_id"] == "flyto-official_database"

    def test_params_schema_converted_correctly(self, sample_manifest):
        """Test inputSchema is converted to params_schema format."""
        modules = transform_manifest_to_modules(sample_manifest)
        module = modules[0]

        params_schema = module["params_schema"]

        assert params_schema["type"] == "object"
        assert "properties" in params_schema
        assert "query" in params_schema["properties"]
        assert params_schema["properties"]["query"]["type"] == "string"
        assert params_schema["properties"]["query"]["required"] is True


class TestPluginModulesAppearInAddNodeMenu:
    """Test F.11: Plugin modules appear in Add Node menu."""

    def test_merge_with_core_modules(self):
        """Test plugin modules are merged with core modules."""
        core_modules = [
            {
                "module_id": "string.uppercase",
                "label": "Uppercase",
                "category": "string",
                "source": "core",
            },
        ]

        plugin_modules = [
            {
                "module_id": "database.query",
                "label": "SQL Query",
                "category": "database",
                "source": "plugin",
                "plugin_id": "flyto-official_database",
            },
        ]

        merged = merge_plugin_modules_with_core(core_modules, plugin_modules)

        # Both modules should be present
        module_ids = [m["module_id"] for m in merged]
        assert "string.uppercase" in module_ids
        assert "database.query" in module_ids

    def test_plugin_overrides_core_with_same_id(self):
        """Test plugin module overrides core module with same ID."""
        core_modules = [
            {
                "module_id": "database.query",
                "label": "Core Query",
                "source": "core",
            },
        ]

        plugin_modules = [
            {
                "module_id": "database.query",
                "label": "Plugin Query",
                "source": "plugin",
                "plugin_id": "flyto-official_database",
            },
        ]

        merged = merge_plugin_modules_with_core(core_modules, plugin_modules)

        # Only one module with that ID
        query_modules = [m for m in merged if m["module_id"] == "database.query"]
        assert len(query_modules) == 1

        # Plugin version wins
        assert query_modules[0]["source"] == "plugin"
        assert query_modules[0]["label"] == "Plugin Query"
        assert query_modules[0]["has_core_fallback"] is True


class TestPluginModulesCanBeAddedToWorkflow:
    """Test F.12: Plugin modules can be added to workflow."""

    def test_module_has_connection_rules(self):
        """Test module has can_receive_from and can_connect_to."""
        manifest = {
            "id": "test-plugin",
            "name": "Test",
            "version": "1.0.0",
            "vendor": "test",
            "steps": [
                {
                    "id": "test_step",
                    "label": "Test Step",
                    "inputSchema": {"type": "object"},
                    "outputSchema": {"type": "object"},
                },
            ],
        }

        modules = transform_manifest_to_modules(manifest)
        module = modules[0]

        # Should have connection rules for workflow editor
        assert module["can_receive_from"] == ["*"]
        assert module["can_connect_to"] == ["*"]
        assert module["input_types"] == ["*"]
        assert "output_types" in module


class TestPluginModuleExecutionWorks:
    """Test F.13: Plugin module execution works."""

    @pytest.fixture
    def plugin_service(self, tmp_path):
        """Create plugin service with temp directory."""
        # Create plugin directory
        plugin_dir = tmp_path / "flyto-official_test"
        plugin_dir.mkdir()

        manifest = {
            "id": "flyto-official_test",
            "name": "Test Plugin",
            "version": "1.0.0",
            "vendor": "test",
            "description": "Test plugin",
            "entryPoint": "main.py",
            "steps": [
                {
                    "id": "echo",
                    "label": "Echo",
                    "inputSchema": {"type": "object"},
                    "outputSchema": {"type": "object"},
                },
            ],
        }

        manifest_path = plugin_dir / "plugin.manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        # Create service
        config = PluginServiceConfig(plugins_dir=str(tmp_path))
        service = PluginService(config=config)

        return service

    def test_install_plugin(self, plugin_service):
        """Test plugin installation."""
        result = plugin_service.install_plugin("flyto-official_test")

        assert result["ok"] is True
        assert result["plugin_id"] == "flyto-official_test"
        assert "echo" in result["steps"]

    def test_get_installed_modules_after_install(self, plugin_service):
        """Test getting modules after installation."""
        plugin_service.install_plugin("flyto-official_test")

        modules = plugin_service.get_installed_modules()

        assert len(modules) == 1
        assert modules[0]["module_id"] == "test.echo"
        assert modules[0]["source"] == "plugin"


class TestDeprecatedPluginsShowWarning:
    """Test F.14: Deprecated plugins show warning."""

    def test_deprecated_status_in_module(self):
        """Test deprecated status is included in module."""
        manifest = {
            "id": "deprecated-plugin",
            "name": "Old Plugin",
            "version": "1.0.0",
            "vendor": "test",
            "steps": [
                {
                    "id": "old_step",
                    "label": "Old Step",
                    "deprecatedMessage": "Use new_step instead",
                },
            ],
        }

        modules = transform_manifest_to_modules(manifest, plugin_status="deprecated")

        module = modules[0]
        assert module["deprecated"] is True
        assert module["plugin_status"] == "deprecated"
        assert module["deprecated_message"] == "Use new_step instead"

    def test_active_plugin_not_deprecated(self):
        """Test active plugin is not marked deprecated."""
        manifest = {
            "id": "active-plugin",
            "name": "Active Plugin",
            "version": "1.0.0",
            "vendor": "test",
            "steps": [{"id": "step", "label": "Step"}],
        }

        modules = transform_manifest_to_modules(manifest, plugin_status="active")

        module = modules[0]
        assert module["deprecated"] is False


class TestTieredModulesFiltering:
    """Test tier-based module filtering."""

    def test_free_tier_filters_premium(self):
        """Test free tier cannot access premium modules."""
        modules = [
            {
                "module_id": "free.module",
                "cost": {"class": "free", "points": 0},
            },
            {
                "module_id": "standard.module",
                "cost": {"class": "standard", "points": 1},
            },
            {
                "module_id": "premium.module",
                "cost": {"class": "premium", "points": 3},
            },
        ]

        filtered = transform_modules_for_tiered_response(modules, tier="free")

        module_ids = [m["module_id"] for m in filtered]
        assert "free.module" in module_ids
        assert "standard.module" in module_ids
        assert "premium.module" not in module_ids

    def test_pro_tier_accesses_all(self):
        """Test pro tier can access premium modules."""
        modules = [
            {
                "module_id": "premium.module",
                "cost": {"class": "premium", "points": 3},
            },
        ]

        filtered = transform_modules_for_tiered_response(modules, tier="pro")

        assert len(filtered) == 1
        assert filtered[0]["tier_access"] is True


class TestCatalogOperations:
    """Test catalog operations."""

    @pytest.fixture
    def service_with_plugins(self, tmp_path):
        """Create service with sample plugins."""
        # Create two plugins
        for i in range(2):
            plugin_dir = tmp_path / f"plugin_{i}"
            plugin_dir.mkdir()

            manifest = {
                "id": f"plugin_{i}",
                "name": f"Plugin {i}",
                "version": "1.0.0",
                "vendor": "test",
                "description": f"Test plugin {i}",
                "entryPoint": "main.py",
                "meta": {"icon": "Box", "color": "#000000", "category": "test"},
                "steps": [{"id": "step", "label": "Step"}],
            }

            (plugin_dir / "plugin.manifest.json").write_text(json.dumps(manifest))

        config = PluginServiceConfig(plugins_dir=str(tmp_path))
        return PluginService(config=config)

    def test_get_catalog(self, service_with_plugins):
        """Test getting plugin catalog."""
        catalog = service_with_plugins.get_catalog()

        assert len(catalog) == 2
        assert all("id" in p for p in catalog)
        assert all("name" in p for p in catalog)
        assert all("steps" in p for p in catalog)

    def test_catalog_etag_changes_on_update(self, service_with_plugins):
        """Test ETag changes when catalog changes."""
        etag1 = service_with_plugins.get_catalog_etag()

        # Install a plugin
        service_with_plugins.install_plugin("plugin_0")

        etag2 = service_with_plugins.get_catalog_etag()

        # ETag should change
        assert etag1 != etag2
