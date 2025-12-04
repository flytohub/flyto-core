"""
Rate Limit Handler
Automatic retry logic for rate-limited API requests (429 responses)
"""
import asyncio
import time
from typing import Optional, Callable, Any
from dataclasses import dataclass


@dataclass
class RateLimitConfig:
    """Configuration for rate limit handling"""
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True


class RateLimitHandler:
    """
    Handler for automatic retry on rate limit responses
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        """
        Initialize rate limit handler

        Args:
            config: Rate limit configuration, uses defaults if None
        """
        self.config = config or RateLimitConfig()
        self.retry_count = 0
        self.total_delays = 0.0

    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with automatic retry on rate limit

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Function result

        Raises:
            Exception: If max retries exceeded or non-rate-limit error
        """
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                result = await func(*args, **kwargs)

                # Check if result indicates rate limit
                if self._is_rate_limited(result):
                    if attempt < self.config.max_retries:
                        delay = self._calculate_delay(attempt, result)
                        await self._wait_with_logging(delay, attempt)
                        continue
                    else:
                        raise RateLimitExceeded(
                            f"Max retries ({self.config.max_retries}) exceeded for rate limit"
                        )

                # Success - return result
                self.retry_count = attempt
                return result

            except RateLimitExceeded:
                # Re-raise rate limit exceeded errors
                raise
            except Exception as e:
                # Check if exception is rate limit error
                if self._is_rate_limit_exception(e):
                    last_exception = e
                    if attempt < self.config.max_retries:
                        delay = self._calculate_delay(attempt, e)
                        await self._wait_with_logging(delay, attempt)
                        continue
                    else:
                        raise RateLimitExceeded(
                            f"Max retries ({self.config.max_retries}) exceeded"
                        ) from e
                else:
                    # Non-rate-limit error - raise immediately without retry
                    raise

        # Should not reach here, but if we do, raise last exception
        raise last_exception or Exception("Unknown error in rate limit handler")

    def _is_rate_limited(self, result: Any) -> bool:
        """Check if result indicates rate limiting"""
        # Check for HTTP response with status 429
        if hasattr(result, 'status_code'):
            return result.status_code == 429

        if hasattr(result, 'status'):
            return result.status == 429

        # Check dict response
        if isinstance(result, dict):
            status = result.get('status_code') or result.get('status')
            if status == 429:
                return True

            # Check for rate limit message
            error_msg = str(result.get('error', '')).lower()
            return 'rate limit' in error_msg or 'too many requests' in error_msg

        return False

    def _is_rate_limit_exception(self, exception: Exception) -> bool:
        """Check if exception is due to rate limiting"""
        error_msg = str(exception).lower()

        # Exclude negative mentions
        negative_patterns = ['not a rate limit', 'not rate limit', 'no rate limit']
        if any(pattern in error_msg for pattern in negative_patterns):
            return False

        # Check for common rate limit indicators
        rate_limit_indicators = [
            '429',
            'rate limit exceeded',
            'rate limited',
            'too many requests',
            'quota exceeded',
            'throttled',
            'retry after'
        ]

        return any(indicator in error_msg for indicator in rate_limit_indicators)

    def _calculate_delay(self, attempt: int, response_or_error: Any) -> float:
        """
        Calculate delay before next retry using exponential backoff

        Args:
            attempt: Current attempt number (0-indexed)
            response_or_error: Response or error object (may contain Retry-After header)

        Returns:
            Delay in seconds
        """
        # Check for Retry-After header
        retry_after = self._extract_retry_after(response_or_error)
        if retry_after is not None:
            return min(retry_after, self.config.max_delay)

        # Exponential backoff
        delay = self.config.base_delay * (self.config.exponential_base ** attempt)

        # Add jitter to avoid thundering herd
        if self.config.jitter:
            import random
            delay = delay * (0.5 + random.random())  # 50-150% of calculated delay

        # Cap at max_delay
        delay = min(delay, self.config.max_delay)

        return delay

    def _extract_retry_after(self, response_or_error: Any) -> Optional[float]:
        """Extract Retry-After value from response or error"""
        # Try to get from response headers
        if hasattr(response_or_error, 'headers'):
            retry_after = response_or_error.headers.get('Retry-After')
            if retry_after:
                try:
                    return float(retry_after)
                except (ValueError, TypeError):
                    pass

        # Try to get from dict response
        if isinstance(response_or_error, dict):
            retry_after = response_or_error.get('retry_after')
            if retry_after:
                try:
                    return float(retry_after)
                except (ValueError, TypeError):
                    pass

        return None

    async def _wait_with_logging(self, delay: float, attempt: int):
        """Wait for delay and track metrics"""
        self.total_delays += delay
        await asyncio.sleep(delay)

    def get_stats(self) -> dict:
        """Get retry statistics"""
        return {
            'retry_count': self.retry_count,
            'total_delays': self.total_delays,
            'config': {
                'max_retries': self.config.max_retries,
                'base_delay': self.config.base_delay,
                'max_delay': self.config.max_delay
            }
        }


class RateLimitExceeded(Exception):
    """Exception raised when rate limit retries are exhausted"""
    pass
