# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
HTTP Session Module
Send multiple HTTP requests with persistent cookies and session state.
Useful for APIs that require login → action → logout flows.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from ....utils import SSRFError, validate_url_with_env_config
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup, Visibility

logger = logging.getLogger(__name__)


def _apply_auth(headers: Dict[str, Any], auth: Dict[str, Any]) -> None:
    """Apply authentication headers in-place."""
    import base64
    auth_type = auth.get('type', 'bearer')
    if auth_type == 'bearer':
        headers['Authorization'] = f'Bearer {auth.get("token", "")}'
    elif auth_type == 'basic':
        cred = base64.b64encode(f'{auth.get("username", "")}:{auth.get("password", "")}'.encode()).decode()
        headers['Authorization'] = f'Basic {cred}'
    elif auth_type == 'api_key':
        headers[auth.get('header_name', 'X-API-Key')] = auth.get('api_key', '')


async def _read_body(response, response_type: str) -> Any:
    """Read response body according to type."""
    if response_type == 'json':
        return await response.json()
    if response_type == 'text':
        return await response.text()
    ct = response.headers.get('Content-Type', '')
    if 'application/json' in ct:
        try:
            return await response.json()
        except Exception:
            return await response.text()
    return await response.text()


async def _execute_request(
    session,
    req: Dict[str, Any],
    index: int,
    auth: Optional[Dict[str, Any]],
    verify_ssl: bool,
) -> Dict[str, Any]:
    """Execute a single request within a session. Returns a result dict."""
    req_url = req.get('url', '')
    req_method = req.get('method', 'GET').upper()
    req_headers = dict(req.get('headers', {}))
    req_body = req.get('body')
    req_label = req.get('label', f'Request {index + 1}')

    try:
        validate_url_with_env_config(req_url)
    except SSRFError as e:
        return {'label': req_label, 'ok': False, 'error': str(e), 'error_code': 'SSRF_BLOCKED'}

    if auth:
        _apply_auth(req_headers, auth)

    kwargs: Dict[str, Any] = {
        'headers': req_headers,
        'ssl': verify_ssl if verify_ssl else False,
    }
    if req_body is not None and req_method in ('POST', 'PUT', 'PATCH'):
        if 'Content-Type' not in req_headers:
            req_headers['Content-Type'] = 'application/json'
        kwargs['json'] = req_body

    req_start = time.time()

    try:
        async with session.request(req_method, req_url, **kwargs) as response:
            req_duration = int((time.time() - req_start) * 1000)
            body_content = await _read_body(response, 'auto')
            ok = 200 <= response.status < 300
            logger.info(f"Session [{req_label}] {req_method} {req_url} -> {response.status} ({req_duration}ms)")
            return {
                'label': req_label, 'ok': ok,
                'status': response.status,
                'headers': dict(response.headers),
                'body': body_content,
                'url': str(response.url),
                'duration_ms': req_duration,
            }
    except asyncio.TimeoutError:
        req_duration = int((time.time() - req_start) * 1000)
        return {'label': req_label, 'ok': False, 'error': 'Timeout', 'error_code': 'TIMEOUT', 'duration_ms': req_duration}
    except Exception as e:
        req_duration = int((time.time() - req_start) * 1000)
        return {'label': req_label, 'ok': False, 'error': str(e), 'error_code': 'CLIENT_ERROR', 'duration_ms': req_duration}


@register_module(
    module_id='http.session',
    version='1.0.0',
    category='atomic',
    subcategory='http',
    tags=['http', 'session', 'cookie', 'login', 'api', 'persistent', 'atomic'],
    label='HTTP Session',
    label_key='modules.http.session.label',
    description='Send a sequence of HTTP requests with persistent cookies (login → action → logout)',
    description_key='modules.http.session.description',
    icon='Cookie',
    color='#EC4899',

    input_types=['object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],
    can_be_start=True,

    timeout_ms=120000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'filesystem.write'],

    params_schema=compose(
        field(
            'requests',
            type='array',
            label='Requests',
            label_key='modules.http.session.requests',
            description='Ordered list of HTTP requests to execute with shared cookies',
            required=True,
            items={
                'type': 'object',
                'properties': {
                    'label': {
                        'type': 'string',
                        'label': 'Label',
                        'description': 'Name for this step (e.g. "Login", "Get Data")',
                        'placeholder': 'Step name',
                    },
                    'url': {
                        'type': 'string',
                        'label': 'URL',
                        'description': 'Request URL',
                        'required': True,
                        'placeholder': 'https://api.example.com/login',
                    },
                    'method': {
                        'type': 'string',
                        'label': 'Method',
                        'default': 'GET',
                        'enum': ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
                    },
                    'headers': {
                        'type': 'object',
                        'label': 'Headers',
                        'default': {},
                    },
                    'body': {
                        'type': 'any',
                        'label': 'Body',
                        'description': 'Request body (JSON)',
                    },
                },
            },
            group=FieldGroup.BASIC,
        ),
        field(
            'auth',
            type='object',
            label='Authentication',
            label_key='schema.field.http_auth',
            description='Authentication applied to all requests in the session',
            properties={
                'type': {
                    'type': 'string',
                    'description': 'Authentication type',
                    'enum': ['bearer', 'basic', 'api_key'],
                    'default': 'bearer',
                },
                'token': {'type': 'string', 'description': 'Bearer token', 'format': 'password'},
                'username': {'type': 'string', 'description': 'Basic auth username'},
                'password': {'type': 'string', 'description': 'Basic auth password', 'format': 'password'},
                'header_name': {'type': 'string', 'description': 'API key header name', 'default': 'X-API-Key'},
                'api_key': {'type': 'string', 'description': 'API key value', 'format': 'password'},
            },
            ui={'widget': 'auth_config'},
            group=FieldGroup.CONNECTION,
        ),
        field(
            'stop_on_error',
            type='boolean',
            label='Stop on Error',
            label_key='modules.http.session.stop_on_error',
            description='Stop executing remaining requests if one fails (non-2xx)',
            default=True,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'timeout',
            type='number',
            label='Timeout per Request (seconds)',
            label_key='schema.field.timeout_s',
            description='Maximum time per individual request',
            default=30,
            min=1,
            max=120,
            step=1,
            ui={'unit': 's'},
            visibility=Visibility.EXPERT,
            group=FieldGroup.ADVANCED,
        ),
        field(
            'verify_ssl',
            type='boolean',
            label='Verify SSL',
            label_key='schema.field.verify_ssl',
            description='Verify SSL certificates',
            default=True,
            visibility=Visibility.EXPERT,
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether all requests succeeded',
            'description_key': 'modules.http.session.output.ok.description',
        },
        'results': {
            'type': 'array',
            'description': 'Results from each request in order',
            'description_key': 'modules.http.session.output.results.description',
        },
        'cookies': {
            'type': 'object',
            'description': 'Final session cookies as key-value pairs',
            'description_key': 'modules.http.session.output.cookies.description',
        },
        'duration_ms': {
            'type': 'number',
            'description': 'Total duration in milliseconds',
            'description_key': 'modules.http.session.output.duration_ms.description',
        },
    },
    examples=[
        {
            'title': 'Login and fetch data',
            'title_key': 'modules.http.session.examples.login.title',
            'params': {
                'requests': [
                    {
                        'label': 'Login',
                        'url': 'https://example.com/api/login',
                        'method': 'POST',
                        'body': {'username': '${env.USER}', 'password': '${env.PASS}'},
                    },
                    {
                        'label': 'Get Profile',
                        'url': 'https://example.com/api/profile',
                        'method': 'GET',
                    },
                ],
                'stop_on_error': True,
            },
        },
        {
            'title': 'CSRF token flow',
            'title_key': 'modules.http.session.examples.csrf.title',
            'params': {
                'requests': [
                    {
                        'label': 'Get CSRF Token',
                        'url': 'https://example.com/csrf-token',
                        'method': 'GET',
                    },
                    {
                        'label': 'Submit Form',
                        'url': 'https://example.com/api/submit',
                        'method': 'POST',
                        'body': {'data': 'value'},
                    },
                ],
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def http_session(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a sequence of HTTP requests with persistent cookies."""
    try:
        import aiohttp
    except ImportError as exc:
        raise ImportError("aiohttp is required for http.session. Install with: pip install aiohttp") from exc

    params = context['params']
    requests_list = params.get('requests', [])
    auth = params.get('auth')
    stop_on_error = params.get('stop_on_error', True)
    timeout_seconds = params.get('timeout', 30)
    verify_ssl = params.get('verify_ssl', True)

    if not requests_list:
        return {'ok': False, 'error': 'No requests provided', 'error_code': 'NO_REQUESTS',
                'results': [], 'cookies': {}, 'duration_ms': 0}

    results: List[Dict[str, Any]] = []
    start_time = time.time()
    all_ok = True

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    cookie_jar = aiohttp.CookieJar()

    try:
        async with aiohttp.ClientSession(timeout=timeout, cookie_jar=cookie_jar) as session:
            for i, req in enumerate(requests_list):
                result = await _execute_request(session, req, i, auth, verify_ssl)
                results.append(result)
                if not result['ok']:
                    all_ok = False
                    if stop_on_error:
                        break

            cookies = {cookie.key: cookie.value for cookie in cookie_jar}

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Session error: {e}")
        return {'ok': False, 'error': str(e), 'error_code': 'SESSION_ERROR',
                'results': results, 'cookies': {}, 'duration_ms': duration_ms}

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(f"Session complete: {len(results)} requests, all_ok={all_ok} ({duration_ms}ms)")
    return {'ok': all_ok, 'results': results, 'cookies': cookies, 'duration_ms': duration_ms}
