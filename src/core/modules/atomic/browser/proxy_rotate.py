# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Proxy Rotate Module — Rotate proxy on each call or on failure

Manages a list of proxies and rotates through them:
- Round-robin rotation
- Auto-rotate on navigation failure
- Remove dead proxies from pool
- Works by closing current browser and relaunching with new proxy

ONE ACTION REACHES THE WORLD. THREE DO NOT, AND SAID SO IN THE SAME VOICE.

All four actions came back through ``_status()``, which returns ``pool.size``,
``pool.available`` and the current proxy string. Every one of those is
arithmetic over the list of proxies the caller supplied, read out of an object
in this process's own ``context`` dict. Nothing was contacted; there is nothing
those numbers could be evidence of. `init`, `status` and `mark_dead` therefore
claim DISPATCHED -- the floor -- with the reason written into the effect, which
is the only thing they add over saying nothing at all.

`rotate` is a different module wearing the same name. It closes the browser,
launches a new one through the next proxy, re-imports the cookies and navigates
back to where it was. The evidence is the last of those:

    the re-navigation came back with an HTTP status   OBSERVED
    it raised, or landed somewhere else               INDETERMINATE
    there was nowhere to navigate back to             ACCEPTED

A status code is a number a server sent through the new proxy. It is the only
thing here that could not have been produced without the rotation, and it is the
question a caller actually has -- "does the new proxy work" -- rather than "is
there a string in ``current_proxy``".

WHAT THIS EXPOSES, and it was already in the code. The re-navigation is wrapped
in ``except Exception: logger.warning(...)``; so is the cookie re-import. A dead
proxy -- the ordinary reason anyone rotates -- makes ``driver.goto`` raise, the
warning goes to a log nobody reads, and the module returns ``status: "success"``
with the dead proxy in ``current_proxy``. The next step then runs against a
browser sitting on ``about:blank`` with no session. Both swallowed failures are
now carried in the envelope, and the cookie count is read back out of the new
context rather than counted from the list that was handed to it.
"""
import logging
from typing import Any, Dict, List, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ....utils import enforce_outbound_url, SSRFError

logger = logging.getLogger(__name__)


def _pool_only_outcome(*, action: str, pool_size: int, alive: int) -> Dict[str, Any]:
    """DISPATCHED for `init`, `status` and `mark_dead`.

    The floor of the ladder, chosen deliberately over ACCEPTED. Nothing here
    left this process: the pool is a Python object in the execution context,
    ``size`` is ``len()`` of the caller's own list and ``available`` is that
    minus a set this module populated. There is no other side to have
    acknowledged anything, so the honest claim is the smallest one -- with the
    reason attached, which is what this adds over the engine's silent default.
    """
    return envelope(
        Outcome.DISPATCHED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'proxy_pool_state',
            'action': action,
            'pool_size': pool_size,
            'alive': alive,
            'measured_by': None,
            'detail': (
                'Arithmetic over the proxy list the caller supplied, held in an '
                'object in this process. No proxy was contacted and no browser '
                'was launched, so these counters are not evidence about any '
                'proxy -- only about what this module was told.'
            ),
        }],
    )


def _rotate_outcome(
    *,
    proxy_fingerprint: str,
    pool_size: int,
    alive: int,
    saved_url: Optional[str],
    landed_url: Optional[str],
    status_code: Optional[int],
    nav_error: Optional[str],
    cookies_offered: int,
    cookies_in_new_context: Optional[int],
    cookie_error: Optional[str],
) -> Dict[str, Any]:
    """The rung a rotation earned, from the page load through the new proxy."""
    launch_effect = {
        'kind': 'browser_relaunched',
        # Never the proxy URL itself: these carry user:pass@host and this
        # envelope is copied into a trace row and a websocket frame.
        'proxy': proxy_fingerprint,
        'pool_size': pool_size,
        'alive': alive,
        'measured_by': None,
        'detail': (
            'A new BrowserDriver was launched with the next proxy. That it '
            'launched says nothing about whether the proxy answers -- the '
            're-navigation below is the part that does.'
        ),
    }

    cookie_effect = {
        'kind': 'cookies_in_new_context',
        'offered': cookies_offered,
        'present': cookies_in_new_context,
        'measured_by': (
            'BrowserContext.cookies() on the NEW context, read back after '
            'add_cookies()'
        ) if cookies_in_new_context is not None else None,
        'error': cookie_error,
        'detail': (
            'Read back rather than counted from the list that was handed over: '
            'add_cookies() returns normally for cookies the jar refuses, and a '
            'session that silently did not survive the rotation is the failure '
            'this preserves cookies to avoid.'
        ),
    }

    if isinstance(status_code, int) and not isinstance(status_code, bool):
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[launch_effect, cookie_effect, {
                'kind': 'navigation_through_new_proxy',
                'status_code': status_code,
                'url': landed_url,
                'measured_by': 'HTTP status of the re-navigation made through the new proxy',
                'detail': (
                    'A server answered through the rotated proxy. This is the '
                    'only value here that could not exist without the rotation '
                    'having happened. A non-2xx is still an observation: the '
                    'rung says how far the effect was followed, not whether the '
                    'answer was welcome.'
                ),
            }],
        )

    if saved_url is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[launch_effect, cookie_effect, {
                'kind': 'no_navigation_attempted',
                'measured_by': None,
                'detail': (
                    'There was no page to return to -- no browser before the '
                    'rotation, or one sitting on about:blank -- so nothing went '
                    'through the new proxy and nothing about it was observed.'
                ),
            }],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[launch_effect, cookie_effect, {
            'kind': 'navigation_through_new_proxy_unconfirmed',
            'predicate': 'the re-navigation through the new proxy returned an HTTP status',
            'url': saved_url,
            'landed_url': landed_url,
            'reason': nav_error or 'the navigation returned no status code',
            'measured_by': None,
            'detail': (
                'The browser was relaunched and nothing came back through the '
                'new proxy. A dead proxy is the ordinary cause and the ordinary '
                'reason to rotate; a fragment-only navigation produces no '
                'status code without anything being wrong. Indeterminate rather '
                'than failed: we cannot tell those apart from here. Before this '
                'the failure was a logger.warning beside status: "success".'
            ),
        }],
    )


def _fingerprint(proxy: str) -> str:
    """A proxy identified without its credentials.

    ``current_proxy`` in the payload already carries the raw string, which is a
    separate problem; this envelope is copied into a database column and a
    websocket frame and will not add to it.
    """
    if not proxy:
        return ''
    scheme, separator, rest = proxy.partition('://')
    if not separator:
        # No scheme. Strip the credential anyway: `user:pass@host:port` is a
        # perfectly ordinary way to write one and returning it whole here is
        # the leak this function exists to prevent.
        return proxy.rpartition('@')[2] or proxy
    host = rest.rpartition('@')[2]
    return f"{scheme}://{host}" if host else scheme


@register_module(
    module_id='browser.proxy_rotate',
    version='1.0.0',
    category='browser',
    tags=['browser', 'proxy', 'rotation', 'anti-ban', 'crawl'],
    label='Rotate Proxy',
    label_key='modules.browser.proxy_rotate.label',
    description='Rotate through a list of proxies. Relaunches browser with the next proxy.',
    description_key='modules.browser.proxy_rotate.description',
    icon='RefreshCw',
    color='#EC4899',
    input_types=['page', 'browser'],
    output_types=['browser', 'page'],
    can_receive_from=['browser.*', 'flow.*', 'start'],
    can_connect_to=['browser.*', 'flow.*', 'ai.*', 'llm.*', 'agent.*'],
    params_schema=compose(
        field('action', type='select', label='Action',
              required=True, default='rotate',
              options=[
                  {'value': 'init', 'label': 'Initialize proxy pool'},
                  {'value': 'rotate', 'label': 'Rotate to next proxy'},
                  {'value': 'mark_dead', 'label': 'Mark current proxy as dead'},
                  {'value': 'status', 'label': 'Get pool status'},
              ],
              group='basic'),
        field('proxies', type='array', label='Proxy list',
              description='List of proxy URLs (for init action). e.g., ["http://proxy1:8080", "socks5://proxy2:1080"].',
              required=False, default=[],
              items={'type': 'string', 'placeholder': 'http://user:pass@proxy:8080'},
              group='basic'),
        field('strategy', type='select', label='Rotation strategy',
              description='How to cycle through proxies.',
              default='round_robin',
              options=[
                  {'value': 'round_robin', 'label': 'Round Robin (sequential)'},
                  {'value': 'random', 'label': 'Random'},
                  {'value': 'failover', 'label': 'Failover (first available)'},
              ],
              required=False,
              showIf={"action": {"$in": ["init"]}},
              group='basic'),
        field('provider_url', type='string', label='Provider API URL',
              description='Proxy provider API endpoint that returns proxy IPs (for init). Fetches fresh IPs from Bright Data, Oxylabs, etc.',
              required=False, default='',
              placeholder='https://api.brightdata.com/zones/proxies?zone=residential',
              group='advanced'),
        field('provider_token', type='string', label='Provider API token',
              description='Bearer token for the proxy provider API.',
              required=False, default='', format='password',
              group='advanced'),
        field('headless', type='boolean', label='Headless',
              description='Run browser in headless mode after rotation.',
              default=True,
              group='basic'),
        field('preserve_cookies', type='boolean', label='Preserve cookies',
              description='Export cookies before rotation and import into the new browser. Keeps login sessions alive.',
              default=True,
              group='basic'),
    ),
    output_schema={
        'action':        {'type': 'string',  'description': 'Action performed'},
        'current_proxy': {'type': 'string',  'description': 'Currently active proxy'},
        'pool_size':     {'type': 'number',  'description': 'Total proxies in pool'},
        'alive':         {'type': 'number',  'description': 'Alive proxies'},
        'dead':          {'type': 'number',  'description': 'Dead proxies'},
        'status_code':   {'type': 'number',  'description': 'HTTP status of the re-navigation through the new proxy (rotate only)'},
        'cookies_in_new_context': {'type': 'number', 'description': 'Cookies present in the new context after the import (rotate only)'},
        'outcome':       {'type': 'object',  'description': (
            'How far the effect was followed. Decided per action: rotate is '
            '"observed" only when a page load came back through the new proxy; '
            'init, status and mark_dead reach no further than "dispatched" '
            'because nothing leaves this process.'
        )},
    },
    examples=[
        {'name': 'Init pool', 'params': {'action': 'init', 'proxies': ['http://p1:8080', 'http://p2:8080']}},
        {'name': 'Rotate', 'params': {'action': 'rotate'}},
    ],
    author='Flyto2 Team', license='MIT', timeout_ms=30000,
    required_permissions=["browser.read", "browser.write"],
)
class BrowserProxyRotateModule(BaseModule):
    module_name = "Rotate Proxy"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.action = self.params.get('action', 'rotate')
        self.proxies = self.params.get('proxies', [])
        self.strategy = self.params.get('strategy', 'round_robin')
        self.headless = self.params.get('headless', True)
        self.preserve_cookies = self.params.get('preserve_cookies', True)
        self.provider_url = self.params.get('provider_url', '')
        self.provider_token = self.params.get('provider_token', '')

    async def execute(self) -> Any:
        from core.browser.proxy_pool import ProxyPool

        if self.action == 'init':
            proxies = list(self.proxies)

            # Fetch from provider API if configured
            if self.provider_url and not proxies:
                proxies = await self._fetch_from_provider()

            if not proxies:
                raise ValueError("No proxies provided. Pass proxy list or provider_url.")

            pool = ProxyPool(proxies, strategy=self.strategy)
            self.context['_proxy_pool'] = pool
            logger.info("Proxy pool initialized: %d proxies, strategy=%s", pool.size, self.strategy)
            return self._status("init")

        elif self.action == 'status':
            return self._status("status")

        elif self.action == 'mark_dead':
            pool = self._get_pool()
            browser = self.context.get('browser')
            if browser and hasattr(browser, '_current_proxy') and browser._current_proxy:
                pool.mark_failed(browser._current_proxy)
            return self._status("mark_dead")

        elif self.action == 'rotate':
            pool = self._get_pool()
            proxy = pool.next()
            if not proxy:
                raise RuntimeError("All proxies are dead. No alive proxy available.")

            # Export cookies and URL from old browser
            browser = self.context.get('browser')
            saved_cookies = []
            saved_url = None
            if browser:
                if self.preserve_cookies:
                    try:
                        ctx = browser._context
                        if ctx:
                            saved_cookies = await ctx.cookies()
                            saved_url = browser.page.url
                            logger.info("Exported %d cookies for preservation", len(saved_cookies))
                    except Exception as e:
                        logger.warning("Cookie export failed: %s", e)
                try:
                    await browser.close()
                except Exception:
                    pass

            # Launch new browser with new proxy
            from core.browser.driver import BrowserDriver
            driver = BrowserDriver(headless=self.headless)
            await driver.launch(proxy=proxy, stealth=True)
            driver._current_proxy = proxy
            driver._proxy_pool = pool

            # Import cookies into new browser. Read back rather than assumed:
            # add_cookies() returns normally for cookies the jar refuses.
            cookies_present = None
            cookie_error = None
            if saved_cookies and self.preserve_cookies:
                try:
                    await driver._context.add_cookies(saved_cookies)
                    cookies_present = len(await driver._context.cookies())
                    logger.info(
                        "Imported %d cookies into new context, %d present",
                        len(saved_cookies), cookies_present,
                    )
                except Exception as e:
                    cookie_error = f"{type(e).__name__}: {e}"
                    logger.warning("Cookie import failed: %s", e)

            # Navigate back to the same URL. The status code that comes back is
            # the only evidence the new proxy actually carries traffic, so it is
            # kept rather than discarded.
            status_code = None
            landed_url = None
            nav_error = None
            target_url = saved_url if saved_url and saved_url != 'about:blank' else None
            if target_url:
                try:
                    nav = await driver.goto(target_url)
                    status_code = (nav or {}).get('status_code')
                    landed_url = (nav or {}).get('url')
                except Exception as e:
                    nav_error = f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"
                    logger.warning("Re-navigation after rotation failed: %s", e)

            self.context['browser'] = driver

            logger.info("Rotated to proxy: %s", proxy[:30])
            result = self._status("rotate", proxy)
            pool = self.context.get('_proxy_pool')
            result["outcome"] = _rotate_outcome(
                proxy_fingerprint=_fingerprint(proxy),
                pool_size=pool.size if pool else 0,
                alive=pool.available if pool else 0,
                saved_url=target_url,
                landed_url=landed_url,
                status_code=status_code,
                nav_error=nav_error,
                cookies_offered=len(saved_cookies),
                cookies_in_new_context=cookies_present,
                cookie_error=cookie_error,
            )
            result["status_code"] = status_code
            result["cookies_in_new_context"] = cookies_present
            return result

        raise ValueError(f"Unknown action: {self.action}")

    def _get_pool(self):
        pool = self.context.get('_proxy_pool')
        if not pool:
            raise ValueError("Proxy pool not initialized. Use action='init' first.")
        return pool

    async def _fetch_from_provider(self) -> list:
        """Fetch proxy list from a provider API (Bright Data, Oxylabs, SmartProxy, etc.)."""
        # SECURITY: gate the client-controlled provider URL through the SSRF
        # guard before fetching it server-side (GHSA-pgwh-4jj4-qm8v).
        try:
            enforce_outbound_url(self.provider_url)
        except SSRFError as e:
            raise ValueError(f"SSRF protection blocked request: {e}")
        try:
            import httpx
            from ....utils import guarded_httpx_client
            headers = {}
            if self.provider_token:
                headers['Authorization'] = f'Bearer {self.provider_token}'
            async with guarded_httpx_client(timeout=15) as client:
                resp = await client.get(self.provider_url, headers=headers)
                resp.raise_for_status()

                data = resp.json() if 'json' in resp.headers.get('content-type', '') else None

                if data:
                    # Handle common API formats
                    if isinstance(data, list):
                        # List of strings or objects
                        proxies = []
                        for item in data:
                            if isinstance(item, str):
                                proxies.append(item)
                            elif isinstance(item, dict):
                                # Common formats: {ip, port, protocol} or {proxy_address}
                                if 'proxy_address' in item:
                                    proxies.append(item['proxy_address'])
                                elif 'ip' in item:
                                    port = item.get('port', 8080)
                                    proto = item.get('protocol', 'http')
                                    proxies.append(f"{proto}://{item['ip']}:{port}")
                        return proxies
                    elif isinstance(data, dict) and 'proxies' in data:
                        return data['proxies']
                else:
                    # Plain text: one proxy per line
                    lines = resp.text.strip().split('\n')
                    return [line.strip() for line in lines if line.strip()]

        except Exception as e:
            logger.warning("Failed to fetch proxies from provider: %s", e)
        return []

    def _status(self, action: str, current_proxy: str = "") -> dict:
        pool = self.context.get('_proxy_pool')
        if not current_proxy:
            browser = self.context.get('browser')
            if browser and hasattr(browser, '_current_proxy'):
                current_proxy = browser._current_proxy or ''
        result = {
            "status": "success",
            "action": action,
            "current_proxy": current_proxy,
            "pool_size": pool.size if pool else 0,
            "alive": pool.available if pool else 0,
            "dead": (pool.size - pool.available) if pool else 0,
        }
        if action != "rotate":
            # `rotate` overwrites this with an envelope that has a measurement
            # behind it. The other three have none, and say so.
            result["outcome"] = _pool_only_outcome(
                action=action,
                pool_size=result["pool_size"],
                alive=result["alive"],
            )
        return result
