"""
Pool Router for Multi-Tenant Isolation

Routes plugin invocations to appropriate process pools based on tenant tier.

Pool Strategy:
- Free/Pro: Shared pool (cost-efficient, fair queuing)
- Team/Enterprise: Dedicated pools (isolation, guaranteed resources)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .manager import PluginManager
from .types import TenantContext, InvokeRequest, InvokeResponse

logger = logging.getLogger(__name__)


class PoolType(Enum):
    """Type of process pool."""
    SHARED = "shared"
    DEDICATED = "dedicated"


class TenantTier(Enum):
    """Tenant subscription tier."""
    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"


@dataclass
class PoolConfig:
    """Configuration for a process pool."""
    pool_id: str
    pool_type: PoolType
    max_processes: int = 2
    max_concurrent_invokes: int = 10
    priority_weight: int = 1
    resource_limits: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PoolStats:
    """Statistics for a process pool."""
    pool_id: str
    active_invokes: int = 0
    total_invokes: int = 0
    total_errors: int = 0
    avg_latency_ms: float = 0.0
    plugins_loaded: int = 0


# Tier to pool mapping
TIER_POOL_MAPPING = {
    TenantTier.FREE: PoolType.SHARED,
    TenantTier.PRO: PoolType.SHARED,
    TenantTier.TEAM: PoolType.DEDICATED,
    TenantTier.ENTERPRISE: PoolType.DEDICATED,
}


class PoolRouter:
    """
    Routes invocations to appropriate process pools.

    Features:
    - Shared pool for Free/Pro tiers (fair queuing)
    - Dedicated pools for Team/Enterprise (isolation)
    - Pool health monitoring
    - Overflow handling
    """

    def __init__(
        self,
        plugin_dir: Path,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize pool router.

        Args:
            plugin_dir: Base directory containing plugins
            config: Router configuration
        """
        self.plugin_dir = Path(plugin_dir)
        self.config = config or {}

        # Shared pool (single instance for Free/Pro)
        self._shared_pool: Optional[PluginManager] = None

        # Dedicated pools (keyed by tenant_id)
        self._dedicated_pools: Dict[str, PluginManager] = {}

        # Pool configurations
        self._pool_configs: Dict[str, PoolConfig] = {}

        # Statistics
        self._pool_stats: Dict[str, PoolStats] = {}

        # Semaphores for concurrency control
        self._pool_semaphores: Dict[str, asyncio.Semaphore] = {}

        # Lock for pool creation
        self._pool_lock = asyncio.Lock()

        # Initialize shared pool config
        shared_config = self.config.get("sharedPool", {})
        self._pool_configs["shared"] = PoolConfig(
            pool_id="shared",
            pool_type=PoolType.SHARED,
            max_processes=shared_config.get("maxProcesses", 4),
            max_concurrent_invokes=shared_config.get("maxConcurrentInvokes", 20),
            priority_weight=1,
        )

        # Default dedicated pool config
        dedicated_config = self.config.get("dedicatedPool", {})
        self._default_dedicated_config = {
            "maxProcesses": dedicated_config.get("maxProcesses", 2),
            "maxConcurrentInvokes": dedicated_config.get("maxConcurrentInvokes", 10),
        }

    async def initialize(self):
        """Initialize the router and shared pool."""
        # Create shared pool
        shared_config = self._pool_configs["shared"]
        self._shared_pool = PluginManager(
            plugin_dir=self.plugin_dir,
            config={
                "maxProcesses": shared_config.max_processes,
            },
            pool_id="shared",
        )

        # Discover plugins in shared pool
        await self._shared_pool.discover_plugins()

        # Create semaphore for shared pool
        self._pool_semaphores["shared"] = asyncio.Semaphore(
            shared_config.max_concurrent_invokes
        )

        # Initialize stats
        self._pool_stats["shared"] = PoolStats(pool_id="shared")

        logger.info("Pool router initialized with shared pool")

    async def get_pool_for_tenant(
        self,
        tenant: TenantContext,
    ) -> PluginManager:
        """
        Get the appropriate pool for a tenant.

        Args:
            tenant: Tenant context

        Returns:
            PluginManager for the appropriate pool
        """
        tier = TenantTier(tenant.tenant_tier)
        pool_type = TIER_POOL_MAPPING.get(tier, PoolType.SHARED)

        if pool_type == PoolType.SHARED:
            return self._shared_pool

        # Dedicated pool - get or create
        return await self._get_or_create_dedicated_pool(tenant)

    async def _get_or_create_dedicated_pool(
        self,
        tenant: TenantContext,
    ) -> PluginManager:
        """Get or create a dedicated pool for a tenant."""
        pool_id = f"tenant_{tenant.tenant_id}"

        if pool_id in self._dedicated_pools:
            return self._dedicated_pools[pool_id]

        async with self._pool_lock:
            # Double-check after acquiring lock
            if pool_id in self._dedicated_pools:
                return self._dedicated_pools[pool_id]

            # Get tenant-specific limits or use defaults
            limits = tenant.resource_limits or {}
            max_processes = limits.get(
                "maxProcesses",
                self._default_dedicated_config["maxProcesses"]
            )
            max_concurrent = limits.get(
                "maxConcurrentInvokes",
                self._default_dedicated_config["maxConcurrentInvokes"]
            )

            # Create pool config
            self._pool_configs[pool_id] = PoolConfig(
                pool_id=pool_id,
                pool_type=PoolType.DEDICATED,
                max_processes=max_processes,
                max_concurrent_invokes=max_concurrent,
            )

            # Create plugin manager
            manager = PluginManager(
                plugin_dir=self.plugin_dir,
                config={"maxProcesses": max_processes},
                pool_id=pool_id,
            )

            # Discover plugins
            await manager.discover_plugins()

            # Create semaphore
            self._pool_semaphores[pool_id] = asyncio.Semaphore(max_concurrent)

            # Initialize stats
            self._pool_stats[pool_id] = PoolStats(pool_id=pool_id)

            self._dedicated_pools[pool_id] = manager

            logger.info(
                f"Created dedicated pool for tenant {tenant.tenant_id} "
                f"(tier: {tenant.tenant_tier})"
            )

            return manager

    async def invoke(
        self,
        request: InvokeRequest,
        tenant: TenantContext,
    ) -> InvokeResponse:
        """
        Route and invoke a request.

        Args:
            request: Invoke request
            tenant: Tenant context

        Returns:
            InvokeResponse
        """
        # Get appropriate pool
        pool = await self.get_pool_for_tenant(tenant)
        pool_id = pool.pool_id

        # Get semaphore for concurrency control
        semaphore = self._pool_semaphores.get(pool_id)
        if not semaphore:
            semaphore = asyncio.Semaphore(10)
            self._pool_semaphores[pool_id] = semaphore

        # Update stats
        stats = self._pool_stats.get(pool_id)
        if stats:
            stats.active_invokes += 1
            stats.total_invokes += 1

        try:
            async with semaphore:
                # Parse module_id to get plugin_id and step_id
                plugin_id, step_id = self._parse_module_id(
                    request.module_id,
                    request.step_id
                )

                # Add tenant context to the request context
                context = dict(request.context)
                context["tenant"] = {
                    "id": tenant.tenant_id,
                    "tier": tenant.tenant_tier,
                    "isolation": tenant.isolation_mode,
                }

                # Invoke
                result = await pool.invoke(
                    plugin_id=plugin_id,
                    step=step_id,
                    input_data=request.input_data,
                    config=request.config,
                    context=context,
                    timeout_ms=request.timeout_ms if request.timeout_ms > 0 else None,
                )

                return InvokeResponse.from_dict(result)

        except Exception as e:
            # Update error stats
            if stats:
                stats.total_errors += 1

            from .types import InvokeError
            return InvokeResponse(
                ok=False,
                error=InvokeError(
                    code="INVOKE_ERROR",
                    message=str(e),
                ),
            )

        finally:
            if stats:
                stats.active_invokes -= 1

    def _parse_module_id(
        self,
        module_id: str,
        step_id: Optional[str] = None,
    ) -> tuple:
        """Parse module_id into plugin_id and step_id."""
        if step_id:
            return module_id, step_id

        # Format: "plugin_id.step_id" or "vendor/plugin.step"
        if "/" in module_id:
            # vendor/plugin.step format
            vendor_plugin, step = module_id.rsplit(".", 1)
            return vendor_plugin.replace("/", "_"), step
        elif "." in module_id:
            # category.action format (legacy) -> plugin_id, step_id
            parts = module_id.split(".")
            if len(parts) == 2:
                return f"flyto-official_{parts[0]}", parts[1]
            else:
                # Multiple dots: first part is plugin, rest is step path
                return parts[0], ".".join(parts[1:])
        else:
            return module_id, "default"

    def get_pool_stats(self, pool_id: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics for pools."""
        if pool_id:
            stats = self._pool_stats.get(pool_id)
            if not stats:
                return {}
            return {
                "poolId": stats.pool_id,
                "activeInvokes": stats.active_invokes,
                "totalInvokes": stats.total_invokes,
                "totalErrors": stats.total_errors,
                "avgLatencyMs": stats.avg_latency_ms,
            }

        # Return all stats
        return {
            pool_id: {
                "poolId": stats.pool_id,
                "activeInvokes": stats.active_invokes,
                "totalInvokes": stats.total_invokes,
                "totalErrors": stats.total_errors,
                "avgLatencyMs": stats.avg_latency_ms,
            }
            for pool_id, stats in self._pool_stats.items()
        }

    def list_pools(self) -> List[Dict[str, Any]]:
        """List all active pools."""
        pools = []

        # Shared pool
        if self._shared_pool:
            config = self._pool_configs.get("shared")
            pools.append({
                "poolId": "shared",
                "type": "shared",
                "maxProcesses": config.max_processes if config else 4,
                "pluginsLoaded": len(self._shared_pool.list_plugins()),
            })

        # Dedicated pools
        for pool_id, manager in self._dedicated_pools.items():
            config = self._pool_configs.get(pool_id)
            tenant_id = pool_id.replace("tenant_", "")
            pools.append({
                "poolId": pool_id,
                "type": "dedicated",
                "tenantId": tenant_id,
                "maxProcesses": config.max_processes if config else 2,
                "pluginsLoaded": len(manager.list_plugins()),
            })

        return pools

    async def shutdown_pool(self, pool_id: str):
        """Shutdown a specific pool."""
        if pool_id == "shared":
            if self._shared_pool:
                await self._shared_pool.shutdown()
                self._shared_pool = None
        elif pool_id in self._dedicated_pools:
            pool = self._dedicated_pools.pop(pool_id)
            await pool.shutdown()
            self._pool_configs.pop(pool_id, None)
            self._pool_stats.pop(pool_id, None)
            self._pool_semaphores.pop(pool_id, None)
            logger.info(f"Shutdown dedicated pool: {pool_id}")

    async def shutdown(self):
        """Shutdown all pools."""
        # Shutdown dedicated pools
        for pool_id in list(self._dedicated_pools.keys()):
            await self.shutdown_pool(pool_id)

        # Shutdown shared pool
        if self._shared_pool:
            await self._shared_pool.shutdown()
            self._shared_pool = None

        logger.info("Pool router shutdown complete")


# Singleton instance
_pool_router: Optional[PoolRouter] = None
_router_lock = asyncio.Lock()


async def get_pool_router(
    plugin_dir: Optional[Path] = None,
    config: Optional[Dict[str, Any]] = None,
) -> PoolRouter:
    """Get or create the pool router singleton."""
    global _pool_router

    if _pool_router is not None:
        return _pool_router

    async with _router_lock:
        if _pool_router is not None:
            return _pool_router

        if plugin_dir is None:
            plugin_dir = Path("plugins")

        _pool_router = PoolRouter(plugin_dir, config)
        await _pool_router.initialize()

        return _pool_router


async def reset_pool_router():
    """Reset the pool router (for testing)."""
    global _pool_router

    if _pool_router:
        await _pool_router.shutdown()
        _pool_router = None
