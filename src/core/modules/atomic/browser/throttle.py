# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Throttle Module — Per-domain rate limiting

Tracks request timing per domain. Before each navigation,
waits if the minimum interval hasn't passed since the last
request to that domain.

Respects robots.txt crawl-delay when available.
Prevents getting banned by hitting sites too fast.
"""
import asyncio
import logging
import time
from typing import Any, Dict
from urllib.parse import urlparse
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field

logger = logging.getLogger(__name__)


@register_module(
    module_id='browser.throttle',
    version='1.0.0',
    category='browser',
    tags=['browser', 'rate-limit', 'throttle', 'polite', 'crawl'],
    label='Throttle',
    label_key='modules.browser.throttle.label',
    description='Per-domain rate limiting. Waits between requests to the same domain to avoid bans.',
    description_key='modules.browser.throttle.description',
    icon='Clock',
    color='#EAB308',
    input_types=['page'],
    output_types=['page'],
    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*'],
    params_schema=compose(
        field('strategy', type='select', label='Strategy',
              description='Delay strategy: fixed, adaptive (auto-backoff on errors), human_like (random delays with reading pauses).',
              default='fixed',
              options=[
                  {'value': 'fixed', 'label': 'Fixed (constant delay)'},
                  {'value': 'adaptive', 'label': 'Adaptive (backoff on errors, recover on success)'},
                  {'value': 'human_like', 'label': 'Human-like (gaussian jitter + reading pauses)'},
              ],
              group='basic'),
        field('min_interval_ms', type='number', label='Base / Min interval (ms)',
              description='Base delay (fixed) or minimum delay (adaptive/human_like).',
              default=2000, min=0, max=60000, step=500,
              group='basic'),
        field('max_interval_ms', type='number', label='Max interval (ms)',
              description='Maximum delay for adaptive/human_like strategies.',
              default=15000, min=1000, max=120000, step=1000,
              showIf={"strategy": {"$in": ["adaptive", "human_like"]}},
              group='basic'),
        field('url', type='string', label='URL (optional)',
              description='URL to throttle for. Empty = use current page URL.',
              required=False, default='',
              group='basic'),
        field('signal', type='select', label='Signal',
              description='Report success or error to update adaptive delay.',
              default='none',
              options=[
                  {'value': 'none', 'label': 'Just wait (no signal)'},
                  {'value': 'success', 'label': 'Report success (decrease delay)'},
                  {'value': 'error', 'label': 'Report error (increase delay)'},
                  {'value': 'rate_limit', 'label': 'Report rate limit / 429 (aggressive backoff)'},
              ],
              showIf={"strategy": {"$in": ["adaptive", "human_like"]}},
              group='advanced'),
    ),
    output_schema={
        'domain':      {'type': 'string', 'description': 'Domain that was throttled'},
        'waited_ms':   {'type': 'number', 'description': 'Actual milliseconds waited (0 if no wait needed)'},
        'interval_ms': {'type': 'number', 'description': 'Current effective interval'},
        'strategy':    {'type': 'string', 'description': 'Active strategy'},
    },
    examples=[
        {'name': 'Fixed 2s delay', 'params': {'min_interval_ms': 2000}},
        {'name': 'Adaptive with backoff', 'params': {'strategy': 'adaptive', 'min_interval_ms': 1000, 'max_interval_ms': 15000}},
        {'name': 'Human-like delays', 'params': {'strategy': 'human_like', 'min_interval_ms': 1500, 'max_interval_ms': 8000}},
    ],
    author='Flyto Team', license='MIT', timeout_ms=65000,
    required_permissions=["browser.read"],
)
class BrowserThrottleModule(BaseModule):
    module_name = "Throttle"
    required_permission = "browser.read"

    def validate_params(self) -> None:
        self.strategy = self.params.get('strategy', 'fixed')
        self.min_interval_ms = self.params.get('min_interval_ms', 2000)
        self.max_interval_ms = self.params.get('max_interval_ms', 15000)
        self.url = self.params.get('url', '')
        self.signal = self.params.get('signal', 'none')

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Determine domain
        url = self.url
        if not url:
            url = await browser.page.evaluate("() => window.location.href")

        parsed = urlparse(url)
        domain = parsed.netloc or parsed.hostname or url

        # Get or create per-domain RateLimiter
        from core.browser.rate_limiter import RateLimiter

        limiter_key = f'_throttle_{domain}'
        limiter = self.context.get(limiter_key)
        if not limiter or not isinstance(limiter, RateLimiter):
            limiter = RateLimiter(
                strategy=self.strategy,
                min_delay_ms=self.min_interval_ms,
                max_delay_ms=self.max_interval_ms,
                base_delay_ms=self.min_interval_ms,
            )
            self.context[limiter_key] = limiter

        # Process signal (from previous step in workflow)
        if self.signal == 'success':
            limiter.on_success()
        elif self.signal == 'error':
            limiter.on_error(is_rate_limit=False)
        elif self.signal == 'rate_limit':
            limiter.on_error(is_rate_limit=True)

        # Wait according to strategy
        t0 = time.monotonic()
        await limiter.wait()
        waited_ms = round((time.monotonic() - t0) * 1000)

        if waited_ms > 0:
            logger.debug("Throttled %s: waited %dms (strategy=%s)", domain, waited_ms, self.strategy)

        return {
            "status": "success",
            "domain": domain,
            "waited_ms": waited_ms,
            "interval_ms": limiter.current_delay_ms,
            "strategy": self.strategy,
        }
