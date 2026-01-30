"""
Routing Tests

Tests for dual-track routing logic.
Tasks: 2.4, 2.5, 2.6
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.runtime.routing import (
    ModuleRouter,
    RoutingConfig,
    RoutingResult,
    RoutingDecision,
    RoutingPreference,
    ModuleRoutingOverride,
    get_router,
    reset_router,
)
from src.core.runtime.invoke import (
    RuntimeInvoker,
    get_invoker,
    reset_invoker,
)


class TestPluginExistsUsesPlugin:
    """Test 2.4: Plugin exists → use plugin."""

    @pytest.fixture
    def router(self):
        """Create a router with plugin available."""
        router = ModuleRouter(RoutingConfig(
            default_prefer=RoutingPreference.PLUGIN,
            default_fallback_enabled=True,
        ))
        router.set_available_plugins({"database", "llm"})
        router.set_available_legacy({"database.query", "string.uppercase"})
        return router

    def test_plugin_available_uses_plugin(self, router):
        """Test that when plugin is available, it is used."""
        result = router.route("database.query")

        assert result.decision == RoutingDecision.USE_PLUGIN
        assert result.use_plugin is True
        assert result.plugin_id == "flyto-official/database"
        assert result.fallback_available is True  # Legacy also available

    def test_plugin_available_with_health_check(self, router):
        """Test that unhealthy plugin falls back."""
        router.set_plugin_health("flyto-official/database", False)

        result = router.route("database.query")

        # Should fall back to legacy since plugin unhealthy
        assert result.decision == RoutingDecision.FALLBACK_TO_LEGACY
        assert result.use_plugin is False

    def test_plugin_available_legacy_not_available(self, router):
        """Test plugin used when legacy not available."""
        result = router.route("llm.chat")  # Not in legacy set

        assert result.decision == RoutingDecision.USE_PLUGIN
        assert result.use_plugin is True
        assert result.fallback_available is False  # No legacy available

    def test_legacy_only_available(self, router):
        """Test legacy used when plugin not available."""
        result = router.route("string.uppercase")  # Not in plugin set

        assert result.decision == RoutingDecision.FALLBACK_TO_LEGACY
        assert result.use_plugin is False
        assert result.legacy_module_id == "string.uppercase"


class TestPluginFailsFallbackLegacy:
    """Test 2.5: Plugin fails → fallback legacy."""

    @pytest.fixture
    def router(self):
        """Create a router with both plugin and legacy available."""
        router = ModuleRouter(RoutingConfig(
            default_prefer=RoutingPreference.PLUGIN,
            default_fallback_enabled=True,
        ))
        router.set_available_plugins({"database"})
        router.set_available_legacy({"database.query"})
        return router

    def test_fallback_available_when_both_exist(self, router):
        """Test fallback is available when both handlers exist."""
        result = router.route("database.query")

        assert result.fallback_available is True
        assert result.use_plugin is True  # Primary is plugin

    def test_route_with_fallback_returns_legacy(self, router):
        """Test fallback routing returns legacy handler."""
        # Get initial route
        initial = router.route("database.query")
        assert initial.use_plugin is True

        # Simulate primary failure
        fallback = router.route_with_fallback("database.query", primary_failed=True)

        assert fallback.decision == RoutingDecision.FALLBACK_TO_LEGACY
        assert fallback.use_plugin is False

    def test_no_fallback_when_legacy_missing(self, router):
        """Test no fallback when legacy not available."""
        router.set_available_legacy(set())  # Remove legacy

        result = router.route("database.query")

        assert result.fallback_available is False

    @pytest.mark.asyncio
    async def test_invoker_uses_legacy_when_no_plugin(self):
        """Test RuntimeInvoker uses legacy module when no plugin available."""
        reset_invoker()
        reset_router()

        invoker = RuntimeInvoker()

        # Use real legacy module - for legacy modules, step_id should be empty
        result = await invoker.invoke(
            module_id="string.uppercase",
            step_id="",  # Empty for legacy format
            input_data={"text": "test"},
            config={},
            context={},
        )

        # Should succeed via legacy
        assert result["ok"] is True
        assert result["data"]["result"] == "TEST"


class TestForcePluginNoFallback:
    """Test 2.6: force plugin → no fallback."""

    @pytest.fixture
    def router(self):
        """Create a router with force plugin config."""
        router = ModuleRouter(RoutingConfig(
            default_prefer=RoutingPreference.PLUGIN,
            default_fallback_enabled=True,
            force_plugin_default=True,  # Force plugin mode
        ))
        router.set_available_plugins({"database"})
        router.set_available_legacy({"database.query"})
        return router

    def test_force_plugin_no_fallback(self, router):
        """Test force plugin mode has no fallback."""
        result = router.route("database.query")

        assert result.decision == RoutingDecision.USE_PLUGIN
        assert result.use_plugin is True
        assert result.fallback_available is False  # No fallback in force mode

    def test_force_plugin_fails_when_unhealthy(self, router):
        """Test force plugin returns error when plugin unhealthy."""
        router.set_plugin_health("flyto-official/database", False)

        result = router.route("database.query")

        assert result.decision == RoutingDecision.NO_HANDLER
        assert result.use_plugin is False
        assert "unhealthy" in result.reason.lower()

    def test_force_plugin_via_override(self):
        """Test force plugin via per-module override."""
        router = ModuleRouter(RoutingConfig(
            default_prefer=RoutingPreference.PLUGIN,
            default_fallback_enabled=True,
            force_plugin_default=False,  # Not forced globally
            overrides=[
                ModuleRoutingOverride(
                    module_pattern="database.*",
                    force_plugin=True,  # Force for database
                ),
            ],
        ))
        router.set_available_plugins({"database"})
        router.set_available_legacy({"database.query", "string.uppercase"})

        # database.query should be forced to plugin
        db_result = router.route("database.query")
        assert db_result.fallback_available is False

        # string.uppercase should have fallback
        str_result = router.route("string.uppercase")
        # String not in plugins, so it falls back to legacy
        assert str_result.use_plugin is False


class TestRoutingOverrides:
    """Test per-module routing overrides."""

    def test_override_matches_exact(self):
        """Test exact module match."""
        override = ModuleRoutingOverride(
            module_pattern="database.query",
            force_plugin=True,
        )

        assert override.matches("database.query") is True
        assert override.matches("database.insert") is False

    def test_override_matches_wildcard(self):
        """Test category wildcard match."""
        override = ModuleRoutingOverride(
            module_pattern="database.*",
            force_plugin=True,
        )

        assert override.matches("database.query") is True
        assert override.matches("database.insert") is True
        assert override.matches("llm.chat") is False

    def test_override_matches_global(self):
        """Test global wildcard match."""
        override = ModuleRoutingOverride(
            module_pattern="*",
            prefer=RoutingPreference.LEGACY,
        )

        assert override.matches("database.query") is True
        assert override.matches("anything") is True

    def test_override_disabled_module(self):
        """Test disabled module returns no handler."""
        router = ModuleRouter(RoutingConfig(
            overrides=[
                ModuleRoutingOverride(
                    module_pattern="deprecated.*",
                    disabled=True,
                    reason="Module deprecated, use new API",
                ),
            ],
        ))
        router.set_available_legacy({"deprecated.old_func"})

        result = router.route("deprecated.old_func")

        assert result.decision == RoutingDecision.NO_HANDLER
        assert "disabled" in result.reason.lower()

    def test_force_legacy_mode(self):
        """Test force legacy mode."""
        router = ModuleRouter(RoutingConfig(
            overrides=[
                ModuleRoutingOverride(
                    module_pattern="string.*",
                    force_legacy=True,
                ),
            ],
        ))
        router.set_available_plugins({"string"})
        router.set_available_legacy({"string.uppercase"})

        result = router.route("string.uppercase")

        assert result.decision == RoutingDecision.USE_LEGACY
        assert result.use_plugin is False
        assert result.fallback_available is False


class TestRoutingConfig:
    """Test routing configuration."""

    def test_config_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            "defaultPrefer": "plugin",
            "defaultFallback": True,
            "forcePluginDefault": False,
            "overrides": [
                {
                    "module": "database.*",
                    "prefer": "plugin",
                    "forcePlugin": True,
                },
                {
                    "module": "deprecated.*",
                    "disabled": True,
                    "reason": "Use new API",
                },
            ],
        }

        config = RoutingConfig.from_dict(data)

        assert config.default_prefer == RoutingPreference.PLUGIN
        assert config.default_fallback_enabled is True
        assert len(config.overrides) == 2
        assert config.overrides[0].force_plugin is True
        assert config.overrides[1].disabled is True

    def test_config_to_dict(self):
        """Test serializing config to dictionary."""
        config = RoutingConfig(
            default_prefer=RoutingPreference.PLUGIN,
            overrides=[
                ModuleRoutingOverride(
                    module_pattern="test.*",
                    force_plugin=True,
                ),
            ],
        )

        data = config.to_dict()

        assert data["defaultPrefer"] == "plugin"
        assert len(data["overrides"]) == 1
        assert data["overrides"][0]["forcePlugin"] is True


class TestPreferLegacy:
    """Test prefer legacy mode."""

    @pytest.fixture
    def router(self):
        """Create a router preferring legacy."""
        router = ModuleRouter(RoutingConfig(
            default_prefer=RoutingPreference.LEGACY,
            default_fallback_enabled=True,
        ))
        router.set_available_plugins({"database"})
        router.set_available_legacy({"database.query"})
        return router

    def test_prefer_legacy_uses_legacy(self, router):
        """Test legacy preferred when available."""
        result = router.route("database.query")

        assert result.decision == RoutingDecision.USE_LEGACY
        assert result.use_plugin is False
        assert result.fallback_available is True  # Plugin available as fallback

    def test_prefer_legacy_fallback_to_plugin(self, router):
        """Test fallback to plugin when legacy missing."""
        router.set_available_legacy(set())

        result = router.route("database.query")

        assert result.decision == RoutingDecision.FALLBACK_TO_PLUGIN
        assert result.use_plugin is True
