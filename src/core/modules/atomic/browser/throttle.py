# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Throttle Module — Per-domain rate limiting

Tracks request timing per domain. Before each navigation,
waits if the minimum interval hasn't passed since the last
request to that domain.

Respects robots.txt crawl-delay when available.
Prevents getting banned by hitting sites too fast.

THE EFFECT IS ELAPSED TIME, SO THE CLOCK IS THE MEASUREMENT

Three of the four numbers this module returns are the caller's own parameters
coming back around: ``strategy`` is ``self.strategy``, ``interval_ms`` is
``limiter.current_delay_ms`` which under the default ``fixed`` strategy is
exactly ``min_interval_ms``, and ``domain`` is parsed out of the URL that was
handed in. The fourth is not:

    t0 = time.monotonic(); await limiter.wait()
    waited_ms = round((time.monotonic() - t0) * 1000)

A monotonic clock read on both sides of the wait. It cannot be non-zero without
time having actually passed inside this process, and no parameter can inflate
it. That is the whole effect of this module, measured.

    the clock shows time elapsed    OBSERVED
    it shows none                   ACCEPTED

The zero case is ACCEPTED rather than OBSERVED, and it is not a technicality --
it is the failure this module has. ``RateLimiter`` keeps its per-domain state in
``self.context['_throttle_<domain>']``, so a context that is not carried between
steps hands every call a brand-new limiter, whose ``_last_request_time`` starts
at 0.0, whose first ``wait()`` therefore computes an elapsed of "since the
machine booted", and which sleeps for nothing. The old payload for that is
``{"status": "success", "waited_ms": 0, "interval_ms": 2000}``: a green tick, a
configured interval, and a crawler going out at full speed. A first call to a
domain legitimately waits zero too, and the two are indistinguishable from here
-- which is exactly why zero claims nothing.

Nothing on this ladder is about politeness. A measured wait says this process
slept; whether the site was happy about the rate is not a thing this module can
see.
"""
import asyncio
import logging
import time
from typing import Any, Dict
from urllib.parse import urlparse

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field

logger = logging.getLogger(__name__)


def _throttle_outcome(
    *, domain: str, waited_ms: int, interval_ms: Any, strategy: str, reused_limiter: bool
) -> Dict[str, Any]:
    """OBSERVED when the clock moved, ACCEPTED when it did not."""
    requested_effect = {
        'kind': 'interval_requested',
        'domain': domain,
        'interval_ms': interval_ms,
        'strategy': strategy,
        'measured_by': None,
        'detail': (
            'The limiter\'s configured delay. Under the default fixed strategy '
            'it is the min_interval_ms parameter unchanged, and it is the same '
            'number whether the wait happened or not.'
        ),
    }

    if waited_ms > 0:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[requested_effect, {
                'kind': 'wait_elapsed',
                'domain': domain,
                'waited_ms': waited_ms,
                'measured_by': 'time.monotonic() read before and after limiter.wait()',
                'detail': (
                    'Wall-clock time that passed inside this process. It cannot '
                    'be non-zero without the sleep having happened. It says this '
                    'process waited -- not that the site was reached politely, '
                    'which is not something this module can see.'
                ),
            }],
        )

    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[requested_effect, {
            'kind': 'no_wait_elapsed',
            'domain': domain,
            'waited_ms': 0,
            'reused_limiter': reused_limiter,
            'measured_by': 'time.monotonic() read before and after limiter.wait()',
            'detail': (
                'The limiter was consulted and asked for no wait. A first '
                'request to a domain legitimately waits zero -- and so does '
                'every request when the execution context is not carried '
                'between steps, because each call then builds a fresh limiter '
                'with no history. The two are indistinguishable from here, so '
                'a zero claims only that the limiter answered.'
            ),
        }],
    )


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
    can_connect_to=['browser.*', 'flow.*', 'ai.*', 'llm.*', 'agent.*'],
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
        'reused_limiter': {'type': 'boolean', 'description': 'Whether a limiter with history for this domain survived from an earlier step'},
        'outcome':     {'type': 'object', 'description': (
            'How far the effect was followed: "observed" when the monotonic '
            'clock shows time elapsed, "accepted" when the limiter asked for '
            'no wait'
        )},
    },
    examples=[
        {'name': 'Fixed 2s delay', 'params': {'min_interval_ms': 2000}},
        {'name': 'Adaptive with backoff', 'params': {'strategy': 'adaptive', 'min_interval_ms': 1000, 'max_interval_ms': 15000}},
        {'name': 'Human-like delays', 'params': {'strategy': 'human_like', 'min_interval_ms': 1500, 'max_interval_ms': 8000}},
    ],
    author='Flyto2 Team', license='MIT', timeout_ms=65000,
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
        # Whether a limiter with history was found decides whether a waited_ms
        # of 0 means "first request to this domain" or "no state survived the
        # last step". The envelope carries it; neither is claimed as the other.
        reused_limiter = bool(limiter) and isinstance(limiter, RateLimiter)
        if not reused_limiter:
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
            "reused_limiter": reused_limiter,
            "outcome": _throttle_outcome(
                domain=domain,
                waited_ms=waited_ms,
                interval_ms=limiter.current_delay_ms,
                strategy=self.strategy,
                reused_limiter=reused_limiter,
            ),
        }
