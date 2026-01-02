"""
HTTP GET Request Module

Simplified GET request for API calls.
"""

import logging
from typing import Any, Dict

from ...registry import register_module

logger = logging.getLogger(__name__)


@register_module(
    module_id='api.http_get',
    version='1.0.0',
    category='atomic',
    subcategory='api',
    tags=['api', 'http', 'get', 'request', 'atomic'],
    label='HTTP GET',
    description='Send HTTP GET request to an API endpoint',
    icon='Download',
    color='#3B82F6',

    input_types=['string'],
    output_types=['object', 'json'],
    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'notification.*', 'file.*', 'flow.*'],

    timeout=60,
    retryable=True,
    max_retries=3,

    params_schema={
        'url': {
            'type': 'string',
            'label': 'URL',
            'required': True,
            'placeholder': 'https://api.example.com/data'
        },
        'headers': {
            'type': 'object',
            'label': 'Headers',
            'default': {}
        },
        'query': {
            'type': 'object',
            'label': 'Query Parameters',
            'default': {}
        },
        'timeout': {
            'type': 'number',
            'label': 'Timeout (seconds)',
            'default': 30
        }
    },
    output_schema={
        'ok': {'type': 'boolean'},
        'status': {'type': 'number'},
        'body': {'type': 'any'},
        'headers': {'type': 'object'}
    }
)
async def api_http_get(context: Dict[str, Any]) -> Dict[str, Any]:
    """Send HTTP GET request"""
    try:
        import aiohttp
    except ImportError:
        return {
            'ok': False,
            'error': 'aiohttp required. Install: pip install aiohttp'
        }

    from urllib.parse import urlencode, urlparse, urlunparse

    params = context['params']
    url = params['url']
    headers = params.get('headers', {})
    query = params.get('query', {})
    timeout_s = params.get('timeout', 30)

    # Add query params to URL
    if query:
        parsed = urlparse(url)
        separator = '&' if parsed.query else ''
        new_query = parsed.query + separator + urlencode(query)
        url = urlunparse(parsed._replace(query=new_query))

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                content_type = response.headers.get('Content-Type', '')

                if 'application/json' in content_type:
                    try:
                        body = await response.json()
                    except Exception:
                        body = await response.text()
                else:
                    body = await response.text()

                return {
                    'ok': 200 <= response.status < 300,
                    'status': response.status,
                    'body': body,
                    'headers': dict(response.headers)
                }

    except Exception as e:
        logger.error(f"HTTP GET failed: {e}")
        return {
            'ok': False,
            'error': str(e),
            'status': 0
        }
