"""
Rate Limiter

Token bucket rate limiter for API calls.
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter.

    Usage:
        limiter = RateLimiter(calls=100, period=60)
        await limiter.acquire()  # Blocks if rate limited
    """

    def __init__(self, calls: int = 100, period: int = 60):
        """
        Initialize rate limiter.

        Args:
            calls: Maximum calls allowed in period
            period: Period in seconds
        """
        self.calls = calls
        self.period = period
        self.tokens = calls
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a token, blocking if rate limited."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update

            # Refill tokens
            refill = (elapsed / self.period) * self.calls
            self.tokens = min(self.calls, self.tokens + refill)
            self.last_update = now

            if self.tokens < 1:
                # Calculate wait time
                wait = (1 - self.tokens) * (self.period / self.calls)
                logger.debug(f"Rate limited, waiting {wait:.2f}s")
                await asyncio.sleep(wait)
                self.tokens = 0
            else:
                self.tokens -= 1

    def reset(self) -> None:
        """Reset rate limiter."""
        self.tokens = self.calls
        self.last_update = time.monotonic()
