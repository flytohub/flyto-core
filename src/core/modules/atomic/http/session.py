# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
HTTP Session Module
Send multiple HTTP requests with persistent cookies and session state.
Useful for APIs that require login → action → logout flows.

HOW FAR THIS MODULE FOLLOWS REALITY

Two envelopes, at two levels, because the result has two levels.

Each entry in `results` carries its own, on the same argument `http.request`
makes: a status line is the peer reporting on its own work, which is ACCEPTED
and not OBSERVED -- a login step that returns 200 has told us it thinks it
logged us in, and nothing here reads any state back to check. A step that never
got a response is INDETERMINATE, and an SSRF refusal is FAILED because nothing
left this machine.

The step-level envelope sits at the top of the result, and it has to: only the
surviving `data` dict is read for an outcome, and `results` is a key inside it
that `step_executor._outcome_payloads` does not descend into. It is the WEAKEST
of the per-request answers, by the same rule `step_outcome` applies across a
step -- a session is only as confirmed as its least confirmed request, and a
login that timed out followed by two requests that 200'd is not an accepted
session.

WHAT `stop_on_error` DOES to that number is worth stating: it breaks the loop,
so requests after the failure are never attempted at all. They are not
DISPATCHED and they are not anything else -- they did not happen. The effect
reports `requests_declared` beside `requests_attempted` so a reader can see
how much of the sequence the rung is about.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope, is_on_ladder, rung_index
from ....utils import guarded_client_session, SSRFError, validate_url_with_env_config
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup, Visibility

logger = logging.getLogger(__name__)


def _session_outcome(
    *,
    results: List[Dict[str, Any]],
    requests_declared: int,
    cookie_count: int,
) -> Dict[str, Any]:
    """The weakest of the per-request rungs, as the step's own answer.

    Weakest, and off-ladder answers win outright, which is `step_outcome`'s
    rule reproduced here rather than referenced: FAILED and INDETERMINATE are
    not low rungs to be averaged away. FAILED is reported ahead of
    INDETERMINATE when a session carries both, because a request that was
    refused before sending is the one somebody has to act on.

    `cookie_count` rides in the effect and lifts nothing. Cookies in the jar
    are Set-Cookie headers the peer sent, which is more of the peer talking
    about itself; they are useful to see and are not evidence that a session
    was established.
    """
    rungs = []
    statuses = []
    for entry in results:
        found = entry.get('outcome')
        if isinstance(found, dict) and found.get('rung'):
            rungs.append(Outcome(found['rung']))
        if entry.get('status') is not None:
            statuses.append(entry['status'])

    measured = {
        'kind': 'session_requests',
        'requests_declared': requests_declared,
        'requests_attempted': len(results),
        'statuses': statuses,
        'cookies': cookie_count,
        'measured_by': 'the weakest rung among the per-request envelopes below',
    }

    if not rungs:
        # No request produced an envelope at all, which today means no request
        # ran. Nothing was confirmed and nothing is claimed beyond that.
        return envelope(
            Outcome.DISPATCHED,
            claim_by=ClaimBy.NONE,
            effects=[dict(measured, detail='No request in this session produced a result.')],
        )

    off_ladder = [rung for rung in rungs if not is_on_ladder(rung)]
    if off_ladder:
        failed = [rung for rung in off_ladder if rung is Outcome.FAILED]
        return envelope(
            failed[0] if failed else off_ladder[0],
            claim_by=ClaimBy.NONE,
            effects=[dict(
                measured,
                detail=(
                    'At least one request was refused before it was sent.'
                    if failed else
                    'At least one request produced no response, so whether the '
                    'peer acted on it is not known.'
                ),
            )],
        )

    # Every rung left is on the ladder, so `rung_index` is a number for all of
    # them and the comparison is the ladder's own order rather than a local
    # opinion about which answer is worse.
    weakest = min(rungs, key=rung_index)
    return envelope(
        weakest,
        claim_by=ClaimBy.NONE,
        effects=[dict(
            measured,
            detail=(
                'Every attempted request got a status line back. The peers '
                'answered; nothing here reads any state back to check what '
                'they did with the requests.'
            ),
        )],
    )


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


def _no_response_outcome(label: str, error_code: str) -> Dict[str, Any]:
    """One request that produced no response at all.

    INDETERMINATE, never FAILED. The request was sent and the answer never
    arrived, so whether the peer acted on it is unknown -- which matters most
    on exactly the sequences this module exists for, where step two of a login
    flow timing out may or may not have already changed something.
    """
    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'http_no_response',
            'label': label,
            'error_code': error_code,
            'measured_by': None,
            'detail': (
                'No response was read. Whether the peer received and acted on '
                'this request is not known, so a retry may repeat an effect '
                'that already happened.'
            ),
        }],
    )


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
        return {
            'label': req_label, 'ok': False, 'error': str(e),
            'error_code': 'SSRF_BLOCKED',
            # FAILED and not INDETERMINATE: the guard runs before the request
            # is built, so nothing reached the peer. That is knowable, and a
            # retry of this step cannot repeat an effect there is none of.
            'outcome': envelope(
                Outcome.FAILED,
                claim_by=ClaimBy.NONE,
                effects=[{
                    'kind': 'request_refused_before_send',
                    'label': req_label,
                    'measured_by': None,
                    'detail': 'The SSRF guard refused this target; nothing was sent.',
                }],
            ),
        }

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
                # ACCEPTED whatever the status. The rung says how far this was
                # followed, not whether it succeeded: a 401 on the login step
                # is the peer receiving the request and answering it, and `ok`
                # beside it carries the success question. Not OBSERVED --
                # nothing here reads any state back.
                'outcome': envelope(
                    Outcome.ACCEPTED,
                    claim_by=ClaimBy.NONE,
                    effects=[{
                        'kind': 'http_status_received',
                        'label': req_label,
                        'status': response.status,
                        'reason': response.reason or '',
                        'measured_by': 'response.status, read off the reply',
                    }],
                ),
            }
    except asyncio.TimeoutError:
        req_duration = int((time.time() - req_start) * 1000)
        return {
            'label': req_label, 'ok': False, 'error': 'Timeout',
            'error_code': 'TIMEOUT', 'duration_ms': req_duration,
            'outcome': _no_response_outcome(req_label, 'TIMEOUT'),
        }
    except Exception as e:
        req_duration = int((time.time() - req_start) * 1000)
        return {
            'label': req_label, 'ok': False, 'error': str(e),
            'error_code': 'CLIENT_ERROR', 'duration_ms': req_duration,
            'outcome': _no_response_outcome(req_label, 'CLIENT_ERROR'),
        }


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
        presets.HTTP_AUTH(),
        field(
            'stop_on_error',
            type='boolean',
            label='Stop on Error',
            label_key='modules.http.session.stop_on_error',
            description='Stop executing remaining requests if one fails (non-2xx)',
            default=True,
            group=FieldGroup.OPTIONS,
        ),
        presets.TIMEOUT_S(default=30),
        presets.VERIFY_SSL(default=True),
        presets.SSRF_PROTECTION(),
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
        'outcome': {
            'type': 'object',
            'description': (
                'Step-level outcome envelope: the weakest of the per-request '
                'rungs. "accepted" when every attempted request got a status '
                'line, "indeterminate" when one produced no response, "failed" '
                'when one was refused before sending. Each entry in results '
                'carries its own envelope under the same key'
            ),
            'description_key': 'modules.http.session.output.outcome.description',
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
    author='Flyto2 Team',
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
                'results': [], 'cookies': {}, 'duration_ms': 0,
                'outcome': envelope(
                    Outcome.FAILED,
                    claim_by=ClaimBy.NONE,
                    effects=[{
                        'kind': 'session_not_started',
                        'measured_by': None,
                        'detail': 'No requests were supplied; no session was opened.',
                    }],
                )}

    results: List[Dict[str, Any]] = []
    start_time = time.time()
    all_ok = True

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    cookie_jar = aiohttp.CookieJar()

    try:
        async with guarded_client_session(timeout=timeout, cookie_jar=cookie_jar) as session:
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
        # INDETERMINATE: this handler covers everything outside the per-request
        # try, including a failure while opening or closing the session, and
        # `results` may already hold requests that were sent. What happened to
        # the ones after it is not known.
        return {'ok': False, 'error': str(e), 'error_code': 'SESSION_ERROR',
                'results': results, 'cookies': {}, 'duration_ms': duration_ms,
                'outcome': envelope(
                    Outcome.INDETERMINATE,
                    claim_by=ClaimBy.NONE,
                    effects=[{
                        'kind': 'session_aborted',
                        'requests_declared': len(requests_list),
                        'requests_attempted': len(results),
                        'error_type': type(e).__name__,
                        'measured_by': None,
                        'detail': (
                            'The session raised outside any single request. '
                            'Requests already in results were sent; whether '
                            'anything else was is not known.'
                        ),
                    }],
                )}

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(f"Session complete: {len(results)} requests, all_ok={all_ok} ({duration_ms}ms)")
    return {'ok': all_ok, 'results': results, 'cookies': cookies, 'duration_ms': duration_ms,
            'outcome': _session_outcome(
                results=results,
                requests_declared=len(requests_list),
                cookie_count=len(cookies),
            )}
