# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Response Module — Capture network response bodies

Listens for XHR/fetch responses matching a URL pattern,
captures the response body (JSON, text, binary), and returns structured data.

Use case: Extract data from API calls made by the page (dashboards, SPAs, feeds).

`count: 0` WITH `status: "success"` IS THE WHOLE PROBLEM

This module is pointed at a page and asked to come back with the API data the
page fetched. When it comes back with nothing it returns exactly what it returns
on a page that never made the call, on a regex that matched none of the URLs, on
a ``resource_types`` filter that excluded them, and on a listen window that
closed before the request went out. All four are ``{"responses": [], "count": 0,
"status": "success"}``.

    at least one response was captured   OBSERVED
    none were                            ACCEPTED

A captured response is an observation and not a small one: ``response.status``
and ``response.headers`` are what the server sent, and ``await response.body()``
pulls the bytes off the wire. None of that exists without the exchange having
happened. An empty capture is `database.query`'s empty result set -- a value
unchanged by whether the effect occurred -- and claims only that the listener
was attached and the window ran.

Bodies that failed to read are counted separately rather than silently folded
in. ``entry['body'] = None`` with an ``error`` beside it still means the
response's status and headers were observed; it is the payload that was not, and
a consumer reading ``count`` alone would not know.

REACHING THE END OF THE WINDOW IS NOT A TIMEOUT. ``asyncio.wait_for`` here is
how the module holds the window open; with the default ``max_responses=0`` the
event is never set and the ``TimeoutError`` is the normal path. It is not the
severed-observation-channel case that `outcome.py` calls indeterminate.
"""
import asyncio
import json
import logging
import re
from typing import Any, Dict, List

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup

logger = logging.getLogger(__name__)


def _response_outcome(
    *,
    count: int,
    unreadable_bodies: int,
    url_pattern: str,
    listened_ms: int,
) -> Dict[str, Any]:
    """OBSERVED for responses that came off the wire, ACCEPTED for a quiet window."""
    if count:
        effects = [{
            'kind': 'responses_captured',
            'count': count,
            'url_pattern': url_pattern,
            'listened_ms': listened_ms,
            'measured_by': (
                'len() over Playwright `response` events, each with a status '
                'and headers the server sent'
            ),
            'detail': (
                'Every entry is an exchange that happened: the status line and '
                'headers came from the server, and the body was pulled off the '
                'wire with response.body().'
            ),
        }]
        if unreadable_bodies:
            effects.append({
                'kind': 'response_bodies_unreadable',
                'count': unreadable_bodies,
                'measured_by': 'entries whose response.body() raised',
                'detail': (
                    'The status and headers of these responses were observed; '
                    'the payload was not. A body evicted from the browser cache '
                    'before this module asked for it does this. They are counted '
                    'here rather than folded into `count`, where they would '
                    'read as captured data.'
                ),
            })
        return envelope(Outcome.OBSERVED, claim_by=ClaimBy.NONE, effects=effects)

    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'no_responses_captured',
            'count': 0,
            'url_pattern': url_pattern,
            'listened_ms': listened_ms,
            'measured_by': None,
            'detail': (
                'The listener was attached for the whole window and nothing '
                'matched. A zero reads identically whether the page never made '
                'the call, the URL pattern matched none of them, the resource '
                'type filter excluded them, or the window closed first -- so it '
                'is not an observation of the network.'
            ),
        }],
    )


@register_module(
    module_id='browser.response',
    version='1.0.0',
    category='browser',
    tags=['browser', 'network', 'api', 'response', 'xhr', 'fetch'],
    label='Capture Response',
    label_key='modules.browser.response.label',
    description='Capture API response bodies (XHR/fetch). Filter by URL pattern, extract JSON data from page API calls.',
    description_key='modules.browser.response.description',
    icon='Download',
    color='#06B6D4',
    input_types=['page'],
    output_types=['json', 'array'],
    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],
    params_schema=compose(
        field('url_pattern', type='string', label='URL Pattern',
              description='Regex pattern to match response URLs (e.g., "/api/data", "graphql").',
              required=True, placeholder='/api/.*\\.json',
              group='basic'),
        field('wait_ms', type='number', label='Listen duration (ms)',
              description='How long to listen for matching responses. 0 = capture during next navigation only.',
              default=5000, min=0, max=60000, step=1000,
              group='basic'),
        field('max_responses', type='number', label='Max responses',
              description='Stop after capturing this many responses. 0 = no limit.',
              default=0, min=0, max=100,
              group='basic'),
        field('resource_types', type='string', label='Resource types',
              description='Comma-separated resource types to capture (xhr, fetch, document). Empty = all.',
              default='xhr,fetch', required=False,
              group='advanced'),
        field('include_headers', type='boolean', label='Include headers',
              description='Include response headers in output.',
              default=False,
              group='advanced'),
    ),
    output_schema={
        'responses': {'type': 'array', 'description': 'Captured responses [{url, status, body, content_type, headers}]'},
        'count': {'type': 'number', 'description': 'Number of responses captured'},
        'unreadable_body_count': {'type': 'number', 'description': 'Captured responses whose body could not be read'},
        'outcome': {'type': 'object', 'description': (
            'How far the capture was followed: "observed" when responses came '
            'off the wire, "accepted" when the window matched nothing'
        )},
    },
    examples=[
        {'name': 'Capture JSON API calls', 'params': {'url_pattern': '/api/', 'wait_ms': 5000}},
        {'name': 'Capture GraphQL responses', 'params': {'url_pattern': 'graphql', 'wait_ms': 3000}},
    ],
    author='Flyto2 Team', license='MIT', timeout_ms=65000,
    required_permissions=["browser.read"],
)
class BrowserResponseModule(BaseModule):
    module_name = "Capture Response"
    required_permission = "browser.read"

    def validate_params(self) -> None:
        self.url_pattern = re.compile(self.params['url_pattern'])
        self.wait_ms = self.params.get('wait_ms', 5000)
        self.max_responses = self.params.get('max_responses', 0)
        types_str = self.params.get('resource_types', 'xhr,fetch')
        self.resource_types = set(t.strip() for t in types_str.split(',') if t.strip()) if types_str else set()
        self.include_headers = self.params.get('include_headers', False)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.real_page
        captured: List[Dict[str, Any]] = []
        done_event = asyncio.Event()

        async def handle_response(response):
            if self.max_responses and len(captured) >= self.max_responses:
                return
            if self.resource_types and response.request.resource_type not in self.resource_types:
                return
            if not self.url_pattern.search(response.url):
                return

            entry: Dict[str, Any] = {
                'url': response.url,
                'status': response.status,
                'method': response.request.method,
                'resource_type': response.request.resource_type,
                'content_type': response.headers.get('content-type', ''),
            }

            # Capture body
            try:
                body = await response.body()
                ct = entry['content_type']
                if 'json' in ct:
                    try:
                        entry['body'] = json.loads(body)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        entry['body'] = body.decode('utf-8', errors='replace')
                elif 'text' in ct or 'html' in ct or 'xml' in ct or 'javascript' in ct:
                    entry['body'] = body.decode('utf-8', errors='replace')
                else:
                    entry['body'] = f"[binary {len(body)} bytes]"
            except Exception as e:
                entry['body'] = None
                entry['error'] = str(e)

            if self.include_headers:
                entry['headers'] = dict(response.headers)

            captured.append(entry)
            logger.debug("Captured response: %s %s (%d)", response.request.method, response.url[:80], response.status)

            if self.max_responses and len(captured) >= self.max_responses:
                done_event.set()

        page.on('response', handle_response)
        try:
            if self.wait_ms > 0:
                try:
                    await asyncio.wait_for(done_event.wait(), timeout=self.wait_ms / 1000)
                except asyncio.TimeoutError:
                    pass
        finally:
            page.remove_listener('response', handle_response)

        # Keyed on `error`, which only the except branch writes. `body is None`
        # would be wrong: a JSON response whose whole payload is the literal
        # `null` parses to None and was read perfectly well.
        unreadable = sum(1 for entry in captured if 'error' in entry)

        return {
            "status": "success",
            "responses": captured,
            "count": len(captured),
            "unreadable_body_count": unreadable,
            "outcome": _response_outcome(
                count=len(captured),
                unreadable_bodies=unreadable,
                url_pattern=self.url_pattern.pattern,
                listened_ms=self.wait_ms,
            ),
        }
