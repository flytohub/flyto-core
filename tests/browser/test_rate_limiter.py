"""Tests for RateLimiter strategies."""
import asyncio
import pytest
from core.browser.rate_limiter import RateLimiter


class TestRateLimiter:
    def test_fixed_strategy(self):
        rl = RateLimiter(strategy='fixed', base_delay_ms=1000)
        assert rl.current_delay_ms == 1000
        rl.on_success()
        assert rl.current_delay_ms == 1000  # fixed doesn't change
        rl.on_error()
        assert rl.current_delay_ms == 1000  # fixed doesn't change

    def test_adaptive_backoff_on_rate_limit(self):
        rl = RateLimiter(strategy='adaptive', base_delay_ms=1000, max_delay_ms=10000)
        rl.on_error(is_rate_limit=True)
        assert rl.current_delay_ms == 3000  # 3x on rate limit

    def test_adaptive_backoff_on_error(self):
        rl = RateLimiter(strategy='adaptive', base_delay_ms=1000, max_delay_ms=10000)
        rl.on_error(is_rate_limit=False)
        assert rl.current_delay_ms == 1500  # 1.5x on regular error

    def test_adaptive_recovery_on_success(self):
        rl = RateLimiter(strategy='adaptive', base_delay_ms=1000, min_delay_ms=500)
        rl.on_error(is_rate_limit=True)  # 3000ms
        rl.on_success()  # 2700ms (10% decrease)
        assert rl.current_delay_ms == 2700

    def test_adaptive_max_cap(self):
        rl = RateLimiter(strategy='adaptive', base_delay_ms=5000, max_delay_ms=10000)
        rl.on_error(is_rate_limit=True)  # would be 15000 but capped
        assert rl.current_delay_ms == 10000

    def test_adaptive_min_cap(self):
        rl = RateLimiter(strategy='adaptive', base_delay_ms=600, min_delay_ms=500)
        for _ in range(20):
            rl.on_success()
        assert rl.current_delay_ms >= 500

    def test_human_like_varies(self):
        rl = RateLimiter(strategy='human_like', base_delay_ms=1000, min_delay_ms=200, max_delay_ms=20000)
        delays = set()
        for _ in range(20):
            delays.add(rl._compute_delay())
        # Human-like should produce varied delays
        assert len(delays) > 1

    def test_consecutive_errors_tracked(self):
        rl = RateLimiter(strategy='adaptive', base_delay_ms=1000)
        assert rl.consecutive_errors == 0
        rl.on_error()
        assert rl.consecutive_errors == 1
        rl.on_error()
        assert rl.consecutive_errors == 2
        rl.on_success()
        assert rl.consecutive_errors == 0

    def test_invalid_strategy(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            RateLimiter(strategy='turbo')

    @pytest.mark.asyncio
    async def test_wait_respects_elapsed_time(self):
        rl = RateLimiter(strategy='fixed', base_delay_ms=100)
        # First wait is instant (no prior request tracked)
        await rl.wait()

        # Second wait right after should enforce the delay
        import time
        start = time.monotonic()
        await rl.wait()
        elapsed = (time.monotonic() - start) * 1000
        assert elapsed >= 50  # 100ms base, some tolerance
