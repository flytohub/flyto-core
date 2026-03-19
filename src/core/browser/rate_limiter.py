# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Adaptive Rate Limiter — Smart delay between requests

Strategies:
    fixed: Constant delay between requests
    adaptive: Exponential backoff on errors (429, captcha), gradual recovery on success
    human_like: Gaussian-distributed delays with occasional longer pauses
"""
import asyncio
import logging
import random
import time

logger = logging.getLogger(__name__)


class RateLimiter:
    """Adaptive rate limiter for browser automation."""

    STRATEGIES = ('fixed', 'adaptive', 'human_like')

    def __init__(
        self,
        strategy: str = 'fixed',
        min_delay_ms: int = 500,
        max_delay_ms: int = 5000,
        base_delay_ms: int = 1000,
    ):
        if strategy not in self.STRATEGIES:
            raise ValueError(f"Unknown strategy: {strategy}. Use: {self.STRATEGIES}")
        self.strategy = strategy
        self.min_delay_ms = min_delay_ms
        self.max_delay_ms = max_delay_ms
        self.base_delay_ms = base_delay_ms
        self._current_delay_ms = base_delay_ms
        self._consecutive_errors = 0
        self._last_request_time = 0.0

    async def wait(self):
        """Wait according to the current strategy and elapsed time."""
        delay_ms = self._compute_delay()

        # Account for time already elapsed since last request
        elapsed_ms = (time.monotonic() - self._last_request_time) * 1000
        remaining_ms = max(0, delay_ms - elapsed_ms)

        if remaining_ms > 0:
            await asyncio.sleep(remaining_ms / 1000)

        self._last_request_time = time.monotonic()

    def _compute_delay(self) -> float:
        if self.strategy == 'fixed':
            return self.base_delay_ms

        elif self.strategy == 'adaptive':
            return self._clamp(self._current_delay_ms)

        elif self.strategy == 'human_like':
            base = self._current_delay_ms
            # Gaussian jitter: mean=base, std=30% of base
            jitter = random.gauss(0, base * 0.3)
            delay = base + jitter
            # 10% chance of a longer "reading" pause
            if random.random() < 0.1:
                delay += random.uniform(2000, 5000)
            return self._clamp(delay)

        return self.base_delay_ms

    def _clamp(self, value: float) -> float:
        return max(self.min_delay_ms, min(value, self.max_delay_ms))

    def on_success(self):
        """Report successful request — gradually decreases delay for adaptive."""
        self._consecutive_errors = 0
        if self.strategy in ('adaptive', 'human_like'):
            # 10% decrease per success, min at base_delay_ms
            self._current_delay_ms = max(
                self.min_delay_ms,
                int(self._current_delay_ms * 0.9),
            )

    def on_error(self, is_rate_limit: bool = False):
        """Report error — increases delay for adaptive strategies."""
        self._consecutive_errors += 1
        if self.strategy in ('adaptive', 'human_like'):
            if is_rate_limit:
                # Aggressive 3x backoff on rate limiting (429)
                self._current_delay_ms = min(
                    self.max_delay_ms,
                    self._current_delay_ms * 3,
                )
            else:
                # Moderate 1.5x backoff on other errors
                self._current_delay_ms = min(
                    self.max_delay_ms,
                    int(self._current_delay_ms * 1.5),
                )
            logger.info(
                f"Rate limiter backoff: {self._current_delay_ms}ms "
                f"(errors: {self._consecutive_errors})"
            )

    @property
    def current_delay_ms(self) -> int:
        return self._current_delay_ms

    @property
    def consecutive_errors(self) -> int:
        return self._consecutive_errors
