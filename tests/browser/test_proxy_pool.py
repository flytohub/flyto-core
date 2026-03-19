"""Tests for ProxyPool rotation strategies."""
import pytest
from core.browser.proxy_pool import ProxyPool


class TestProxyPool:
    def test_round_robin(self):
        pool = ProxyPool(['a', 'b', 'c'], strategy='round_robin')
        assert pool.next() == 'a'
        assert pool.next() == 'b'
        assert pool.next() == 'c'
        assert pool.next() == 'a'  # wraps around

    def test_random(self):
        pool = ProxyPool(['a', 'b', 'c'], strategy='random')
        results = {pool.next() for _ in range(50)}
        assert len(results) >= 2  # should hit at least 2 of 3

    def test_failover(self):
        pool = ProxyPool(['a', 'b', 'c'], strategy='failover')
        assert pool.next() == 'a'
        assert pool.next() == 'a'  # always first

        pool.mark_failed('a')
        assert pool.next() == 'b'

        pool.mark_failed('b')
        assert pool.next() == 'c'

    def test_mark_failed_and_recover(self):
        pool = ProxyPool(['a', 'b'], strategy='round_robin')
        pool.mark_failed('a')
        assert pool.available == 1
        assert pool.next() == 'b'
        assert pool.next() == 'b'

        pool.mark_alive('a')
        assert pool.available == 2

    def test_all_failed_resets(self):
        pool = ProxyPool(['a', 'b'], strategy='round_robin')
        pool.mark_failed('a')
        pool.mark_failed('b')
        # All failed — should auto-reset
        result = pool.next()
        assert result in ('a', 'b')

    def test_reset(self):
        pool = ProxyPool(['a', 'b', 'c'], strategy='round_robin')
        pool.mark_failed('a')
        pool.mark_failed('b')
        pool.reset()
        assert pool.available == 3
        assert pool.next() == 'a'

    def test_empty_list_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            ProxyPool([], strategy='round_robin')

    def test_invalid_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            ProxyPool(['a'], strategy='invalid')

    def test_size_and_available(self):
        pool = ProxyPool(['a', 'b', 'c'], strategy='round_robin')
        assert pool.size == 3
        assert pool.available == 3
        pool.mark_failed('a')
        assert pool.size == 3
        assert pool.available == 2
