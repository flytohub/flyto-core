# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Network Module

Monitor and intercept network requests.

THREE ACTIONS, TWO DIFFERENT KINDS OF ZERO

`monitor` only watches; `block` and `intercept` change what the page receives.
All three returned ``status: "success"`` with a count, and a count of 0 meant
something different in each case and nothing in all of them:

    monitor    OBSERVED when requests arrived -- every entry is a Playwright
               `request` event carrying a URL, method and resource type the
               browser reported. ACCEPTED at zero: an empty capture reads
               identically whether the page made no requests, the regex matched
               none of them, or the listener was on a different page object.
               That is `database.query`'s empty result set.
    block      OBSERVED when at least one route was aborted -- the count is of
               `route.abort()` calls that RETURNED, on routes the browser
               handed us. ACCEPTED at zero, for the same reason: a filter that
               matched nothing and a route handler that never ran are the same
               zero.
    intercept  OBSERVED when at least one route was fulfilled with the mock.
               ACCEPTED at zero.

WHY THE COUNTERS MOVED. ``blocked_count += 1`` and the ``requests.append``
happened BEFORE the ``await route.abort()`` they were counting, and the same
shape stood in `intercept` around ``route.fulfill``. A route that raises on
abort -- an already-handled route, a page torn down mid-flight -- was counted as
blocked and reported as a URL that had been stopped. The count is the rung's
only evidence, so it now counts calls that came back, not calls that were
attempted. Nothing else about the handlers changed: the exception propagates out
of the handler exactly as it did before.

What OBSERVED does not say for `block`: an aborted route is not a request that
never reached the network -- Chromium may have started it before the route
handler ran. What is claimed is that this many routes were aborted.
"""
import asyncio
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field


#: What each action's count is a count OF, and the line that produced it.
_NETWORK_MEASURES = {
    'monitor': (
        'requests_captured',
        'len() over Playwright `request` events the browser delivered',
        'Each entry is a request the browser reported, with the URL, method and '
        'resource type it reported. Watching only: nothing here changed what the '
        'page received.',
    ),
    'block': (
        'routes_aborted',
        'count of route.abort() calls that returned, on routes the browser handed us',
        'Each one is a route this module aborted. An aborted route is not a '
        'request that never reached the network -- only one the page was not '
        'given the answer to.',
    ),
    'intercept': (
        'routes_fulfilled',
        'count of route.fulfill() calls that returned, on routes the browser handed us',
        'Each one is a route this module answered with the mock response '
        'instead of letting it reach the network.',
    ),
}


def _network_outcome(*, action: str, count: int, listened_ms: int,
                     url_pattern: Optional[str], resource_type: Optional[str]) -> Dict[str, Any]:
    """OBSERVED for routes and requests that arrived, ACCEPTED for a quiet window."""
    kind, measured_by, detail = _NETWORK_MEASURES[action]
    if count:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': kind,
                'action': action,
                'count': count,
                'listened_ms': listened_ms,
                'url_pattern': url_pattern,
                'resource_type': resource_type,
                'measured_by': measured_by,
                'detail': detail,
            }],
        )
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': f'no_{kind}',
            'action': action,
            'count': 0,
            'listened_ms': listened_ms,
            'url_pattern': url_pattern,
            'resource_type': resource_type,
            'measured_by': None,
            'detail': (
                'The handler was installed for the whole window and nothing '
                'matched. A zero reads identically whether the page made no '
                'requests, the filters matched none of them, or the handler was '
                'attached to a different page object -- so it is not an '
                'observation of the network.'
            ),
        }],
    )


@register_module(
    module_id='browser.network',
    version='1.0.0',
    category='browser',
    tags=['browser', 'network', 'request', 'response', 'intercept', 'ssrf_protected'],
    label='Network Monitor',
    label_key='modules.browser.network.label',
    description='Monitor and intercept network requests',
    description_key='modules.browser.network.description',
    icon='Globe',
    color='#198754',

    # Connection types
    input_types=['page'],
    output_types=['array', 'json'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],
    params_schema=compose(
        field(
            'action',
            type='select',
            label='Action',
            label_key='modules.browser.network.params.action.label',
            description='Network action to perform',
            required=True,
            options=[
                {'value': 'monitor', 'label': 'Monitor (capture requests)'},
                {'value': 'block', 'label': 'Block (abort matching requests)'},
                {'value': 'intercept', 'label': 'Intercept (mock responses)'},
            ],
        ),
        field(
            'url_pattern',
            type='string',
            label='URL Pattern',
            label_key='modules.browser.network.params.url_pattern.label',
            placeholder='.*\\.api\\..*',
            description='Regex pattern to match request URLs',
            required=False,
        ),
        field(
            'resource_type',
            type='string',
            label='Resource Type',
            label_key='modules.browser.network.params.resource_type.label',
            description='Filter by resource type (document, script, image, etc)',
            placeholder='document',
            required=False,
        ),
        presets.TIMEOUT_MS(default=30000),
        field(
            'mock_response',
            type='object',
            label='Mock Response',
            label_key='modules.browser.network.params.mock_response.label',
            description='Response to return for intercepted requests',
            required=False,
            showIf={"action": {"$in": ["intercept"]}},
        ),
        field(
            'include_headers',
            type='boolean',
            label='Include Headers',
            description='Include request headers in captured output. Disable for reusable smoke artifacts.',
            default=True,
            required=False,
        ),
        field(
            'strip_query',
            type='boolean',
            label='Strip Query String',
            description='Remove query strings and fragments from captured URLs.',
            default=False,
            required=False,
        ),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.network.output.status.description'},
        'requests': {'type': 'array', 'description': 'Captured network requests',
                'description_key': 'modules.browser.network.output.requests.description'},
        'blocked_count': {'type': 'number', 'description': 'The blocked count',
                'description_key': 'modules.browser.network.output.blocked_count.description'},
        'outcome': {'type': 'object', 'description': (
            'How far the effect was followed: "observed" when requests were '
            'captured or routes were aborted or fulfilled, "accepted" when '
            'nothing matched during the window'
        ),
                'description_key': 'modules.browser.network.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Monitor API calls',
            'params': {'action': 'monitor', 'url_pattern': '.*api.*', 'timeout': 10000}
        },
        {
            'name': 'Block images',
            'params': {'action': 'block', 'resource_type': 'image'}
        },
        {
            'name': 'Mock API response',
            'params': {
                'action': 'intercept',
                'url_pattern': '.*users.*',
                'mock_response': {
                    'status': 200,
                    'body': '{"users": []}'
                }
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserNetworkModule(BaseModule):
    """Network Monitor Module"""

    module_name = "Network Monitor"
    module_description = "Monitor and intercept network requests"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'action' not in self.params:
            raise ValueError("Missing required parameter: action")

        self.action = self.params['action']
        if self.action not in ['monitor', 'block', 'intercept']:
            raise ValueError(f"Invalid action: {self.action}")

        self.url_pattern = self.params.get('url_pattern')
        self.resource_type = self.params.get('resource_type')
        self.timeout = self.params.get('timeout', 30000)
        self.mock_response = self.params.get('mock_response')
        self.include_headers = self.params.get('include_headers', True)
        self.strip_query = self.params.get('strip_query', False)

        if self.action == 'intercept' and not self.mock_response:
            raise ValueError("intercept action requires mock_response")

        # Compile regex if provided
        self._pattern = re.compile(self.url_pattern) if self.url_pattern else None

    def _matches_filter(self, request) -> bool:
        """Check if request matches filters"""
        if self._pattern and not self._pattern.search(request.url):
            return False
        if self.resource_type and request.resource_type != self.resource_type:
            return False
        return True

    def _safe_url(self, url: str) -> str:
        if not self.strip_query:
            return url
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.real_page
        requests: List[Dict[str, Any]] = []
        blocked_count = 0

        if self.action == 'monitor':
            requests_by_url: Dict[str, List[Dict[str, Any]]] = {}

            def handle_request(request):
                if self._matches_filter(request):
                    entry = {
                        'url': self._safe_url(request.url),
                        'method': request.method,
                        'resource_type': request.resource_type,
                    }
                    if self.include_headers:
                        entry['headers'] = dict(request.headers)
                    requests.append(entry)
                    requests_by_url.setdefault(request.url, []).append(entry)

            def handle_response(response):
                # Find matching request and add response info
                for req in requests_by_url.get(response.url, []):
                    if 'status' not in req:
                        req['status'] = response.status
                        req['status_text'] = response.status_text
                        break

            page.on('request', handle_request)
            page.on('response', handle_response)

            try:
                await asyncio.sleep(self.timeout / 1000)
            finally:
                page.remove_listener('request', handle_request)
                page.remove_listener('response', handle_response)

            return {
                "status": "success",
                "requests": requests,
                "count": len(requests),
                "outcome": self._outcome(len(requests)),
            }

        elif self.action == 'block':
            async def handle_route(route):
                nonlocal blocked_count
                request = route.request
                if self._matches_filter(request):
                    # Abort FIRST, then count. The counter is the only evidence
                    # this action has, and a route that raises on abort was not
                    # blocked -- counting it before the await reported a URL as
                    # stopped when nothing had stopped it.
                    url = self._safe_url(request.url)
                    await route.abort()
                    blocked_count += 1
                    requests.append({'url': url, 'blocked': True})
                else:
                    await route.continue_()

            await page.route('**/*', handle_route)

            try:
                await asyncio.sleep(self.timeout / 1000)
            finally:
                await page.unroute('**/*', handle_route)

            return {
                "status": "success",
                "requests": requests,
                "blocked_count": blocked_count,
                "outcome": self._outcome(blocked_count),
            }

        elif self.action == 'intercept':
            async def handle_route(route):
                request = route.request
                if self._matches_filter(request):
                    # Fulfil FIRST, then count -- see the block branch above.
                    url = self._safe_url(request.url)
                    await route.fulfill(
                        status=self.mock_response.get('status', 200),
                        content_type=self.mock_response.get('content_type', 'application/json'),
                        body=self.mock_response.get('body', '{}')
                    )
                    requests.append({'url': url, 'intercepted': True})
                else:
                    await route.continue_()

            await page.route('**/*', handle_route)

            try:
                await asyncio.sleep(self.timeout / 1000)
            finally:
                await page.unroute('**/*', handle_route)

            return {
                "status": "success",
                "requests": requests,
                "intercepted_count": len(requests),
                "outcome": self._outcome(len(requests)),
            }

    def _outcome(self, count: int) -> Dict[str, Any]:
        return _network_outcome(
            action=self.action,
            count=count,
            listened_ms=self.timeout,
            url_pattern=self.url_pattern,
            resource_type=self.resource_type,
        )
