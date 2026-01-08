"""
Tests for capabilities enforcement.

Tests the capability checking and production policy enforcement.
"""
import os
import pytest
from src.core.constants import Capability, ProductionPolicy, ErrorCode
from src.core.modules.runtime import check_capabilities, execute_module


class TestProductionPolicy:
    """Test ProductionPolicy class."""

    def test_production_denies_shell_exec(self):
        """Test that shell.exec is denied in production."""
        assert not ProductionPolicy.is_capability_allowed(
            Capability.SHELL_EXEC, "production"
        )

    def test_production_denies_network_localhost(self):
        """Test that network.localhost is denied in production."""
        assert not ProductionPolicy.is_capability_allowed(
            Capability.NETWORK_LOCALHOST, "production"
        )

    def test_production_denies_network_private(self):
        """Test that network.private is denied in production."""
        assert not ProductionPolicy.is_capability_allowed(
            Capability.NETWORK_PRIVATE, "production"
        )

    def test_production_allows_network_public(self):
        """Test that network.public is allowed in production."""
        assert ProductionPolicy.is_capability_allowed(
            Capability.NETWORK_PUBLIC, "production"
        )

    def test_production_allows_browser_control(self):
        """Test that browser.control is allowed in production."""
        assert ProductionPolicy.is_capability_allowed(
            Capability.BROWSER_CONTROL, "production"
        )

    def test_staging_denies_shell_exec(self):
        """Test that shell.exec is denied in staging."""
        assert not ProductionPolicy.is_capability_allowed(
            Capability.SHELL_EXEC, "staging"
        )

    def test_staging_allows_network_localhost(self):
        """Test that network.localhost is allowed in staging."""
        assert ProductionPolicy.is_capability_allowed(
            Capability.NETWORK_LOCALHOST, "staging"
        )

    def test_development_allows_all(self):
        """Test that development allows all capabilities."""
        assert ProductionPolicy.is_capability_allowed(
            Capability.SHELL_EXEC, "development"
        )
        assert ProductionPolicy.is_capability_allowed(
            Capability.NETWORK_LOCALHOST, "development"
        )
        assert ProductionPolicy.is_capability_allowed(
            Capability.DESKTOP_CONTROL, "development"
        )

    def test_local_allows_all(self):
        """Test that local allows all capabilities."""
        assert ProductionPolicy.is_capability_allowed(
            Capability.SHELL_EXEC, "local"
        )
        assert ProductionPolicy.is_capability_allowed(
            Capability.NETWORK_PRIVATE, "local"
        )

    def test_unknown_env_uses_production_policy(self):
        """Test that unknown environment uses production policy (safest)."""
        assert not ProductionPolicy.is_capability_allowed(
            Capability.SHELL_EXEC, "unknown_env"
        )


class TestCheckCapabilities:
    """Test check_capabilities function."""

    def test_returns_none_for_empty_capabilities(self):
        """Test that empty capabilities return None (allowed)."""
        result = check_capabilities([], "test.module")
        assert result is None

    def test_returns_none_for_none_capabilities(self):
        """Test that None capabilities return None (allowed)."""
        result = check_capabilities(None, "test.module")
        assert result is None

    def test_returns_none_for_allowed_capabilities(self):
        """Test that allowed capabilities return None."""
        result = check_capabilities(
            [Capability.NETWORK_PUBLIC, Capability.BROWSER_CONTROL],
            "test.module",
            env="production"
        )
        assert result is None

    def test_returns_failure_for_denied_capability(self):
        """Test that denied capability returns failure result."""
        result = check_capabilities(
            [Capability.SHELL_EXEC],
            "shell.exec",
            env="production"
        )

        assert result is not None
        assert result.ok is False
        assert result.error_code == ErrorCode.FORBIDDEN
        assert "shell.exec" in result.error
        assert "production" in result.error

    def test_returns_failure_details(self):
        """Test that failure includes denied capabilities in details."""
        result = check_capabilities(
            [Capability.SHELL_EXEC, Capability.NETWORK_LOCALHOST],
            "test.module",
            env="production"
        )

        assert result is not None
        assert result.ok is False
        # Check details
        details = result.meta.get("error_details", {})
        assert Capability.SHELL_EXEC in details.get("denied_capabilities", [])
        assert details.get("environment") == "production"


class TestExecuteModuleWithCapabilities:
    """Test execute_module with capability checking."""

    @pytest.mark.asyncio
    async def test_executes_with_allowed_capabilities(self):
        """Test that module executes when capabilities are allowed."""
        async def my_module(context):
            return {"result": "success"}

        result = await execute_module(
            module_fn=my_module,
            params={},
            context={},
            module_id="test.module",
            capabilities=[Capability.NETWORK_PUBLIC],
            env="production"
        )

        assert result.ok is True
        assert result.data == {"result": "success"}

    @pytest.mark.asyncio
    async def test_blocks_with_denied_capabilities(self):
        """Test that module is blocked when capabilities are denied."""
        async def my_module(context):
            return {"result": "should not reach here"}

        result = await execute_module(
            module_fn=my_module,
            params={},
            context={},
            module_id="shell.exec",
            capabilities=[Capability.SHELL_EXEC],
            env="production"
        )

        assert result.ok is False
        assert result.error_code == ErrorCode.FORBIDDEN
        assert "shell.exec" in result.error

    @pytest.mark.asyncio
    async def test_executes_without_capabilities_param(self):
        """Test that module executes when no capabilities specified."""
        async def my_module(context):
            return {"result": "success"}

        result = await execute_module(
            module_fn=my_module,
            params={},
            context={},
            module_id="test.module"
            # No capabilities param
        )

        assert result.ok is True

    @pytest.mark.asyncio
    async def test_respects_env_param(self):
        """Test that env param overrides FLYTO_ENV."""
        async def my_module(context):
            return {"result": "success"}

        # Should be allowed in development
        result = await execute_module(
            module_fn=my_module,
            params={},
            context={},
            module_id="shell.exec",
            capabilities=[Capability.SHELL_EXEC],
            env="development"
        )

        assert result.ok is True

    @pytest.mark.asyncio
    async def test_uses_flyto_env_by_default(self, monkeypatch):
        """Test that FLYTO_ENV is used when env not specified."""
        monkeypatch.setenv("FLYTO_ENV", "production")

        async def my_module(context):
            return {"result": "success"}

        result = await execute_module(
            module_fn=my_module,
            params={},
            context={},
            module_id="shell.exec",
            capabilities=[Capability.SHELL_EXEC]
            # No env param - should use FLYTO_ENV
        )

        assert result.ok is False
        assert result.error_code == ErrorCode.FORBIDDEN
