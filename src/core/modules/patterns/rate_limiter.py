"""
Rate Limiter Patterns (Level 4)

Request rate limiting with various algorithms.
"""
import asyncio
import logging
import time
from collections import deque
from typing import Any, Callable, Dict, Optional

from .base import (
    BasePattern,
    PatternResult,
    PatternState,
    register_pattern,
)

logger = logging.getLogger(__name__)


@register_pattern(
    pattern_id='pattern.rate_limiter.token_bucket',
    version='1.0.0',
    category='rate_limiting',
    tags=['rate-limit', 'throttle', 'token-bucket', 'api'],

    label='Token Bucket Rate Limiter',
    label_key='patterns.rate_limiter.token_bucket.label',
    description='Rate limit requests using token bucket algorithm',
    description_key='patterns.rate_limiter.token_bucket.description',

    icon='Timer',
    color='#F59E0B',

    config_schema={
        'tokens_per_second': {
            'type': 'number',
            'label': 'Tokens per Second',
            'description': 'Rate at which tokens are added',
            'default': 10,
            'min': 0.1,
            'max': 1000
        },
        'bucket_size': {
            'type': 'number',
            'label': 'Bucket Size',
            'description': 'Maximum tokens in bucket (burst capacity)',
            'default': 10,
            'min': 1,
            'max': 1000
        },
        'wait_for_token': {
            'type': 'boolean',
            'label': 'Wait for Token',
            'description': 'Wait for token instead of rejecting',
            'default': True
        },
        'max_wait_ms': {
            'type': 'number',
            'label': 'Max Wait (ms)',
            'description': 'Maximum wait time for token (0 = unlimited)',
            'default': 5000
        }
    },

    examples=[
        {
            'name': 'API rate limiting',
            'description': 'Limit to 100 requests per second',
            'config': {
                'tokens_per_second': 100,
                'bucket_size': 100,
                'wait_for_token': True
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class TokenBucketRateLimiter(BasePattern):
    """
    Token Bucket Rate Limiter Pattern

    Algorithm:
    - Bucket starts full with `bucket_size` tokens
    - Tokens are added at `tokens_per_second` rate
    - Each request consumes one token
    - If no tokens available, wait or reject based on config
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        self.tokens_per_second = self.config.get('tokens_per_second', 10)
        self.bucket_size = self.config.get('bucket_size', 10)
        self.wait_for_token = self.config.get('wait_for_token', True)
        self.max_wait_ms = self.config.get('max_wait_ms', 5000)

        self._tokens = float(self.bucket_size)
        self._last_update = time.time()
        self._lock = asyncio.Lock()

    def _refill_tokens(self):
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self._last_update
        self._tokens = min(
            self.bucket_size,
            self._tokens + elapsed * self.tokens_per_second
        )
        self._last_update = now

    async def _acquire_token(self) -> bool:
        """Try to acquire a token"""
        async with self._lock:
            self._refill_tokens()

            if self._tokens >= 1:
                self._tokens -= 1
                return True

            if not self.wait_for_token:
                return False

            # Calculate wait time for next token
            tokens_needed = 1 - self._tokens
            wait_seconds = tokens_needed / self.tokens_per_second

            if self.max_wait_ms > 0:
                max_wait_seconds = self.max_wait_ms / 1000.0
                if wait_seconds > max_wait_seconds:
                    return False

        # Wait outside lock
        await asyncio.sleep(wait_seconds)

        # Acquire after wait
        async with self._lock:
            self._refill_tokens()
            if self._tokens >= 1:
                self._tokens -= 1
                return True
            return False

    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> PatternResult:
        """
        Execute function with rate limiting

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            PatternResult with execution result
        """
        start_time = time.time()
        self.state = PatternState.RUNNING

        # Try to acquire token
        acquired = await self._acquire_token()

        if not acquired:
            elapsed_ms = (time.time() - start_time) * 1000
            pattern_result = PatternResult(
                success=False,
                error='Rate limit exceeded',
                elapsed_ms=elapsed_ms,
                state=PatternState.FAILED,
                metadata={
                    'available_tokens': self._tokens,
                    'rate_limited': True
                }
            )
            self._update_metrics(pattern_result)
            return pattern_result

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            elapsed_ms = (time.time() - start_time) * 1000

            pattern_result = PatternResult(
                success=True,
                value=result,
                elapsed_ms=elapsed_ms,
                state=PatternState.SUCCESS,
                metadata={'available_tokens': self._tokens}
            )
            self._update_metrics(pattern_result)
            self.state = PatternState.SUCCESS
            return pattern_result

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000

            pattern_result = PatternResult(
                success=False,
                error=str(e),
                elapsed_ms=elapsed_ms,
                state=PatternState.FAILED
            )
            self._update_metrics(pattern_result)
            self.state = PatternState.FAILED
            return pattern_result


@register_pattern(
    pattern_id='pattern.rate_limiter.sliding_window',
    version='1.0.0',
    category='rate_limiting',
    tags=['rate-limit', 'throttle', 'sliding-window', 'api'],

    label='Sliding Window Rate Limiter',
    label_key='patterns.rate_limiter.sliding_window.label',
    description='Rate limit requests using sliding window algorithm',
    description_key='patterns.rate_limiter.sliding_window.description',

    icon='Clock',
    color='#3B82F6',

    config_schema={
        'max_requests': {
            'type': 'number',
            'label': 'Max Requests',
            'description': 'Maximum requests in window',
            'default': 100,
            'min': 1,
            'max': 10000
        },
        'window_ms': {
            'type': 'number',
            'label': 'Window Size (ms)',
            'description': 'Size of sliding window',
            'default': 60000,
            'min': 1000,
            'max': 3600000
        },
        'wait_for_slot': {
            'type': 'boolean',
            'label': 'Wait for Slot',
            'description': 'Wait for slot instead of rejecting',
            'default': False
        }
    },

    examples=[
        {
            'name': 'API rate limiting',
            'description': 'Limit to 100 requests per minute',
            'config': {
                'max_requests': 100,
                'window_ms': 60000
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class SlidingWindowRateLimiter(BasePattern):
    """
    Sliding Window Rate Limiter Pattern

    Algorithm:
    - Track timestamps of requests within sliding window
    - Reject if number of requests in window exceeds limit
    - Automatically cleans old entries
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        self.max_requests = self.config.get('max_requests', 100)
        self.window_ms = self.config.get('window_ms', 60000)
        self.wait_for_slot = self.config.get('wait_for_slot', False)

        self._requests: deque = deque()
        self._lock = asyncio.Lock()

    def _clean_old_requests(self):
        """Remove requests outside the window"""
        cutoff = time.time() - (self.window_ms / 1000.0)
        while self._requests and self._requests[0] < cutoff:
            self._requests.popleft()

    async def _can_proceed(self) -> bool:
        """Check if request can proceed"""
        async with self._lock:
            self._clean_old_requests()

            if len(self._requests) < self.max_requests:
                self._requests.append(time.time())
                return True

            if not self.wait_for_slot:
                return False

            # Calculate wait time
            oldest = self._requests[0]
            wait_until = oldest + (self.window_ms / 1000.0)
            wait_time = wait_until - time.time()

        if wait_time > 0:
            await asyncio.sleep(wait_time)

        async with self._lock:
            self._clean_old_requests()
            if len(self._requests) < self.max_requests:
                self._requests.append(time.time())
                return True

        return False

    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> PatternResult:
        """Execute function with sliding window rate limiting"""
        start_time = time.time()
        self.state = PatternState.RUNNING

        can_proceed = await self._can_proceed()

        if not can_proceed:
            elapsed_ms = (time.time() - start_time) * 1000
            pattern_result = PatternResult(
                success=False,
                error='Rate limit exceeded',
                elapsed_ms=elapsed_ms,
                state=PatternState.FAILED,
                metadata={
                    'requests_in_window': len(self._requests),
                    'max_requests': self.max_requests,
                    'rate_limited': True
                }
            )
            self._update_metrics(pattern_result)
            return pattern_result

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            elapsed_ms = (time.time() - start_time) * 1000

            pattern_result = PatternResult(
                success=True,
                value=result,
                elapsed_ms=elapsed_ms,
                state=PatternState.SUCCESS,
                metadata={'requests_in_window': len(self._requests)}
            )
            self._update_metrics(pattern_result)
            self.state = PatternState.SUCCESS
            return pattern_result

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000

            pattern_result = PatternResult(
                success=False,
                error=str(e),
                elapsed_ms=elapsed_ms,
                state=PatternState.FAILED
            )
            self._update_metrics(pattern_result)
            self.state = PatternState.FAILED
            return pattern_result
