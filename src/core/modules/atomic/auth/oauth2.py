# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
OAuth2 Token Exchange Module
Exchange authorization codes, refresh tokens, or client credentials for access tokens.
Supports most OAuth2 providers (Google, GitHub, Slack, Notion, Stripe, etc.)

HOW FAR THIS MODULE FOLLOWS REALITY

Seven return paths, four answers, and the split that matters is not between
success and failure -- it is between "the provider told us what it did" and "we
do not know what the provider did". This module MUTATES state at the provider:
an `authorization_code` grant is single-use, so a request that reached the
server burns the code whether or not the reply ever reached us.

  2xx, and no `error` key in the body                 ACCEPTED
      A server received this POST and chose a reply. That is the whole distance
      travelled: nothing here uses the token, so "a credential that works" is
      not observed and is not claimed. `http.request` settled this position for
      every 2xx in this product and `third_party/developer/github.py` restates
      it -- a body the peer wrote about its own work is the peer's word.
      Whether an access grant actually came back rides in the effect as a
      boolean, because a 200 whose body carries no `access_token` is a real
      path here: `data.get('access_token', '')` returns '' and `ok` stays True.

  4xx, or an `error` key in a non-5xx body            FAILED
      The provider read the request, named a refusal, and issued nothing.
      Nothing is left in doubt.

  5xx                                                 INDETERMINATE
      The provider took the request off the wire and did not say what it did
      with it. A code may already be consumed. This module is `retryable=True,
      max_retries=2`, so calling this FAILED would tell an author "nothing
      happened" about the one case where a retry can come back
      `invalid_grant` for a code the first attempt spent.

  timeout, transport error, unexpected exception      INDETERMINATE
      The textbook indeterminate. The POST may have been received in full.

  SSRF block BEFORE the request                       FAILED
      `enforce_outbound_url` runs at the top of the function, before a session
      exists. Nothing left this machine.

  SSRFError raised from inside the request            INDETERMINATE
      Not the same fact, and the difference is worth the extra branch.
      `guarded_aiohttp_request` re-validates every redirect hop
      (`utils.py:913`), and the initial URL was already validated above, so an
      SSRFError from in there is a blocked *hop* -- meaning the original POST
      was sent, and only the follow-up was stopped.

VERIFIED is unreachable and no postcondition is declared. Verifying an access
token means using it -- one call to a resource server that comes back 200 --
and this module never makes one. Declaring a postcondition without that call
would move the claim up a rung and the evidence not at all.

A NOTE ON FIELD NAMES: `_redact_sensitive_output` (`step_executor/executor.py:44`)
blanks any dict key matching `token|credential|auth|secret|...`, recursively,
before results reach hooks or storage. The keys inside these effects avoid
those substrings on purpose -- an effect field called `access_token_present`
would reach every consumer as '[REDACTED]' and the rung would be evidence-free.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import (
    SSRFError,
    enforce_outbound_url,
    guarded_aiohttp_request,
    guarded_client_session,
)
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup, Visibility

logger = logging.getLogger(__name__)


def _reply_read(status: int, grant_type: str) -> Dict[str, Any]:
    """The one thing every path that got an answer can point at.

    A server received this request, processed it far enough to choose a status
    line, and sent one. Everything else in this module's success payload is the
    provider describing its own work.
    """
    return {
        'kind': 'token_endpoint_reply_read',
        'grant_type': grant_type,
        'status': status,
        'measured_by': 'aiohttp response.status -- the status line of the reply to this POST',
        'detail': (
            'A server chose a reply to this exchange. Nothing in this module '
            'uses the result of the exchange, so this is the whole distance '
            'travelled: no resource server was called with what came back.'
        ),
    }


def _exchange_accepted(
    *,
    status: int,
    grant_type: str,
    carries_grant: bool,
    expires_in: Any,
) -> Dict[str, Any]:
    """ACCEPTED -- the provider answered without naming an error.

    `carries_grant` is recorded rather than being allowed to change the rung.
    It is a fact about the reply, not a measurement of the world: an
    `access_token` in a JSON body is the provider stating that it issued one,
    which is the same kind of claim as the 2xx that carried it. Promoting it to
    OBSERVED would mean claiming we saw a credential work, and nothing here
    ever presents it to a resource server.
    """
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[
            _reply_read(status, grant_type),
            {
                'kind': 'grant_reply_body_read',
                'carries_access_grant': carries_grant,
                'expires_in': expires_in,
                'measured_by': "bool(data.get('access_token')) over the parsed reply body",
                'detail': (
                    'Whether the reply carried a non-empty access grant. False '
                    'is a real outcome of this path: the module returns ok=True '
                    'with an empty string when a 2xx body has no access_token, '
                    'so a consumer that only reads ok cannot tell the two apart.'
                ),
            },
        ],
    )


def _exchange_refused(*, status: int, grant_type: str, error_named: bool) -> Dict[str, Any]:
    """FAILED -- the provider read the request and named a refusal.

    FAILED rather than INDETERMINATE because nothing is left in doubt: a 4xx
    from a token endpoint, or an RFC 6749 `error` member in the body, is the
    provider saying it issued nothing. The code may still have been consumed by
    that attempt -- `invalid_grant` often means exactly that -- but "no token
    was issued to us" is not uncertain, and that is what the rung is about.

    `error_named` is a BOOLEAN and not the provider's error string, which is a
    deliberate limit rather than an oversight. The failure return here carries
    only a status: the body is withheld because a token endpoint's error body
    can echo request material back, and
    `tests/core/test_reported_security_advisories.py::test_oauth2_uses_guarded_request_and_redacts_error_body`
    pins that -- it asserts the body appears nowhere in `repr(result)`. An
    envelope is part of the result, so putting `data['error']` in here would
    reopen exactly the hole that test was written to close.
    """
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[
            _reply_read(status, grant_type),
            {
                'kind': 'exchange_refused',
                'status': status,
                'error_named_in_body': error_named,
                'measured_by': "response.status >= 400, or an 'error' member in the parsed body",
                'detail': (
                    'The provider named a refusal. No access grant was issued to us. '
                    'The error body is deliberately not carried here.'
                ),
            },
        ],
    )


def _exchange_uncertain(
    *,
    grant_type: str,
    reason: str,
    detail: str,
    status: Optional[int] = None,
) -> Dict[str, Any]:
    """INDETERMINATE -- the request may have been processed in full.

    The set this covers is every way of not getting a usable answer: a 5xx, a
    timeout, a severed connection, a blocked redirect hop, an unexpected raise.
    They differ in cause and not in what is known, which is nothing about
    whether the provider consumed the grant.

    This is the rung that has to be right for `retryable=True` to be safe to
    read. An automation that treats "no answer" as "nothing happened" retries a
    single-use authorization code and gets a refusal for the wrong reason.
    """
    effects = [{
        'kind': 'exchange_unconfirmed',
        'grant_type': grant_type,
        'reason': reason,
        'status': status,
        'measured_by': None,
        'detail': detail,
    }]
    if status is not None:
        effects.insert(0, _reply_read(status, grant_type))
    return envelope(Outcome.INDETERMINATE, claim_by=ClaimBy.NONE, effects=effects)


def _exchange_not_sent(*, grant_type: str, reason: str) -> Dict[str, Any]:
    """FAILED -- the request never left this machine.

    Distinct from every other failure here, and the reason it is worth its own
    envelope is what the engine does without one: `default_for` stamps a
    side-effecting module that reports nothing as `dispatched` -- "the
    instruction left us". For a URL rejected before a session was opened, that
    default would be false in the one direction that matters, telling an
    operator a token endpoint was contacted when it was not.
    """
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'request_not_sent',
            'grant_type': grant_type,
            'reason': reason,
            'measured_by': 'enforce_outbound_url raised before any session was opened',
            'detail': 'No request was issued. The provider was never contacted.',
        }],
    )


def _build_token_body(params: Dict[str, Any]) -> Dict[str, Any]:
    """Build the token request body based on grant_type."""
    grant_type = params.get('grant_type', 'authorization_code')
    body: Dict[str, Any] = {
        'grant_type': grant_type,
        'client_id': params['client_id'],
    }

    client_secret = params.get('client_secret')
    if client_secret:
        body['client_secret'] = client_secret

    if grant_type == 'authorization_code':
        body['code'] = params.get('code', '')
        redirect_uri = params.get('redirect_uri')
        if redirect_uri:
            body['redirect_uri'] = redirect_uri
        code_verifier = params.get('code_verifier')
        if code_verifier:
            body['code_verifier'] = code_verifier

    elif grant_type == 'refresh_token':
        body['refresh_token'] = params.get('refresh_token', '')

    elif grant_type == 'client_credentials':
        scope = params.get('scope')
        if scope:
            body['scope'] = scope

    return body


def _apply_client_auth(
    headers: Dict[str, str],
    body: Dict[str, Any],
    params: Dict[str, Any],
) -> None:
    """Apply client authentication (header vs body)."""
    import base64

    auth_method = params.get('client_auth_method', 'body')
    if auth_method == 'header':
        client_id = params['client_id']
        client_secret = params.get('client_secret', '')
        credentials = base64.b64encode(
            f'{client_id}:{client_secret}'.encode()
        ).decode()
        headers['Authorization'] = f'Basic {credentials}'
        body.pop('client_id', None)
        body.pop('client_secret', None)


@register_module(
    module_id='auth.oauth2',
    version='1.0.0',
    category='atomic',
    subcategory='auth',
    tags=['oauth2', 'auth', 'token', 'api', 'authorization', 'atomic'],
    label='OAuth2 Token Exchange',
    label_key='modules.auth.oauth2.label',
    description='Exchange authorization code, refresh token, or client credentials for an access token',
    description_key='modules.auth.oauth2.description',
    icon='Key',
    color='#F59E0B',

    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],
    can_be_start=True,

    timeout_ms=30000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'filesystem.write'],

    params_schema=compose(
        field(
            'token_url',
            type='string',
            label='Token URL',
            label_key='modules.auth.oauth2.token_url',
            description='OAuth2 token endpoint URL',
            placeholder='https://oauth2.googleapis.com/token',
            required=True,
            validation={'pattern': r'^https?://.+', 'message': 'Must start with http:// or https://'},
            format='url',
            group=FieldGroup.BASIC,
        ),
        field(
            'grant_type',
            type='string',
            label='Grant Type',
            label_key='modules.auth.oauth2.grant_type',
            description='OAuth2 grant type',
            default='authorization_code',
            options=[
                {'value': 'authorization_code', 'label': 'Authorization Code'},
                {'value': 'refresh_token', 'label': 'Refresh Token'},
                {'value': 'client_credentials', 'label': 'Client Credentials'},
            ],
            group=FieldGroup.BASIC,
        ),
        field(
            'client_id',
            type='string',
            label='Client ID',
            label_key='modules.auth.oauth2.client_id',
            description='OAuth2 application client ID',
            placeholder='${env.OAUTH_CLIENT_ID}',
            required=True,
            group=FieldGroup.CONNECTION,
        ),
        field(
            'client_secret',
            type='string',
            label='Client Secret',
            label_key='modules.auth.oauth2.client_secret',
            description='OAuth2 application client secret',
            placeholder='${env.OAUTH_CLIENT_SECRET}',
            format='password',
            group=FieldGroup.CONNECTION,
        ),
        field(
            'code',
            type='string',
            label='Authorization Code',
            label_key='modules.auth.oauth2.code',
            description='Authorization code received from the OAuth2 authorization flow',
            placeholder='4/0AX4XfWh...',
            showIf={'grant_type': {'$in': ['authorization_code']}},
            group=FieldGroup.BASIC,
        ),
        field(
            'redirect_uri',
            type='string',
            label='Redirect URI',
            label_key='modules.auth.oauth2.redirect_uri',
            description='Redirect URI used in the authorization request (must match exactly)',
            placeholder='https://yourapp.com/callback',
            format='url',
            showIf={'grant_type': {'$in': ['authorization_code']}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'refresh_token',
            type='string',
            label='Refresh Token',
            label_key='modules.auth.oauth2.refresh_token',
            description='Refresh token for obtaining a new access token',
            format='password',
            showIf={'grant_type': {'$in': ['refresh_token']}},
            group=FieldGroup.BASIC,
        ),
        field(
            'scope',
            type='string',
            label='Scope',
            label_key='modules.auth.oauth2.scope',
            description='Space-separated list of OAuth2 scopes',
            placeholder='read write openid',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'code_verifier',
            type='string',
            label='Code Verifier (PKCE)',
            label_key='modules.auth.oauth2.code_verifier',
            description='PKCE code verifier for public clients',
            showIf={'grant_type': {'$in': ['authorization_code']}},
            visibility=Visibility.EXPERT,
            group=FieldGroup.ADVANCED,
        ),
        field(
            'client_auth_method',
            type='string',
            label='Client Auth Method',
            label_key='modules.auth.oauth2.client_auth_method',
            description='How to send client credentials to the token endpoint',
            default='body',
            options=[
                {'value': 'body', 'label': 'POST Body (most common)'},
                {'value': 'header', 'label': 'Basic Auth Header'},
            ],
            visibility=Visibility.EXPERT,
            group=FieldGroup.ADVANCED,
        ),
        field(
            'extra_params',
            type='object',
            label='Extra Parameters',
            label_key='modules.auth.oauth2.extra_params',
            description='Additional parameters to include in the token request',
            default={},
            ui={'widget': 'key_value'},
            visibility=Visibility.EXPERT,
            group=FieldGroup.ADVANCED,
        ),
        field(
            'timeout',
            type='number',
            label='Timeout (seconds)',
            label_key='schema.field.timeout_s',
            description='Maximum time to wait in seconds',
            default=15,
            min=1,
            max=60,
            step=1,
            ui={'unit': 's'},
            visibility=Visibility.EXPERT,
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether token exchange was successful',
            'description_key': 'modules.auth.oauth2.output.ok.description',
        },
        'access_token': {
            'type': 'string',
            'description': 'The access token for API requests',
            'description_key': 'modules.auth.oauth2.output.access_token.description',
        },
        'token_type': {
            'type': 'string',
            'description': 'Token type (usually "Bearer")',
            'description_key': 'modules.auth.oauth2.output.token_type.description',
        },
        'expires_in': {
            'type': 'number',
            'description': 'Token lifetime in seconds',
            'description_key': 'modules.auth.oauth2.output.expires_in.description',
        },
        'refresh_token': {
            'type': 'string',
            'description': 'Refresh token (if provided by the OAuth2 server)',
            'description_key': 'modules.auth.oauth2.output.refresh_token.description',
        },
        'scope': {
            'type': 'string',
            'description': 'Granted scopes',
            'description_key': 'modules.auth.oauth2.output.scope.description',
        },
        'raw': {
            'type': 'object',
            'description': 'Full raw response from the token endpoint',
            'description_key': 'modules.auth.oauth2.output.raw.description',
        },
        'duration_ms': {
            'type': 'number',
            'description': 'Request duration in milliseconds',
            'description_key': 'modules.auth.oauth2.output.duration_ms.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the exchange was followed: "accepted" when the provider '
                'answered without naming an error, "failed" when it named one or '
                'the request was never sent, "indeterminate" on a 5xx, a timeout '
                'or a transport error -- where a single-use grant may already have '
                'been consumed. Never higher than "accepted": nothing here uses '
                'the token it received'
            ),
            'description_key': 'modules.auth.oauth2.output.outcome.description',
        },
    },
    examples=[
        {
            'title': 'Exchange authorization code (Google)',
            'title_key': 'modules.auth.oauth2.examples.auth_code.title',
            'params': {
                'token_url': 'https://oauth2.googleapis.com/token',
                'grant_type': 'authorization_code',
                'client_id': '${env.GOOGLE_CLIENT_ID}',
                'client_secret': '${env.GOOGLE_CLIENT_SECRET}',
                'code': '4/0AX4XfWh...',
                'redirect_uri': 'https://yourapp.com/callback',
            },
        },
        {
            'title': 'Refresh an expired token',
            'title_key': 'modules.auth.oauth2.examples.refresh.title',
            'params': {
                'token_url': 'https://oauth2.googleapis.com/token',
                'grant_type': 'refresh_token',
                'client_id': '${env.GOOGLE_CLIENT_ID}',
                'client_secret': '${env.GOOGLE_CLIENT_SECRET}',
                'refresh_token': '${env.REFRESH_TOKEN}',
            },
        },
        {
            'title': 'Client credentials (machine-to-machine)',
            'title_key': 'modules.auth.oauth2.examples.client_creds.title',
            'params': {
                'token_url': 'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token',
                'grant_type': 'client_credentials',
                'client_id': '${env.AZURE_CLIENT_ID}',
                'client_secret': '${env.AZURE_CLIENT_SECRET}',
                'scope': 'https://graph.microsoft.com/.default',
            },
        },
        {
            'title': 'GitHub OAuth (code exchange)',
            'title_key': 'modules.auth.oauth2.examples.github.title',
            'params': {
                'token_url': 'https://github.com/login/oauth/access_token',
                'grant_type': 'authorization_code',
                'client_id': '${env.GITHUB_CLIENT_ID}',
                'client_secret': '${env.GITHUB_CLIENT_SECRET}',
                'code': 'abc123...',
            },
        },
    ],
    author='Flyto2 Team',
    license='MIT',
)
async def auth_oauth2(context: Dict[str, Any]) -> Dict[str, Any]:
    """Exchange OAuth2 credentials for an access token."""
    try:
        import aiohttp
    except ImportError:
        raise ImportError(
            "aiohttp is required for auth.oauth2. Install with: pip install aiohttp"
        ) from None

    params = context['params']
    token_url = params['token_url']
    grant_type = params.get('grant_type', 'authorization_code')
    timeout_seconds = params.get('timeout', 15)

    try:
        enforce_outbound_url(token_url)
    except SSRFError as e:
        return {
            'ok': False,
            'error': f'SSRF protection blocked token endpoint: {e}',
            'error_code': 'SSRF_BLOCKED',
            'outcome': _exchange_not_sent(
                grant_type=grant_type,
                reason='the token endpoint URL was blocked by the outbound SSRF guard',
            ),
        }

    body = _build_token_body(params)

    extra_params = params.get('extra_params', {})
    if extra_params:
        body.update(extra_params)

    headers: Dict[str, str] = {
        'Accept': 'application/json',
    }

    _apply_client_auth(headers, body, params)

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    start_time = time.time()

    try:
        async with guarded_client_session(timeout=timeout) as session:
            response = await guarded_aiohttp_request(
                session,
                'POST',
                token_url,
                data=body,
                headers=headers,
                ssl=True,
            )
            try:
                duration_ms = int((time.time() - start_time) * 1000)

                # Some providers (GitHub) return text by default
                ct = response.headers.get('Content-Type', '')
                if 'application/json' in ct:
                    data = await response.json()
                else:
                    text = await response.text()
                    # Try JSON parse anyway (GitHub returns JSON with wrong content-type)
                    try:
                        import json
                        data = json.loads(text)
                    except (ValueError, TypeError):
                        # URL-encoded response (rare but some old providers)
                        from urllib.parse import parse_qs
                        parsed = parse_qs(text)
                        data = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

                if response.status >= 400 or 'error' in data:
                    logger.error(
                        "OAuth2 token endpoint rejected the request (HTTP %s)",
                        response.status,
                    )
                    # One return, two rungs, split on 5xx. A 4xx (or an RFC 6749
                    # `error` member) is the provider stating it issued nothing.
                    # A 5xx is the provider not stating anything: it took the
                    # POST and broke, and an authorization_code is single-use,
                    # so the grant may already be spent. The old code treated
                    # both as one error and a retry could not tell them apart.
                    error_named = isinstance(data, dict) and bool(data.get('error'))
                    if response.status >= 500:
                        outcome = _exchange_uncertain(
                            grant_type=grant_type,
                            reason='server_error',
                            status=response.status,
                            detail=(
                                f'The provider answered HTTP {response.status} without saying '
                                'what it did with the request. A single-use grant may already '
                                'have been consumed by this attempt.'
                            ),
                        )
                    else:
                        outcome = _exchange_refused(
                            status=response.status,
                            grant_type=grant_type,
                            error_named=error_named,
                        )
                    return {
                        'ok': False,
                        'error': f'Token endpoint rejected request (HTTP {response.status})',
                        'error_code': 'TOKEN_ENDPOINT_ERROR',
                        'status': response.status,
                        'duration_ms': duration_ms,
                        'outcome': outcome,
                    }

                logger.info(
                    f"OAuth2 {grant_type} token exchange successful "
                    f"(expires_in={data.get('expires_in', 'unknown')}s, {duration_ms}ms)"
                )

                access_grant = data.get('access_token', '')
                return {
                    'ok': True,
                    'access_token': access_grant,
                    'token_type': data.get('token_type', 'Bearer'),
                    'expires_in': data.get('expires_in'),
                    'refresh_token': data.get('refresh_token'),
                    'scope': data.get('scope', ''),
                    'raw': data,
                    'duration_ms': duration_ms,
                    'outcome': _exchange_accepted(
                        status=response.status,
                        grant_type=grant_type,
                        carries_grant=bool(access_grant),
                        expires_in=data.get('expires_in'),
                    ),
                }
            finally:
                response.release()

    except SSRFError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.warning("SSRF protection blocked OAuth2 token endpoint")
        return {
            'ok': False,
            'error': f'SSRF protection blocked token endpoint: {e}',
            'error_code': 'SSRF_BLOCKED',
            'duration_ms': duration_ms,
            # NOT the same answer as the identical exception caught above the
            # session. The initial URL passed `enforce_outbound_url` already, so
            # what `guarded_aiohttp_request` blocks in here is a redirect hop
            # (utils.py:913) -- the original POST was sent and answered with a
            # 30x, and only the follow-up was stopped. What the first host did
            # with the grant before redirecting us is not knowable from here.
            'outcome': _exchange_uncertain(
                grant_type=grant_type,
                reason='ssrf_blocked_redirect',
                detail=(
                    'The SSRF guard blocked a redirect target after the request had '
                    'already been sent to the original token endpoint.'
                ),
            ),
        }
    except asyncio.TimeoutError:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"OAuth2 token exchange timeout after {timeout_seconds}s")
        return {
            'ok': False,
            'error': f'Token exchange timed out after {timeout_seconds} seconds',
            'error_code': 'TIMEOUT',
            'duration_ms': duration_ms,
            'outcome': _exchange_uncertain(
                grant_type=grant_type,
                reason='timeout',
                detail=(
                    f'No reply within {timeout_seconds}s. The POST may have been received '
                    'and processed in full; a single-use grant may already be spent.'
                ),
            ),
        }
    except aiohttp.ClientError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"OAuth2 client error: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'CLIENT_ERROR',
            'duration_ms': duration_ms,
            # Deliberately not split into "could not connect" (nothing sent) and
            # "disconnected mid-exchange" (sent). aiohttp raises
            # ClientConnectorError for the first and ServerDisconnectedError for
            # the second, but both are ClientError and this handler cannot tell
            # which subclass arrived without asserting on exception types that
            # differ between versions. Claiming the stronger of the two would be
            # guessing; indeterminate is what is actually known.
            'outcome': _exchange_uncertain(
                grant_type=grant_type,
                reason='transport_error',
                detail=(
                    f'The transport failed ({type(e).__name__}). Whether the POST reached '
                    'the provider before it failed is not knowable from here.'
                ),
            ),
        }
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"OAuth2 token exchange failed: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'EXCHANGE_ERROR',
            'duration_ms': duration_ms,
            'outcome': _exchange_uncertain(
                grant_type=grant_type,
                reason='unexpected_error',
                detail=(
                    f'{type(e).__name__} escaped the exchange. This handler wraps both the '
                    'request and the parsing of its reply, so how far the exchange got is '
                    'not knowable from here.'
                ),
            ),
        }
