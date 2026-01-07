"""
Browser Network Module

Monitor and intercept network requests.
"""
from typing import Any, Dict, List, Optional
import asyncio
import re
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field


@register_module(
    module_id='browser.network',
    version='1.0.0',
    category='browser',
    tags=['browser', 'network', 'request', 'response', 'intercept'],
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
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    params_schema=compose(
        field(
            'action',
            type='string',
            label='Action',
            label_key='modules.browser.network.params.action.label',
            description='Network action to perform',
            required=True,
            enum=['monitor', 'block', 'intercept'],
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
        ),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)'},
        'requests': {'type': 'array', 'description': 'Captured network requests'},
        'blocked_count': {'type': 'number', 'description': 'The blocked count'}
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
    license='MIT'
)
class BrowserNetworkModule(BaseModule):
    """Network Monitor Module"""

    module_name = "Network Monitor"
    module_description = "Monitor and intercept network requests"
    required_permission = "browser.interact"

    def validate_params(self):
        if 'action' not in self.params:
            raise ValueError("Missing required parameter: action")

        self.action = self.params['action']
        if self.action not in ['monitor', 'block', 'intercept']:
            raise ValueError(f"Invalid action: {self.action}")

        self.url_pattern = self.params.get('url_pattern')
        self.resource_type = self.params.get('resource_type')
        self.timeout = self.params.get('timeout', 30000)
        self.mock_response = self.params.get('mock_response')

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

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page
        requests: List[Dict[str, Any]] = []
        blocked_count = 0

        if self.action == 'monitor':
            def handle_request(request):
                if self._matches_filter(request):
                    requests.append({
                        'url': request.url,
                        'method': request.method,
                        'resource_type': request.resource_type,
                        'headers': dict(request.headers)
                    })

            def handle_response(response):
                # Find matching request and add response info
                for req in requests:
                    if req['url'] == response.url:
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
                "count": len(requests)
            }

        elif self.action == 'block':
            async def handle_route(route):
                nonlocal blocked_count
                request = route.request
                if self._matches_filter(request):
                    blocked_count += 1
                    requests.append({
                        'url': request.url,
                        'blocked': True
                    })
                    await route.abort()
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
                "blocked_count": blocked_count
            }

        elif self.action == 'intercept':
            async def handle_route(route):
                request = route.request
                if self._matches_filter(request):
                    requests.append({
                        'url': request.url,
                        'intercepted': True
                    })
                    await route.fulfill(
                        status=self.mock_response.get('status', 200),
                        content_type=self.mock_response.get('content_type', 'application/json'),
                        body=self.mock_response.get('body', '{}')
                    )
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
                "intercepted_count": len(requests)
            }
