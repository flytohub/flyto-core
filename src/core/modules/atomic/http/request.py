"""
HTTP Request Module
Send HTTP requests with full control over method, headers, body, and auth
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Union

from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_url_with_env_config, SSRFError


logger = logging.getLogger(__name__)


@register_module(
    module_id='http.request',
    version='1.0.0',
    category='atomic',
    subcategory='http',
    tags=['http', 'request', 'api', 'rest', 'client', 'atomic'],
    label='HTTP Request',
    label_key='modules.http.request.label',
    description='Send HTTP request and receive response',
    description_key='modules.http.request.description',
    icon='Globe',
    color='#3B82F6',

    # Connection types
    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['test.*', 'data.*', 'file.*'],
    can_receive_from=['start', 'flow.*'],

    # Execution settings
    timeout=60,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=True,  # May contain auth tokens
    required_permissions=['network.http'],

    # Schema-driven params
    params_schema=compose(
        presets.URL(required=True, placeholder='https://api.example.com/endpoint'),
        presets.HTTP_METHOD(default='GET'),
        presets.HEADERS(),
        presets.REQUEST_BODY(),
        presets.QUERY_PARAMS(),
        presets.CONTENT_TYPE(default='application/json'),
        presets.HTTP_AUTH(),
        presets.TIMEOUT_S(default=30),
        presets.FOLLOW_REDIRECTS(default=True),
        presets.VERIFY_SSL(default=True),
        presets.RESPONSE_TYPE(default='auto'),
    ),
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether request was successful (2xx status)'
        ,
                'description_key': 'modules.http.request.output.ok.description'},
        'status': {
            'type': 'number',
            'description': 'HTTP status code'
        ,
                'description_key': 'modules.http.request.output.status.description'},
        'status_text': {
            'type': 'string',
            'description': 'HTTP status text'
        ,
                'description_key': 'modules.http.request.output.status_text.description'},
        'headers': {
            'type': 'object',
            'description': 'Response headers'
        ,
                'description_key': 'modules.http.request.output.headers.description'},
        'body': {
            'type': 'any',
            'description': 'Response body (parsed JSON or text)'
        ,
                'description_key': 'modules.http.request.output.body.description'},
        'url': {
            'type': 'string',
            'description': 'Final URL (after redirects)'
        ,
                'description_key': 'modules.http.request.output.url.description'},
        'duration_ms': {
            'type': 'number',
            'description': 'Request duration in milliseconds'
        ,
                'description_key': 'modules.http.request.output.duration_ms.description'},
        'content_type': {
            'type': 'string',
            'description': 'Response Content-Type'
        ,
                'description_key': 'modules.http.request.output.content_type.description'},
        'content_length': {
            'type': 'number',
            'description': 'Response body size in bytes'
        ,
                'description_key': 'modules.http.request.output.content_length.description'}
    },
    examples=[
        {
            'title': 'Simple GET request',
            'title_key': 'modules.http.request.examples.get.title',
            'params': {
                'url': 'https://api.example.com/users',
                'method': 'GET'
            }
        },
        {
            'title': 'POST with JSON body',
            'title_key': 'modules.http.request.examples.post.title',
            'params': {
                'url': 'https://api.example.com/users',
                'method': 'POST',
                'body': {'name': 'John', 'email': 'john@example.com'}
            }
        },
        {
            'title': 'Request with Bearer auth',
            'title_key': 'modules.http.request.examples.auth.title',
            'params': {
                'url': 'https://api.example.com/protected',
                'method': 'GET',
                'auth': {'type': 'bearer', 'token': '${env.API_TOKEN}'}
            }
        },
        {
            'title': 'Request with query params',
            'title_key': 'modules.http.request.examples.query.title',
            'params': {
                'url': 'https://api.example.com/search',
                'method': 'GET',
                'query': {'q': 'flyto', 'limit': 10}
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def http_request(context: Dict[str, Any]) -> Dict[str, Any]:
    """Send HTTP request and return response"""
    try:
        import aiohttp
    except ImportError:
        raise ImportError(
            "aiohttp is required for http.request. "
            "Install with: pip install aiohttp"
        )

    import base64
    from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

    params = context['params']
    url = params['url']
    method = params.get('method', 'GET').upper()
    headers = dict(params.get('headers', {}))
    body = params.get('body')
    query = params.get('query', {})
    content_type = params.get('content_type', 'application/json')
    auth = params.get('auth')
    timeout_seconds = params.get('timeout', 30)
    follow_redirects = params.get('follow_redirects', True)
    verify_ssl = params.get('verify_ssl', True)
    response_type = params.get('response_type', 'auto')

    # SECURITY: Validate URL against SSRF attacks
    try:
        validate_url_with_env_config(url)
    except SSRFError as e:
        logger.warning(f"SSRF protection blocked request to: {url}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'SSRF_BLOCKED',
            'url': url,
            'duration_ms': 0
        }

    # Build URL with query params
    if query:
        parsed = urlparse(url)
        existing_query = parse_qs(parsed.query)
        existing_query.update({k: [str(v)] for k, v in query.items()})
        new_query = urlencode(existing_query, doseq=True)
        url = urlunparse(parsed._replace(query=new_query))

    # Set Content-Type header
    if body and 'Content-Type' not in headers:
        headers['Content-Type'] = content_type

    # Handle authentication
    if auth:
        auth_type = auth.get('type', 'bearer')
        if auth_type == 'bearer':
            token = auth.get('token', '')
            headers['Authorization'] = f'Bearer {token}'
        elif auth_type == 'basic':
            username = auth.get('username', '')
            password = auth.get('password', '')
            credentials = base64.b64encode(
                f'{username}:{password}'.encode()
            ).decode()
            headers['Authorization'] = f'Basic {credentials}'
        elif auth_type == 'api_key':
            header_name = auth.get('header_name', 'X-API-Key')
            api_key = auth.get('api_key', '')
            headers[header_name] = api_key

    # Prepare request body
    request_kwargs: Dict[str, Any] = {
        'headers': headers,
        'allow_redirects': follow_redirects,
        'ssl': verify_ssl if verify_ssl else False
    }

    if body is not None and method in ('POST', 'PUT', 'PATCH'):
        if content_type == 'application/json':
            request_kwargs['json'] = body
        elif content_type == 'application/x-www-form-urlencoded':
            request_kwargs['data'] = body
        else:
            request_kwargs['data'] = str(body) if not isinstance(body, (bytes, str)) else body

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    start_time = time.time()

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, url, **request_kwargs) as response:
                duration_ms = int((time.time() - start_time) * 1000)

                status = response.status
                status_text = response.reason or ''
                response_headers = dict(response.headers)
                final_url = str(response.url)
                response_content_type = response.headers.get('Content-Type', '')
                content_length = response.headers.get('Content-Length')

                # Parse response body
                if response_type == 'binary':
                    body_content = await response.read()
                elif response_type == 'json':
                    body_content = await response.json()
                elif response_type == 'text':
                    body_content = await response.text()
                else:  # auto
                    if 'application/json' in response_content_type:
                        try:
                            body_content = await response.json()
                        except Exception:
                            body_content = await response.text()
                    else:
                        body_content = await response.text()

                ok = 200 <= status < 300

                logger.info(
                    f"HTTP {method} {url} -> {status} "
                    f"({duration_ms}ms)"
                )

                return {
                    'ok': ok,
                    'status': status,
                    'status_text': status_text,
                    'headers': response_headers,
                    'body': body_content,
                    'url': final_url,
                    'duration_ms': duration_ms,
                    'content_type': response_content_type,
                    'content_length': int(content_length) if content_length else len(
                        body_content if isinstance(body_content, (str, bytes)) else str(body_content)
                    )
                }

    except asyncio.TimeoutError:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"HTTP request timeout: {method} {url}")
        return {
            'ok': False,
            'error': f'Request timed out after {timeout_seconds} seconds',
            'error_code': 'TIMEOUT',
            'url': url,
            'duration_ms': duration_ms
        }

    except aiohttp.ClientError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"HTTP client error: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'CLIENT_ERROR',
            'url': url,
            'duration_ms': duration_ms
        }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"HTTP request failed: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'REQUEST_ERROR',
            'url': url,
            'duration_ms': duration_ms
        }
