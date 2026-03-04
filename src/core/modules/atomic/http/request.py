# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
HTTP Request Module
Send HTTP requests with full control over method, headers, body, and auth
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Union

from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import Visibility, FieldGroup
from ....utils import validate_url_with_env_config, SSRFError


logger = logging.getLogger(__name__)


# Retry-After header status codes
_RETRY_STATUS_CODES = {429, 503}


def _build_url_with_query(url: str, query: dict) -> str:
    """Merge query params into the URL."""
    from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

    parsed = urlparse(url)
    existing_query = parse_qs(parsed.query)
    existing_query.update({k: [str(v)] for k, v in query.items()})
    new_query = urlencode(existing_query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _apply_auth(headers: Dict[str, str], auth: Dict[str, Any]) -> None:
    """Apply authentication headers in-place."""
    import base64

    auth_type = auth.get('type', 'bearer')
    if auth_type == 'bearer':
        headers['Authorization'] = f'Bearer {auth.get("token", "")}'
    elif auth_type == 'basic':
        credentials = base64.b64encode(
            '{}:{}'.format(auth.get('username', ''), auth.get('password', '')).encode()
        ).decode()
        headers['Authorization'] = f'Basic {credentials}'
    elif auth_type == 'api_key':
        headers[auth.get('header_name', 'X-API-Key')] = auth.get('api_key', '')


def _build_request_kwargs(
    headers: dict, body: Any, method: str,
    content_type: str, follow_redirects: bool, verify_ssl: bool,
) -> Dict[str, Any]:
    """Build kwargs dict for aiohttp session.request()."""
    kwargs: Dict[str, Any] = {
        'headers': headers,
        'allow_redirects': follow_redirects,
        'ssl': verify_ssl if verify_ssl else False,
    }
    if body is not None and method in ('POST', 'PUT', 'PATCH'):
        if content_type == 'application/json':
            kwargs['json'] = body
        elif content_type == 'application/x-www-form-urlencoded':
            kwargs['data'] = body
        else:
            kwargs['data'] = str(body) if not isinstance(body, (bytes, str)) else body
    return kwargs


async def _read_response_body(response, response_type: str) -> Any:
    """Read response body according to the requested type."""
    if response_type == 'binary':
        return await response.read()
    if response_type == 'json':
        return await response.json()
    if response_type == 'text':
        return await response.text()
    # auto
    ct = response.headers.get('Content-Type', '')
    if 'application/json' in ct:
        try:
            return await response.json()
        except Exception:
            return await response.text()
    return await response.text()


def _compute_content_length(content_length_header: Optional[str], body_content: Any) -> int:
    """Compute content length from header or body."""
    if content_length_header:
        return int(content_length_header)
    return len(body_content if isinstance(body_content, (str, bytes)) else str(body_content))


def _error_result(error_msg: str, error_code: str, url: str, duration_ms: int) -> Dict[str, Any]:
    """Build a standard error result dict."""
    return {'ok': False, 'error': error_msg, 'error_code': error_code, 'url': url, 'duration_ms': duration_ms}


@register_module(
    module_id='http.request',
    version='1.0.0',
    category='atomic',
    subcategory='http',
    tags=['http', 'request', 'api', 'rest', 'client', 'atomic', 'ssrf_protected'],
    label='HTTP Request',
    label_key='modules.http.request.label',
    description='Send HTTP request and receive response',
    description_key='modules.http.request.description',
    icon='Globe',
    color='#3B82F6',

    # Connection types
    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],
    can_be_start=True,

    # Execution settings
    timeout_ms=60000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=True,  # May contain auth tokens
    required_permissions=['filesystem.read', 'filesystem.write'],

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
        field(
            'retry_count',
            type='number',
            label='Retry Count',
            label_key='modules.http.request.retry_count',
            description='Number of retries on failure or 429/503 status',
            default=0,
            min=0,
            max=10,
            step=1,
            visibility=Visibility.EXPERT,
            group=FieldGroup.ADVANCED,
        ),
        field(
            'retry_backoff',
            type='string',
            label='Retry Backoff',
            label_key='modules.http.request.retry_backoff',
            description='Backoff strategy between retries',
            default='exponential',
            options=[
                {'value': 'none', 'label': 'No delay'},
                {'value': 'linear', 'label': 'Linear (1s, 2s, 3s...)'},
                {'value': 'exponential', 'label': 'Exponential (1s, 2s, 4s...)'},
            ],
            showIf={'retry_count': {'$in': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}},
            visibility=Visibility.EXPERT,
            group=FieldGroup.ADVANCED,
        ),
        field(
            'retry_delay',
            type='number',
            label='Base Retry Delay (seconds)',
            label_key='modules.http.request.retry_delay',
            description='Initial delay between retries in seconds',
            default=1,
            min=0.1,
            max=30,
            step=0.1,
            ui={'unit': 's'},
            showIf={'retry_count': {'$in': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}},
            visibility=Visibility.EXPERT,
            group=FieldGroup.ADVANCED,
        ),
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
    author='Flyto Team',
    license='MIT'
)
async def http_request(context: Dict[str, Any]) -> Dict[str, Any]:
    """Send HTTP request and return response"""
    try:
        import aiohttp
    except ImportError:
        raise ImportError("aiohttp is required for http.request. Install with: pip install aiohttp")

    params = context['params']
    url = params['url']
    method = params.get('method', 'GET').upper()
    headers = dict(params.get('headers', {}))
    body = params.get('body')
    query = params.get('query', {})
    content_type = params.get('content_type', 'application/json')
    auth = params.get('auth')
    timeout_seconds = params.get('timeout', 30)
    response_type = params.get('response_type', 'auto')
    retry_count = int(params.get('retry_count', 0))
    retry_backoff = params.get('retry_backoff', 'exponential')
    retry_delay = float(params.get('retry_delay', 1))

    # Detect unresolved template placeholders in URL
    import re
    unresolved = re.findall(r'\$\{[^}]+\}|\{\{[^}]+\}\}', url)
    if unresolved:
        placeholders = ', '.join(unresolved)
        return _error_result(
            f"URL contains unresolved variables: {placeholders}. "
            f"Use ${{variable_name}} syntax and ensure the variable is defined.",
            'UNRESOLVED_VARIABLE', url, 0)

    try:
        validate_url_with_env_config(url)
    except SSRFError as e:
        logger.warning(f"SSRF protection blocked request to: {url}")
        return _error_result(str(e), 'SSRF_BLOCKED', url, 0)

    if query:
        url = _build_url_with_query(url, query)
    if body and 'Content-Type' not in headers:
        headers['Content-Type'] = content_type
    if auth:
        _apply_auth(headers, auth)

    request_kwargs = _build_request_kwargs(
        headers, body, method, content_type,
        params.get('follow_redirects', True), params.get('verify_ssl', True),
    )
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    start_time = time.time()
    last_error = None
    max_attempts = 1 + retry_count

    for attempt in range(max_attempts):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, **request_kwargs) as response:
                    duration_ms = int((time.time() - start_time) * 1000)
                    body_content = await _read_response_body(response, response_type)

                    # Retry on 429/503 if retries remaining
                    if response.status in _RETRY_STATUS_CODES and attempt < max_attempts - 1:
                        # Respect Retry-After header if present
                        retry_after = response.headers.get('Retry-After')
                        if retry_after and retry_after.isdigit():
                            wait = float(retry_after)
                        else:
                            wait = _compute_backoff(attempt, retry_delay, retry_backoff)
                        logger.warning(f"HTTP {method} {url} -> {response.status}, retry {attempt + 1}/{retry_count} in {wait:.1f}s")
                        await asyncio.sleep(wait)
                        continue

                    logger.info(f"HTTP {method} {url} -> {response.status} ({duration_ms}ms)")
                    is_ok = 200 <= response.status < 300
                    result = {
                        'ok': is_ok,
                        'status': response.status,
                        'status_text': response.reason or '',
                        'headers': dict(response.headers),
                        'body': body_content,
                        'url': str(response.url),
                        'duration_ms': duration_ms,
                        'content_type': response.headers.get('Content-Type', ''),
                        'content_length': _compute_content_length(response.headers.get('Content-Length'), body_content),
                    }
                    if not is_ok:
                        result['error'] = f"HTTP {response.status} {response.reason or ''}"
                        result['error_code'] = f"HTTP_{response.status}"
                    if attempt > 0:
                        result['retries'] = attempt
                    return result

        except asyncio.TimeoutError:
            last_error = ('TIMEOUT', f'Request timed out after {timeout_seconds} seconds')
        except aiohttp.ClientError as e:
            last_error = ('CLIENT_ERROR', str(e))
        except Exception as e:
            last_error = ('REQUEST_ERROR', str(e))

        # Retry on exception if retries remaining
        if attempt < max_attempts - 1:
            wait = _compute_backoff(attempt, retry_delay, retry_backoff)
            logger.warning(f"HTTP {method} {url} failed ({last_error[0]}), retry {attempt + 1}/{retry_count} in {wait:.1f}s")
            await asyncio.sleep(wait)
        else:
            duration_ms = int((time.time() - start_time) * 1000)
            error_code, error_msg = last_error
            logger.error(f"HTTP {method} {url} failed after {attempt + 1} attempts: {error_msg}")
            result = _error_result(error_msg, error_code, url, duration_ms)
            if attempt > 0:
                result['retries'] = attempt
            return result

    # Should not reach here, but just in case
    duration_ms = int((time.time() - start_time) * 1000)
    return _error_result('Unexpected retry loop exit', 'REQUEST_ERROR', url, duration_ms)


def _compute_backoff(attempt: int, base_delay: float, strategy: str) -> float:
    """Compute retry delay based on backoff strategy."""
    if strategy == 'none':
        return 0
    elif strategy == 'linear':
        return base_delay * (attempt + 1)
    else:  # exponential
        return base_delay * (2 ** attempt)
