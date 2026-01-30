"""
Pool Router Tests

Tests for Multi-Tenant Support (Phase M).
Tasks: M.1 - M.5
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.runtime.pool_router import (
    PoolRouter,
    PoolConfig,
    PoolStats,
    PoolType,
    TenantTier,
    TIER_POOL_MAPPING,
    get_pool_router,
    reset_pool_router,
)
from src.core.runtime.types import TenantContext, InvokeRequest, InvokeResponse


class TestPoolRouterCreation:
    """Test M.1: Pool router creation."""

    @pytest.fixture
    def plugin_dir(self, tmp_path):
        """Create plugin directory with sample manifest."""
        plugin = tmp_path / "flyto-official_test"
        plugin.mkdir()

        manifest = {
            "id": "flyto-official_test",
            "name": "Test Plugin",
            "version": "1.0.0",
            "vendor": "flyto-official",
            "entryPoint": "main.py",
            "steps": [{"id": "echo", "label": "Echo"}],
        }

        import json
        (plugin / "plugin.manifest.json").write_text(json.dumps(manifest))

        return tmp_path

    @pytest.mark.asyncio
    async def test_router_initialization(self, plugin_dir):
        """Test router initializes with shared pool."""
        router = PoolRouter(plugin_dir)
        await router.initialize()

        try:
            assert router._shared_pool is not None
            assert "shared" in router._pool_stats
            assert "shared" in router._pool_semaphores
        finally:
            await router.shutdown()

    @pytest.mark.asyncio
    async def test_router_with_config(self, plugin_dir):
        """Test router respects configuration."""
        config = {
            "sharedPool": {
                "maxProcesses": 8,
                "maxConcurrentInvokes": 50,
            },
            "dedicatedPool": {
                "maxProcesses": 4,
                "maxConcurrentInvokes": 20,
            },
        }

        router = PoolRouter(plugin_dir, config)
        await router.initialize()

        try:
            shared_config = router._pool_configs["shared"]
            assert shared_config.max_processes == 8
            assert shared_config.max_concurrent_invokes == 50
        finally:
            await router.shutdown()


class TestSharedPoolForFreePro:
    """Test M.2: Shared pool for Free/Pro tiers."""

    @pytest.fixture
    def plugin_dir(self, tmp_path):
        """Create plugin directory."""
        plugin = tmp_path / "flyto-official_test"
        plugin.mkdir()

        import json
        manifest = {
            "id": "flyto-official_test",
            "name": "Test",
            "version": "1.0.0",
            "vendor": "test",
            "entryPoint": "main.py",
            "steps": [{"id": "step", "label": "Step"}],
        }
        (plugin / "plugin.manifest.json").write_text(json.dumps(manifest))

        return tmp_path

    def test_tier_mapping(self):
        """Test tier to pool type mapping."""
        assert TIER_POOL_MAPPING[TenantTier.FREE] == PoolType.SHARED
        assert TIER_POOL_MAPPING[TenantTier.PRO] == PoolType.SHARED
        assert TIER_POOL_MAPPING[TenantTier.TEAM] == PoolType.DEDICATED
        assert TIER_POOL_MAPPING[TenantTier.ENTERPRISE] == PoolType.DEDICATED

    @pytest.mark.asyncio
    async def test_free_tier_uses_shared_pool(self, plugin_dir):
        """Test Free tier uses shared pool."""
        router = PoolRouter(plugin_dir)
        await router.initialize()

        try:
            tenant = TenantContext(
                tenant_id="user_123",
                tenant_tier="free",
                isolation_mode="shared_pool",
            )

            pool = await router.get_pool_for_tenant(tenant)

            assert pool is router._shared_pool
            assert pool.pool_id == "shared"
        finally:
            await router.shutdown()

    @pytest.mark.asyncio
    async def test_pro_tier_uses_shared_pool(self, plugin_dir):
        """Test Pro tier uses shared pool."""
        router = PoolRouter(plugin_dir)
        await router.initialize()

        try:
            tenant = TenantContext(
                tenant_id="user_456",
                tenant_tier="pro",
                isolation_mode="shared_pool",
            )

            pool = await router.get_pool_for_tenant(tenant)

            assert pool is router._shared_pool
        finally:
            await router.shutdown()

    @pytest.mark.asyncio
    async def test_multiple_free_users_share_pool(self, plugin_dir):
        """Test multiple Free users share the same pool."""
        router = PoolRouter(plugin_dir)
        await router.initialize()

        try:
            tenant1 = TenantContext(tenant_id="user_1", tenant_tier="free")
            tenant2 = TenantContext(tenant_id="user_2", tenant_tier="free")
            tenant3 = TenantContext(tenant_id="user_3", tenant_tier="pro")

            pool1 = await router.get_pool_for_tenant(tenant1)
            pool2 = await router.get_pool_for_tenant(tenant2)
            pool3 = await router.get_pool_for_tenant(tenant3)

            # All should be the same shared pool
            assert pool1 is pool2 is pool3
            assert pool1.pool_id == "shared"
        finally:
            await router.shutdown()


class TestDedicatedPoolForTeamEnterprise:
    """Test M.3: Dedicated pools for Team/Enterprise."""

    @pytest.fixture
    def plugin_dir(self, tmp_path):
        """Create plugin directory."""
        plugin = tmp_path / "flyto-official_test"
        plugin.mkdir()

        import json
        manifest = {
            "id": "flyto-official_test",
            "name": "Test",
            "version": "1.0.0",
            "vendor": "test",
            "entryPoint": "main.py",
            "steps": [{"id": "step", "label": "Step"}],
        }
        (plugin / "plugin.manifest.json").write_text(json.dumps(manifest))

        return tmp_path

    @pytest.mark.asyncio
    async def test_team_tier_gets_dedicated_pool(self, plugin_dir):
        """Test Team tier gets a dedicated pool."""
        router = PoolRouter(plugin_dir)
        await router.initialize()

        try:
            tenant = TenantContext(
                tenant_id="team_abc",
                tenant_tier="team",
                isolation_mode="dedicated_pool",
            )

            pool = await router.get_pool_for_tenant(tenant)

            assert pool is not router._shared_pool
            assert pool.pool_id == "tenant_team_abc"
            assert "tenant_team_abc" in router._dedicated_pools
        finally:
            await router.shutdown()

    @pytest.mark.asyncio
    async def test_enterprise_tier_gets_dedicated_pool(self, plugin_dir):
        """Test Enterprise tier gets a dedicated pool."""
        router = PoolRouter(plugin_dir)
        await router.initialize()

        try:
            tenant = TenantContext(
                tenant_id="enterprise_xyz",
                tenant_tier="enterprise",
                isolation_mode="dedicated_pool",
            )

            pool = await router.get_pool_for_tenant(tenant)

            assert pool is not router._shared_pool
            assert pool.pool_id == "tenant_enterprise_xyz"
        finally:
            await router.shutdown()

    @pytest.mark.asyncio
    async def test_different_teams_get_different_pools(self, plugin_dir):
        """Test different Team tenants get isolated pools."""
        router = PoolRouter(plugin_dir)
        await router.initialize()

        try:
            tenant1 = TenantContext(tenant_id="team_1", tenant_tier="team")
            tenant2 = TenantContext(tenant_id="team_2", tenant_tier="team")

            pool1 = await router.get_pool_for_tenant(tenant1)
            pool2 = await router.get_pool_for_tenant(tenant2)

            assert pool1 is not pool2
            assert pool1.pool_id == "tenant_team_1"
            assert pool2.pool_id == "tenant_team_2"
        finally:
            await router.shutdown()

    @pytest.mark.asyncio
    async def test_dedicated_pool_respects_resource_limits(self, plugin_dir):
        """Test dedicated pool uses tenant resource limits."""
        router = PoolRouter(plugin_dir)
        await router.initialize()

        try:
            tenant = TenantContext(
                tenant_id="enterprise_big",
                tenant_tier="enterprise",
                resource_limits={
                    "maxProcesses": 10,
                    "maxConcurrentInvokes": 100,
                },
            )

            pool = await router.get_pool_for_tenant(tenant)

            config = router._pool_configs["tenant_enterprise_big"]
            assert config.max_processes == 10
            assert config.max_concurrent_invokes == 100
        finally:
            await router.shutdown()

    @pytest.mark.asyncio
    async def test_same_team_reuses_pool(self, plugin_dir):
        """Test same team tenant reuses existing pool."""
        router = PoolRouter(plugin_dir)
        await router.initialize()

        try:
            tenant = TenantContext(tenant_id="team_abc", tenant_tier="team")

            pool1 = await router.get_pool_for_tenant(tenant)
            pool2 = await router.get_pool_for_tenant(tenant)

            assert pool1 is pool2
        finally:
            await router.shutdown()


class TestTenantContextInInvokes:
    """Test M.4: Tenant context in all invokes."""

    @pytest.fixture
    def plugin_dir(self, tmp_path):
        """Create plugin directory."""
        plugin = tmp_path / "flyto-official_test"
        plugin.mkdir()

        import json
        manifest = {
            "id": "flyto-official_test",
            "name": "Test",
            "version": "1.0.0",
            "vendor": "test",
            "entryPoint": "main.py",
            "steps": [{"id": "step", "label": "Step"}],
        }
        (plugin / "plugin.manifest.json").write_text(json.dumps(manifest))
        (plugin / "main.py").write_text("# Entry point")

        return tmp_path

    @pytest.mark.asyncio
    async def test_invoke_includes_tenant_context(self, plugin_dir):
        """Test invoke adds tenant context."""
        router = PoolRouter(plugin_dir)
        await router.initialize()

        try:
            tenant = TenantContext(
                tenant_id="user_123",
                tenant_tier="pro",
                isolation_mode="shared_pool",
            )

            request = InvokeRequest(
                module_id="test.step",
                step_id="step",
                input_data={"value": "test"},
            )

            # Mock the pool's invoke method
            captured_context = {}

            async def capture_invoke(**kwargs):
                captured_context.update(kwargs.get("context", {}))
                return {"ok": True, "data": {}}

            router._shared_pool.invoke = AsyncMock(side_effect=capture_invoke)

            await router.invoke(request, tenant)

            # Verify tenant context was added
            assert "tenant" in captured_context
            assert captured_context["tenant"]["id"] == "user_123"
            assert captured_context["tenant"]["tier"] == "pro"
            assert captured_context["tenant"]["isolation"] == "shared_pool"

        finally:
            await router.shutdown()

    def test_parse_module_id_with_step(self):
        """Test module ID parsing with explicit step."""
        router = PoolRouter(Path("."))

        plugin_id, step_id = router._parse_module_id("database", "query")
        assert plugin_id == "database"
        assert step_id == "query"

    def test_parse_module_id_dot_notation(self):
        """Test module ID parsing with dot notation."""
        router = PoolRouter(Path("."))

        plugin_id, step_id = router._parse_module_id("database.query")
        assert plugin_id == "flyto-official_database"
        assert step_id == "query"

    def test_parse_module_id_vendor_notation(self):
        """Test module ID parsing with vendor notation."""
        router = PoolRouter(Path("."))

        plugin_id, step_id = router._parse_module_id("vendor/plugin.step")
        assert plugin_id == "vendor_plugin"
        assert step_id == "step"


class TestPoolStatistics:
    """Test pool statistics tracking."""

    @pytest.fixture
    def plugin_dir(self, tmp_path):
        """Create plugin directory."""
        plugin = tmp_path / "flyto-official_test"
        plugin.mkdir()

        import json
        manifest = {
            "id": "flyto-official_test",
            "name": "Test",
            "version": "1.0.0",
            "vendor": "test",
            "entryPoint": "main.py",
            "steps": [{"id": "step", "label": "Step"}],
        }
        (plugin / "plugin.manifest.json").write_text(json.dumps(manifest))

        return tmp_path

    @pytest.mark.asyncio
    async def test_get_pool_stats(self, plugin_dir):
        """Test getting pool statistics."""
        router = PoolRouter(plugin_dir)
        await router.initialize()

        try:
            stats = router.get_pool_stats("shared")

            assert stats["poolId"] == "shared"
            assert stats["activeInvokes"] == 0
            assert stats["totalInvokes"] == 0
        finally:
            await router.shutdown()

    @pytest.mark.asyncio
    async def test_list_pools(self, plugin_dir):
        """Test listing all pools."""
        router = PoolRouter(plugin_dir)
        await router.initialize()

        try:
            # Create a dedicated pool
            tenant = TenantContext(tenant_id="team_1", tenant_tier="team")
            await router.get_pool_for_tenant(tenant)

            pools = router.list_pools()

            assert len(pools) == 2

            pool_ids = [p["poolId"] for p in pools]
            assert "shared" in pool_ids
            assert "tenant_team_1" in pool_ids
        finally:
            await router.shutdown()


class TestPoolLifecycle:
    """Test pool lifecycle management."""

    @pytest.fixture
    def plugin_dir(self, tmp_path):
        """Create plugin directory."""
        plugin = tmp_path / "flyto-official_test"
        plugin.mkdir()

        import json
        manifest = {
            "id": "flyto-official_test",
            "name": "Test",
            "version": "1.0.0",
            "vendor": "test",
            "entryPoint": "main.py",
            "steps": [{"id": "step", "label": "Step"}],
        }
        (plugin / "plugin.manifest.json").write_text(json.dumps(manifest))

        return tmp_path

    @pytest.mark.asyncio
    async def test_shutdown_dedicated_pool(self, plugin_dir):
        """Test shutting down a dedicated pool."""
        router = PoolRouter(plugin_dir)
        await router.initialize()

        try:
            # Create dedicated pool
            tenant = TenantContext(tenant_id="team_1", tenant_tier="team")
            await router.get_pool_for_tenant(tenant)

            assert "tenant_team_1" in router._dedicated_pools

            # Shutdown the pool
            await router.shutdown_pool("tenant_team_1")

            assert "tenant_team_1" not in router._dedicated_pools
            assert "tenant_team_1" not in router._pool_configs
            assert "tenant_team_1" not in router._pool_stats
        finally:
            await router.shutdown()

    @pytest.mark.asyncio
    async def test_full_shutdown(self, plugin_dir):
        """Test full router shutdown."""
        router = PoolRouter(plugin_dir)
        await router.initialize()

        # Create some dedicated pools
        for i in range(3):
            tenant = TenantContext(tenant_id=f"team_{i}", tenant_tier="team")
            await router.get_pool_for_tenant(tenant)

        assert len(router._dedicated_pools) == 3
        assert router._shared_pool is not None

        # Full shutdown
        await router.shutdown()

        assert len(router._dedicated_pools) == 0
        assert router._shared_pool is None


class TestSingletonPoolRouter:
    """Test singleton pool router."""

    @pytest.fixture
    def plugin_dir(self, tmp_path):
        """Create plugin directory."""
        plugin = tmp_path / "flyto-official_test"
        plugin.mkdir()

        import json
        manifest = {
            "id": "flyto-official_test",
            "name": "Test",
            "version": "1.0.0",
            "vendor": "test",
            "entryPoint": "main.py",
            "steps": [{"id": "step", "label": "Step"}],
        }
        (plugin / "plugin.manifest.json").write_text(json.dumps(manifest))

        return tmp_path

    @pytest.mark.asyncio
    async def test_singleton_returns_same_instance(self, plugin_dir):
        """Test singleton returns same instance."""
        await reset_pool_router()

        try:
            router1 = await get_pool_router(plugin_dir)
            router2 = await get_pool_router(plugin_dir)

            assert router1 is router2
        finally:
            await reset_pool_router()

    @pytest.mark.asyncio
    async def test_reset_clears_singleton(self, plugin_dir):
        """Test reset clears the singleton."""
        await reset_pool_router()

        router1 = await get_pool_router(plugin_dir)
        await reset_pool_router()
        router2 = await get_pool_router(plugin_dir)

        assert router1 is not router2

        await reset_pool_router()
