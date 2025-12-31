"""
HTTP Request Modules

Generic HTTP GET and POST request modules.
"""

from typing import Any

import aiohttp

from ....base import BaseModule
from ....registry import register_module
from ....schema import compose, presets


@register_module(
    module_id='core.api.http_get',
    version='1.0.0',
    category='api',
    subcategory='api',
    tags=['api', 'http', 'request', 'get'],
    label='HTTP GET Request',
    label_key='modules.api.http_get.label',
    description='Send HTTP GET request to any URL',
    description_key='modules.api.http_get.description',
    icon='Globe',
    color='#3B82F6',
    input_types=[],
    output_types=['json', 'text', 'api_response'],
    can_connect_to=['data.*', 'notification.*', 'file.*'],

    # Schema-driven params
    params_schema=compose(
        presets.URL(required=True, placeholder='https://api.example.com/data'),
        presets.HEADERS(),
        presets.QUERY_PARAMS(key='params'),
        presets.TIMEOUT_S(default=30),
    ),
    output_schema={
        'status_code': {'type': 'number'},
        'headers': {'type': 'object'},
        'body': {'type': 'string'},
        'json': {'type': 'object', 'optional': True}
    },
    examples=[{
        'title': 'Fetch API data',
        'params': {
            'url': 'https://api.github.com/users/octocat'
        }
    }],
    author='Flyto2 Team',
    license='MIT'
)
class HTTPGetModule(BaseModule):
    """Send HTTP GET request"""

    module_name = "HTTP GET Request"
    module_description = "Send HTTP GET request to any URL"

    def validate_params(self):
        if 'url' not in self.params:
            raise ValueError("Missing required parameter: url")

    async def execute(self) -> Any:
        url = self.params.get('url')
        headers = self.params.get('headers', {})
        params = self.params.get('params', {})
        timeout = self.params.get('timeout', 30)

        if not url:
            raise ValueError("URL is required")

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                status_code = response.status
                response_headers = dict(response.headers)
                body = await response.text()

                result = {
                    'status_code': status_code,
                    'headers': response_headers,
                    'body': body
                }

                if 'application/json' in response_headers.get('Content-Type', ''):
                    try:
                        result['json'] = await response.json()
                    except Exception:
                        pass

                return result


@register_module(
    module_id='core.api.http_post',
    version='1.0.0',
    category='api',
    subcategory='api',
    tags=['api', 'http', 'request', 'post'],
    label='HTTP POST Request',
    label_key='modules.api.http_post.label',
    description='Send HTTP POST request to any URL',
    description_key='modules.api.http_post.description',
    icon='Send',
    color='#3B82F6',
    input_types=['json', 'text', 'any'],
    output_types=['json', 'text', 'api_response'],
    can_receive_from=['data.*'],
    can_connect_to=['data.*', 'notification.*', 'file.*'],

    # Schema-driven params
    params_schema=compose(
        presets.URL(required=True, placeholder='https://api.example.com/data'),
        presets.HEADERS(),
        presets.TEXT(key='body', label='Body', label_key='schema.field.body', multiline=True),
        presets.REQUEST_BODY(key='json'),
        presets.TIMEOUT_S(default=30),
    ),
    output_schema={
        'status_code': {'type': 'number'},
        'headers': {'type': 'object'},
        'body': {'type': 'string'},
        'json': {'type': 'object', 'optional': True}
    },
    examples=[{
        'title': 'Post JSON data',
        'params': {
            'url': 'https://api.example.com/users',
            'json': {'name': 'John', 'email': 'john@example.com'}
        }
    }],
    author='Flyto2 Team',
    license='MIT'
)
class HTTPPostModule(BaseModule):
    """Send HTTP POST request"""

    module_name = "HTTP POST Request"
    module_description = "Send HTTP POST request to any URL"

    def validate_params(self):
        if 'url' not in self.params:
            raise ValueError("Missing required parameter: url")

    async def execute(self) -> Any:
        url = self.params.get('url')
        headers = self.params.get('headers', {})
        body = self.params.get('body')
        json_data = self.params.get('json')
        timeout = self.params.get('timeout', 30)

        if not url:
            raise ValueError("URL is required")

        kwargs = {
            'headers': headers,
            'timeout': aiohttp.ClientTimeout(total=timeout)
        }

        if json_data:
            kwargs['json'] = json_data
        elif body:
            kwargs['data'] = body

        async with aiohttp.ClientSession() as session:
            async with session.post(url, **kwargs) as response:
                status_code = response.status
                response_headers = dict(response.headers)
                response_body = await response.text()

                result = {
                    'status_code': status_code,
                    'headers': response_headers,
                    'body': response_body
                }

                if 'application/json' in response_headers.get('Content-Type', ''):
                    try:
                        result['json'] = await response.json()
                    except Exception:
                        pass

                return result
