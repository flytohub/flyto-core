# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
HTTP GET Request Module

Simplified GET request for API calls.
"""

import logging
from typing import Any, Dict

from ...registry import register_module
from ...errors import ValidationError, NetworkError, ModuleError
from ....utils import validate_url_with_env_config, SSRFError

logger = logging.getLogger(__name__)


def _append_query_params(url: str, query: dict) -> str:
    """Append query parameters to URL."""
    from urllib.parse import urlencode, urlparse, urlunparse

    parsed = urlparse(url)
    separator = '&' if parsed.query else ''
    new_query = parsed.query + separator + urlencode(query)
    return urlunparse(parsed._replace(query=new_query))


async def _parse_response_body(response) -> Any:
    """Parse response body, attempting JSON for JSON content types."""
    content_type = response.headers.get('Content-Type', '')
    if 'application/json' in content_type:
        try:
            return await response.json()
        except Exception:
            return await response.text()
    return await response.text()


@register_module(
    module_id='http.get',
    version='1.0.0',
    category='http',
    subcategory='client',
    tags=['api', 'http', 'get', 'request', 'atomic', 'ssrf_protected'],
    label='HTTP GET',
    label_key='modules.http.get.label',
    description='Send HTTP GET request to an API endpoint',
    description_key='modules.http.get.description',
    icon='Download',
    color='#3B82F6',

    input_types=['string'],
    output_types=['object', 'json'],
    can_receive_from=['*'],
    can_connect_to=['*'],

    timeout_ms=60000,
    required_permissions=["network.access"],
    retryable=True,
    max_retries=3,
    requires_credentials=True,
    credential_keys=['API_KEY'],

    params_schema={
        'url': {
            'type': 'string',
            'label': 'URL',
            'required': True,
            'placeholder': 'https://api.example.com/data',
            'description': 'Target URL',
        },
        'headers': {
            'type': 'object',
            'label': 'Headers',
            'default': {},
            'description': 'HTTP request headers',
        },
        'query': {
            'type': 'object',
            'label': 'Query Parameters',
            'default': {},
            'description': 'Query string',
        },
        'timeout': {
            'type': 'number',
            'label': 'Timeout (seconds)',
            'default': 30,
            'description': 'Maximum time to wait in milliseconds',
        },
    },
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether the operation succeeded',
               'description_key': 'modules.http.get.output.ok.description'},
        'status': {'type': 'number', 'description': 'HTTP status code',
                   'description_key': 'modules.http.get.output.status.description'},
        'body': {'type': 'any', 'description': 'Response body content',
                 'description_key': 'modules.http.get.output.body.description'},
        'headers': {'type': 'object', 'description': 'Response headers',
                    'description_key': 'modules.http.get.output.headers.description'}
    }
)
async def http_get(context: Dict[str, Any]) -> Dict[str, Any]:
    """Send HTTP GET request."""
    try:
        import aiohttp
    except ImportError:
        raise ModuleError("aiohttp required. Install: pip install aiohttp")

    params = context['params']
    url = params.get('url')
    if not url:
        raise ValidationError("Missing required parameter: url", field="url")

    headers = params.get('headers', {})
    query = params.get('query', {})
    timeout_s = params.get('timeout', 30)

    try:
        validate_url_with_env_config(url)
    except SSRFError as e:
        logger.warning(f"SSRF protection blocked GET to: {url}")
        raise NetworkError(str(e), url=url, status_code=0)

    if query:
        url = _append_query_params(url, query)

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                body = await _parse_response_body(response)
                if 200 <= response.status < 300:
                    return {'ok': True, 'data': {'status': response.status, 'body': body, 'headers': dict(response.headers)}}
                raise NetworkError(f"HTTP {response.status} error", url=url, status_code=response.status)
    except NetworkError:
        raise
    except Exception as e:
        logger.error(f"HTTP GET failed: {e}")
        raise NetworkError(str(e), url=url)
