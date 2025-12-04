"""
Connection Pool Manager
Optimizes concurrent HTTP connection management
"""
import asyncio
from typing import Dict, Optional, Any
from dataclasses import dataclass
import aiohttp


@dataclass
class PoolConfig:
    """Configuration for connection pool"""
    max_connections: int = 100
    max_per_host: int = 10
    timeout: float = 30.0
    keepalive_timeout: float = 30.0


class ConnectionPool:
    """
    Manages HTTP connection pool for efficient concurrent requests
    """

    def __init__(self, config: Optional[PoolConfig] = None):
        """
        Initialize connection pool

        Args:
            config: Pool configuration
        """
        self.config = config or PoolConfig()
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None

    async def __aenter__(self):
        """Context manager entry"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        await self.close()

    async def initialize(self):
        """Initialize connection pool"""
        if self._session is None:
            self._connector = aiohttp.TCPConnector(
                limit=self.config.max_connections,
                limit_per_host=self.config.max_per_host,
                ttl_dns_cache=300,
                keepalive_timeout=self.config.keepalive_timeout
            )

            timeout = aiohttp.ClientTimeout(total=self.config.timeout)

            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout
            )

    async def close(self):
        """Close connection pool"""
        if self._session:
            await self._session.close()
            self._session = None
            self._connector = None

    async def get(self, url: str, **kwargs) -> Dict[str, Any]:
        """
        Execute GET request using pool

        Args:
            url: Request URL
            **kwargs: Additional request parameters

        Returns:
            Response data
        """
        if not self._session:
            await self.initialize()

        async with self._session.get(url, **kwargs) as response:
            return {
                'status': response.status,
                'headers': dict(response.headers),
                'body': await response.text(),
                'url': str(response.url)
            }

    async def post(self, url: str, **kwargs) -> Dict[str, Any]:
        """
        Execute POST request using pool

        Args:
            url: Request URL
            **kwargs: Additional request parameters

        Returns:
            Response data
        """
        if not self._session:
            await self.initialize()

        async with self._session.post(url, **kwargs) as response:
            return {
                'status': response.status,
                'headers': dict(response.headers),
                'body': await response.text(),
                'url': str(response.url)
            }

    def get_stats(self) -> Dict[str, Any]:
        """
        Get connection pool statistics

        Returns:
            Pool statistics
        """
        if not self._connector:
            return {'status': 'not_initialized'}

        return {
            'status': 'active',
            'max_connections': self.config.max_connections,
            'max_per_host': self.config.max_per_host,
            'timeout': self.config.timeout,
            'keepalive_timeout': self.config.keepalive_timeout
        }


# Global connection pool instance
_global_pool: Optional[ConnectionPool] = None


async def get_connection_pool(config: Optional[PoolConfig] = None) -> ConnectionPool:
    """
    Get or create global connection pool

    Args:
        config: Optional pool configuration

    Returns:
        ConnectionPool instance
    """
    global _global_pool

    if _global_pool is None:
        _global_pool = ConnectionPool(config)
        await _global_pool.initialize()

    return _global_pool


async def close_global_pool():
    """Close global connection pool"""
    global _global_pool

    if _global_pool:
        await _global_pool.close()
        _global_pool = None
