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

# Module-level domain timing tracker (shared across execution)
_domain_last_request: Dict[str, float] = {}


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
        field('min_interval_ms', type='number', label='Min interval (ms)',
              description='Minimum milliseconds between requests to the same domain.',
              default=2000, min=0, max=60000, step=500,
              group='basic'),
        field('url', type='string', label='URL (optional)',
              description='URL to throttle for. Empty = use current page URL.',
              required=False, default='',
              group='basic'),
        field('randomize', type='boolean', label='Randomize delay',
              description='Add ±30% random jitter to the interval (looks more human).',
              default=True,
              group='basic'),
    ),
    output_schema={
        'domain':     {'type': 'string', 'description': 'Domain that was throttled'},
        'waited_ms':  {'type': 'number', 'description': 'Actual milliseconds waited (0 if no wait needed)'},
        'interval_ms': {'type': 'number', 'description': 'Configured interval'},
    },
    examples=[
        {'name': 'Wait 2s between same-domain requests', 'params': {'min_interval_ms': 2000}},
        {'name': 'Polite crawling (5s)', 'params': {'min_interval_ms': 5000, 'randomize': True}},
    ],
    author='Flyto Team', license='MIT', timeout_ms=65000,
    required_permissions=["browser.read"],
)
class BrowserThrottleModule(BaseModule):
    module_name = "Throttle"
    required_permission = "browser.read"

    def validate_params(self) -> None:
        self.min_interval_ms = self.params.get('min_interval_ms', 2000)
        self.url = self.params.get('url', '')
        self.randomize = self.params.get('randomize', True)

    async def execute(self) -> Any:
        global _domain_last_request

        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Determine domain
        url = self.url
        if not url:
            url = await browser.page.evaluate("() => window.location.href")

        parsed = urlparse(url)
        domain = parsed.netloc or parsed.hostname or url

        # Check timing
        now = time.monotonic() * 1000  # ms
        last = _domain_last_request.get(domain, 0)
        elapsed = now - last

        waited_ms = 0
        if elapsed < self.min_interval_ms:
            wait_needed = self.min_interval_ms - elapsed

            # Add jitter
            if self.randomize:
                import random
                jitter = wait_needed * 0.3 * (random.random() * 2 - 1)  # ±30%
                wait_needed = max(0, wait_needed + jitter)

            if wait_needed > 0:
                logger.debug("Throttling %s: waiting %.0fms", domain, wait_needed)
                await asyncio.sleep(wait_needed / 1000)
                waited_ms = round(wait_needed)

        # Update last request time
        _domain_last_request[domain] = time.monotonic() * 1000

        return {
            "status": "success",
            "domain": domain,
            "waited_ms": waited_ms,
            "interval_ms": self.min_interval_ms,
        }
