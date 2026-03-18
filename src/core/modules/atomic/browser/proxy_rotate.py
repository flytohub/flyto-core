# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Proxy Rotate Module — Rotate proxy on each call or on failure

Manages a list of proxies and rotates through them:
- Round-robin rotation
- Auto-rotate on navigation failure
- Remove dead proxies from pool
- Works by closing current browser and relaunching with new proxy
"""
import logging
from typing import Any, Dict, List
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field

logger = logging.getLogger(__name__)

# Module-level proxy state
_proxy_pool: List[str] = []
_proxy_index: int = 0
_dead_proxies: set = set()


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
    can_connect_to=['browser.*', 'flow.*'],
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
    ),
    output_schema={
        'action':        {'type': 'string',  'description': 'Action performed'},
        'current_proxy': {'type': 'string',  'description': 'Currently active proxy'},
        'pool_size':     {'type': 'number',  'description': 'Total proxies in pool'},
        'alive':         {'type': 'number',  'description': 'Alive proxies'},
        'dead':          {'type': 'number',  'description': 'Dead proxies'},
    },
    examples=[
        {'name': 'Init pool', 'params': {'action': 'init', 'proxies': ['http://p1:8080', 'http://p2:8080']}},
        {'name': 'Rotate', 'params': {'action': 'rotate'}},
    ],
    author='Flyto Team', license='MIT', timeout_ms=30000,
    required_permissions=["browser.read", "browser.write"],
)
class BrowserProxyRotateModule(BaseModule):
    module_name = "Rotate Proxy"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.action = self.params.get('action', 'rotate')
        self.proxies = self.params.get('proxies', [])
        self.headless = self.params.get('headless', True)
        self.provider_url = self.params.get('provider_url', '')
        self.provider_token = self.params.get('provider_token', '')

    async def execute(self) -> Any:
        global _proxy_pool, _proxy_index, _dead_proxies

        if self.action == 'init':
            proxies = list(self.proxies)

            # Fetch from provider API if configured
            if self.provider_url and not proxies:
                proxies = await self._fetch_from_provider()

            if not proxies:
                raise ValueError("No proxies provided. Pass proxy list or provider_url.")

            _proxy_pool = proxies
            _proxy_index = 0
            _dead_proxies = set()
            logger.info("Proxy pool initialized with %d proxies", len(_proxy_pool))
            return self._status("init")

        elif self.action == 'status':
            return self._status("status")

        elif self.action == 'mark_dead':
            if _proxy_pool and _proxy_index < len(_proxy_pool):
                dead = _proxy_pool[_proxy_index]
                _dead_proxies.add(dead)
                logger.warning("Marked proxy as dead: %s", dead[:30])
            return self._status("mark_dead")

        elif self.action == 'rotate':
            if not _proxy_pool:
                raise ValueError("Proxy pool not initialized. Use action='init' first.")

            # Find next alive proxy
            attempts = 0
            proxy = None
            while attempts < len(_proxy_pool):
                _proxy_index = (_proxy_index + 1) % len(_proxy_pool)
                candidate = _proxy_pool[_proxy_index]
                if candidate not in _dead_proxies:
                    proxy = candidate
                    break
                attempts += 1

            if not proxy:
                raise RuntimeError("All proxies are dead. No alive proxy available.")

            # Relaunch browser with new proxy
            browser = self.context.get('browser')
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass

            from core.browser.driver import BrowserDriver
            driver = BrowserDriver(headless=self.headless)
            await driver.launch(proxy=proxy, stealth=True)
            self.context['browser'] = driver

            logger.info("Rotated to proxy: %s", proxy[:30])
            return self._status("rotate", proxy)

        raise ValueError(f"Unknown action: {self.action}")

    async def _fetch_from_provider(self) -> list:
        """Fetch proxy list from a provider API (Bright Data, Oxylabs, SmartProxy, etc.)."""
        try:
            import httpx
            headers = {}
            if self.provider_token:
                headers['Authorization'] = f'Bearer {self.provider_token}'
            async with httpx.AsyncClient(timeout=15) as client:
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
        if not current_proxy and _proxy_pool and _proxy_index < len(_proxy_pool):
            current_proxy = _proxy_pool[_proxy_index]
        alive = len(_proxy_pool) - len(_dead_proxies)
        return {
            "status": "success",
            "action": action,
            "current_proxy": current_proxy,
            "pool_size": len(_proxy_pool),
            "alive": alive,
            "dead": len(_dead_proxies),
        }
