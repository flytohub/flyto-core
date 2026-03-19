# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Proxy Pool — Rotation strategies for proxy lists

Supports round-robin, random, and failover rotation.
Automatically recovers when all proxies fail.
"""
import logging
import random as _random
import threading
from typing import List, Optional

logger = logging.getLogger(__name__)


class ProxyPool:
    """Manages a pool of proxy servers with rotation strategies.

    Thread-safe: uses threading.Lock (not asyncio.Lock) because all critical
    sections are microsecond CPU-only operations (list filter + index bump).
    This also allows ProxyPool to be safely shared between sync and async code.

    Strategies:
        round_robin: Cycle through proxies in order
        random: Pick a random proxy each time
        failover: Use the first available; move to next on failure
    """

    STRATEGIES = ('round_robin', 'random', 'failover')

    def __init__(self, proxies: List[str], strategy: str = 'round_robin'):
        if strategy not in self.STRATEGIES:
            raise ValueError(f"Unknown strategy: {strategy}. Use: {self.STRATEGIES}")
        if not proxies:
            raise ValueError("Proxy list cannot be empty")
        self._proxies = list(proxies)
        self._strategy = strategy
        self._index = 0
        self._failed: set = set()
        self._lock = threading.Lock()

    @property
    def strategy(self) -> str:
        return self._strategy

    @property
    def size(self) -> int:
        return len(self._proxies)

    @property
    def available(self) -> int:
        return len(self._proxies) - len(self._failed)

    def next(self) -> Optional[str]:
        """Get next proxy according to strategy."""
        with self._lock:
            alive = [p for p in self._proxies if p not in self._failed]
            if not alive:
                # Reset failed list and try again
                logger.warning("All proxies failed, resetting pool")
                self._failed.clear()
                alive = list(self._proxies)

            if not alive:
                return None

            if self._strategy == 'round_robin':
                proxy = alive[self._index % len(alive)]
                self._index += 1
                return proxy
            elif self._strategy == 'random':
                return _random.choice(alive)
            elif self._strategy == 'failover':
                return alive[0]  # Always use first available
            return alive[0]

    def mark_failed(self, proxy: str):
        """Mark a proxy as failed."""
        with self._lock:
            self._failed.add(proxy)
            remaining = self.size - len(self._failed)
            logger.info(f"Proxy marked failed: {proxy} ({remaining}/{self.size} remaining)")

    def mark_alive(self, proxy: str):
        """Mark a proxy as alive (recovered)."""
        with self._lock:
            self._failed.discard(proxy)

    def reset(self):
        """Reset all failure states."""
        with self._lock:
            self._failed.clear()
            self._index = 0
