"""
Plugin Health Check System

Monitors plugin health and manages restart policy.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status of a plugin."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckConfig:
    """Configuration for health checking."""
    enabled: bool = True
    interval_seconds: int = 30
    timeout_seconds: int = 5
    method: str = "ping"  # ping, http, custom

    # Thresholds
    consecutive_failures_for_unhealthy: int = 3
    consecutive_successes_for_healthy: int = 2


@dataclass
class HealthRecord:
    """Record of a health check."""
    timestamp: float
    status: HealthStatus
    latency_ms: int
    error: Optional[str] = None


@dataclass
class PluginHealth:
    """Health state of a plugin."""
    plugin_id: str
    status: HealthStatus = HealthStatus.UNKNOWN
    last_check: Optional[float] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    history: List[HealthRecord] = field(default_factory=list)
    unhealthy_since: Optional[float] = None


class HealthChecker:
    """
    Monitors health of plugins.

    Features:
    - Periodic health checks
    - Consecutive failure tracking
    - Health history
    - Callbacks for status changes
    """

    def __init__(
        self,
        config: Optional[HealthCheckConfig] = None,
        max_history: int = 100,
    ):
        self.config = config or HealthCheckConfig()
        self.max_history = max_history

        self._health: Dict[str, PluginHealth] = {}
        self._check_callbacks: Dict[str, Callable] = {}
        self._status_change_callbacks: List[Callable] = []

        self._running = False
        self._check_task: Optional[asyncio.Task] = None

    def register_plugin(
        self,
        plugin_id: str,
        check_callback: Callable,
    ):
        """
        Register a plugin for health monitoring.

        Args:
            plugin_id: Plugin ID
            check_callback: Async function that returns (success, latency_ms, error)
        """
        self._health[plugin_id] = PluginHealth(plugin_id=plugin_id)
        self._check_callbacks[plugin_id] = check_callback
        logger.debug(f"Registered health check for: {plugin_id}")

    def unregister_plugin(self, plugin_id: str):
        """Unregister a plugin from health monitoring."""
        self._health.pop(plugin_id, None)
        self._check_callbacks.pop(plugin_id, None)
        logger.debug(f"Unregistered health check for: {plugin_id}")

    def on_status_change(self, callback: Callable):
        """
        Register callback for health status changes.

        Callback signature: (plugin_id, old_status, new_status)
        """
        self._status_change_callbacks.append(callback)

    async def check_plugin(self, plugin_id: str) -> HealthRecord:
        """
        Perform health check on a specific plugin.

        Returns:
            HealthRecord with check results
        """
        health = self._health.get(plugin_id)
        callback = self._check_callbacks.get(plugin_id)

        if not health or not callback:
            return HealthRecord(
                timestamp=time.time(),
                status=HealthStatus.UNKNOWN,
                latency_ms=0,
                error="Plugin not registered",
            )

        start_time = time.time()
        try:
            # Call health check with timeout
            success, latency_ms, error = await asyncio.wait_for(
                callback(),
                timeout=self.config.timeout_seconds,
            )

            status = HealthStatus.HEALTHY if success else HealthStatus.DEGRADED

        except asyncio.TimeoutError:
            latency_ms = int((time.time() - start_time) * 1000)
            status = HealthStatus.UNHEALTHY
            error = f"Health check timeout ({self.config.timeout_seconds}s)"

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            status = HealthStatus.UNHEALTHY
            error = str(e)

        # Create record
        record = HealthRecord(
            timestamp=time.time(),
            status=status,
            latency_ms=latency_ms,
            error=error,
        )

        # Update health state
        self._update_health(plugin_id, record)

        return record

    def _update_health(self, plugin_id: str, record: HealthRecord):
        """Update health state based on check result."""
        health = self._health.get(plugin_id)
        if not health:
            return

        old_status = health.status

        # Add to history
        health.history.append(record)
        if len(health.history) > self.max_history:
            health.history = health.history[-self.max_history:]

        health.last_check = record.timestamp

        # Update consecutive counts
        if record.status == HealthStatus.HEALTHY:
            health.consecutive_successes += 1
            health.consecutive_failures = 0
        else:
            health.consecutive_failures += 1
            health.consecutive_successes = 0

        # Determine new status
        if health.consecutive_failures >= self.config.consecutive_failures_for_unhealthy:
            health.status = HealthStatus.UNHEALTHY
            if health.unhealthy_since is None:
                health.unhealthy_since = record.timestamp
        elif health.consecutive_successes >= self.config.consecutive_successes_for_healthy:
            health.status = HealthStatus.HEALTHY
            health.unhealthy_since = None
        elif health.consecutive_failures > 0:
            health.status = HealthStatus.DEGRADED

        # Notify status change
        if health.status != old_status:
            self._notify_status_change(plugin_id, old_status, health.status)

    def _notify_status_change(
        self,
        plugin_id: str,
        old_status: HealthStatus,
        new_status: HealthStatus,
    ):
        """Notify callbacks of status change."""
        logger.info(f"Plugin {plugin_id} health: {old_status.value} -> {new_status.value}")
        for callback in self._status_change_callbacks:
            try:
                callback(plugin_id, old_status, new_status)
            except Exception as e:
                logger.error(f"Status change callback error: {e}")

    async def check_all(self) -> Dict[str, HealthRecord]:
        """
        Check health of all registered plugins.

        Returns:
            Dict of plugin_id -> HealthRecord
        """
        results = {}
        for plugin_id in list(self._health.keys()):
            results[plugin_id] = await self.check_plugin(plugin_id)
        return results

    async def start(self):
        """Start periodic health checking."""
        if not self.config.enabled:
            logger.info("Health checking disabled")
            return

        if self._running:
            return

        self._running = True

        async def check_loop():
            while self._running:
                try:
                    await self.check_all()
                except Exception as e:
                    logger.error(f"Health check loop error: {e}")
                await asyncio.sleep(self.config.interval_seconds)

        self._check_task = asyncio.create_task(check_loop())
        logger.info(f"Health checking started (interval: {self.config.interval_seconds}s)")

    async def stop(self):
        """Stop health checking."""
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
            self._check_task = None
        logger.info("Health checking stopped")

    def get_health(self, plugin_id: str) -> Optional[PluginHealth]:
        """Get health state of a plugin."""
        return self._health.get(plugin_id)

    def get_status(self, plugin_id: str) -> HealthStatus:
        """Get current health status of a plugin."""
        health = self._health.get(plugin_id)
        return health.status if health else HealthStatus.UNKNOWN

    def get_all_health(self) -> Dict[str, PluginHealth]:
        """Get health state of all plugins."""
        return dict(self._health)

    def get_summary(self) -> Dict[str, Any]:
        """Get health summary."""
        healthy = sum(1 for h in self._health.values() if h.status == HealthStatus.HEALTHY)
        degraded = sum(1 for h in self._health.values() if h.status == HealthStatus.DEGRADED)
        unhealthy = sum(1 for h in self._health.values() if h.status == HealthStatus.UNHEALTHY)
        unknown = sum(1 for h in self._health.values() if h.status == HealthStatus.UNKNOWN)

        return {
            "total": len(self._health),
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "unknown": unknown,
            "plugins": {
                pid: h.status.value
                for pid, h in self._health.items()
            },
        }
