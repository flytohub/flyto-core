# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Response Module — Capture network response bodies

Listens for XHR/fetch responses matching a URL pattern,
captures the response body (JSON, text, binary), and returns structured data.

Use case: Extract data from API calls made by the page (dashboards, SPAs, feeds).
"""
import asyncio
import json
import logging
import re
from typing import Any, Dict, List
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup

logger = logging.getLogger(__name__)


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
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],
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
    },
    examples=[
        {'name': 'Capture JSON API calls', 'params': {'url_pattern': '/api/', 'wait_ms': 5000}},
        {'name': 'Capture GraphQL responses', 'params': {'url_pattern': 'graphql', 'wait_ms': 3000}},
    ],
    author='Flyto Team', license='MIT', timeout_ms=65000,
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

        return {
            "status": "success",
            "responses": captured,
            "count": len(captured),
        }
