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
from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import (
    guarded_client_session,
    validate_url_with_env_config,
    SSRFError,
    ssrf_protection_enabled,
    guarded_aiohttp_request,
)


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
    """Compute content length from header or body.

    The header is peer-controlled on any URL a workflow does not own, and a
    malformed one is not a number. `int(header)` used to run unguarded here, so
    `Content-Length: not-a-number` raised ValueError out of a 200 response,
    which the broad `except Exception` in the request loop turned into a
    REQUEST_ERROR -- a successful request reported as a step failure, and with
    `retry_count` set, re-sent N times. A header that does not parse is treated
    exactly as an absent one: fall through to measuring the body. The
    try/except is narrowed to ValueError/TypeError so nothing else is swallowed.
    """
    if content_length_header:
        try:
            return int(content_length_header)
        except (ValueError, TypeError):
            pass
    return len(body_content if isinstance(body_content, (str, bytes)) else str(body_content))


def _observed_effects(response, body_content: Any) -> List[Dict[str, Any]]:
    """The two things this request actually measured, each with its provenance.

    Both entries are deliberately narrower than the module's own output fields,
    because the output fields mix measurement with relay and the ladder must not.

      * `status` / `reason` are read straight off the response object
        (`response.status`, `response.reason`). They are a real answer from the
        other side: a server received the request, processed it far enough to
        choose a status line, and sent one back. That is the strongest thing
        this module knows, and it is why the rung is ACCEPTED rather than
        DISPATCHED.

      * `bytes_received` is `len(body_content)` and ONLY when `body_content` is
        actually bytes -- i.e. `response_type='binary'`, the one path where
        `_read_response_body` hands back the wire payload untouched. For 'text'
        the value has already been decoded to str, so its length is characters
        and not bytes; for 'json' it is a parsed object with no size at all. In
        both of those cases this field is None, which is the honest answer,
        rather than a number that would read like a byte count and is not one.

      * `declared_content_length` is the server's Content-Length header. It is
        named "declared" because that is what it is: a claim by the peer about
        how much it intended to send, not a count of what arrived. The module's
        own `content_length` output field (`_compute_content_length`, :98)
        prefers this header and silently falls back to `len(str(body_content))`
        for parsed JSON -- the length of a Python repr. That field is fine for
        display and is not evidence, so no effect entry is built from it.
    """
    declared = response.headers.get('Content-Length')
    return [
        {
            'effect': 'http_status_received',
            'status': response.status,
            'reason': response.reason or '',
        },
        {
            'effect': 'response_body_read',
            'bytes_received': (
                len(body_content) if isinstance(body_content, (bytes, bytearray)) else None
            ),
            'declared_content_length': (
                int(declared) if isinstance(declared, str) and declared.isdigit() else None
            ),
        },
    ]


# Which errors mean "we do not know", and which mean "it did not happen".
#
# The distinction is the whole point of the off-ladder pair, and this module is
# where it bites hardest. A request refused before a byte left us did not happen:
# an unresolved `${var}` in the URL and an SSRF refusal are FAILED, and retrying
# them is pointless. A request that timed out is INDETERMINATE -- the server may
# have taken the POST, charged the card and been slow to say so -- and retrying
# it may do the thing twice.
#
# Today the engine cannot act on this: every one of these returns `ok: False`,
# which `wrap_legacy_result` turns into ExecutionStatus.ERROR and the executor
# raises, discarding the payload. The envelope is attached anyway, because the
# fact is true whether or not anything currently reads it, and because the
# alternative -- adding it later, once a consumer exists -- means the consumer
# is built first and has nothing to read. Making a timed-out POST behave
# differently from a refused one is a change to retry semantics and belongs with
# the work that owns retries, not smuggled in beside a contract definition.
_INDETERMINATE_ERROR_CODES = frozenset({'TIMEOUT', 'REQUEST_ERROR', 'CLIENT_ERROR'})


def _error_result(error_msg: str, error_code: str, url: str, duration_ms: int) -> Dict[str, Any]:
    """Build a standard error result dict."""
    rung = (
        Outcome.INDETERMINATE
        if error_code in _INDETERMINATE_ERROR_CODES
        else Outcome.FAILED
    )
    return {
        'ok': False,
        'error': error_msg,
        'error_code': error_code,
        'url': url,
        'duration_ms': duration_ms,
        'outcome': envelope(
            rung,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'http_no_response',
                'error_code': error_code,
                'measured_by': None,
                'detail': (
                    'The request was refused before it was sent; nothing reached '
                    'the peer.'
                    if rung is Outcome.FAILED else
                    'No response was read. Whether the peer received and acted on '
                    'this request is not known, so a retry may repeat an effect '
                    'that already happened.'
                ),
            }],
        ),
    }


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
        presets.SSRF_PROTECTION(),
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
                'description_key': 'modules.http.request.output.content_length.description'},
        # Present on 2xx replies only; see the comment at the success return for
        # why the non-2xx branch carries none and could not be read if it did.
        'outcome': {
            'type': 'object',
            'description': (
                "Outcome envelope. Rung 'accepted': the peer answered with a "
                "status line. Nothing here reads the resource back, so no "
                "change to it was observed."
            )
        }
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
                'body': {'name': 'John', 'email': 'dev@flyto2.com'}
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

    if ssrf_protection_enabled():
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
            async with guarded_client_session(timeout=timeout) as session:
                # SECURITY: revalidate every redirect hop through the SSRF guard
                # so a public URL cannot 302 into internal space
                # (GHSA-c9hr-64h3-gxpc). follow_redirects=False => do not follow.
                _follow = request_kwargs.get('allow_redirects', True)
                _req_kwargs = {k: v for k, v in request_kwargs.items() if k != 'allow_redirects'}
                response = await guarded_aiohttp_request(
                    session, method, url,
                    max_redirects=(5 if _follow else 0), **_req_kwargs)
                try:
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
                    if is_ok:
                        # ACCEPTED, and not one rung higher. The status line is
                        # a real answer from the other side -- somebody received
                        # this request and chose a reply -- which is exactly
                        # what separates ACCEPTED from DISPATCHED and is more
                        # than most modules in this registry can say.
                        #
                        # It is not OBSERVED, because OBSERVED is "we saw the
                        # world change" and nothing here looks at the world. A
                        # 201 Created is the server ASSERTING it created
                        # something; a 202 Accepted says in so many words that
                        # the processing has not happened yet; a 204 says
                        # nothing about state at all. All three arrive on this
                        # branch as `is_ok`. To observe the effect this module
                        # would have to read the resource back, and it never
                        # does -- there is no second request, no comparison,
                        # nothing measured outside the reply to the very
                        # message we sent. Reading a peer's report of its own
                        # work is the definition of taking its word for it.
                        #
                        # The 2xx test at :427 does not lift this either. It
                        # partitions the peer's own claim into two buckets; it
                        # does not check the claim against anything.
                        #
                        # `claim_by` is NONE: no caller declared an expected
                        # outcome and this module infers none, so there is no
                        # expectation that could have been broken. `postcondition`
                        # is None because none was declared and none was
                        # evaluated -- `register_module` accepts a
                        # `postcondition=` kwarg now, but this module passes
                        # none and reads nothing back, so the ceiling from
                        # `ceiling_for(None)` is OBSERVED. That ceiling never
                        # binds here: the honest claim is a rung below it.
                        result['outcome'] = envelope(
                            Outcome.ACCEPTED,
                            claim_by=ClaimBy.NONE,
                            effects=_observed_effects(response, body_content),
                        )
                    else:
                        # No envelope on this branch, and that is not an
                        # oversight. `ok: False` reaches `wrap_legacy_result`
                        # (modules/items.py:364) which discards `data` entirely
                        # and builds an ERROR NodeExecutionResult, so an
                        # envelope written here could never be read by anything.
                        # See the report accompanying this change: an HTTP 404
                        # raises StepExecutionError today, which means the
                        # off-ladder rungs have nowhere to sit on this module.
                        result['error'] = f"HTTP {response.status} {response.reason or ''}"
                        result['error_code'] = f"HTTP_{response.status}"
                    if attempt > 0:
                        result['retries'] = attempt
                    return result
                finally:
                    response.release()

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
