# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
OAuth2 Token Exchange Module
Exchange authorization codes, refresh tokens, or client credentials for access tokens.
Supports most OAuth2 providers (Google, GitHub, Slack, Notion, Stripe, etc.)
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import Visibility, FieldGroup

logger = logging.getLogger(__name__)


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
    author='Flyto Team',
    license='MIT',
)
async def auth_oauth2(context: Dict[str, Any]) -> Dict[str, Any]:
    """Exchange OAuth2 credentials for an access token."""
    try:
        import aiohttp
    except ImportError:
        raise ImportError("aiohttp is required for auth.oauth2. Install with: pip install aiohttp")

    params = context['params']
    token_url = params['token_url']
    grant_type = params.get('grant_type', 'authorization_code')
    timeout_seconds = params.get('timeout', 15)

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
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                token_url,
                data=body,
                headers=headers,
                ssl=True,
            ) as response:
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
                    error_desc = data.get('error_description', data.get('error', f'HTTP {response.status}'))
                    error_code = data.get('error', 'token_error')
                    logger.error(f"OAuth2 token exchange failed: {error_code} - {error_desc}")
                    return {
                        'ok': False,
                        'error': error_desc,
                        'error_code': error_code,
                        'status': response.status,
                        'raw': data,
                        'duration_ms': duration_ms,
                    }

                logger.info(
                    f"OAuth2 {grant_type} token exchange successful "
                    f"(expires_in={data.get('expires_in', 'unknown')}s, {duration_ms}ms)"
                )

                return {
                    'ok': True,
                    'access_token': data.get('access_token', ''),
                    'token_type': data.get('token_type', 'Bearer'),
                    'expires_in': data.get('expires_in'),
                    'refresh_token': data.get('refresh_token'),
                    'scope': data.get('scope', ''),
                    'raw': data,
                    'duration_ms': duration_ms,
                }

    except asyncio.TimeoutError:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"OAuth2 token exchange timeout after {timeout_seconds}s")
        return {
            'ok': False,
            'error': f'Token exchange timed out after {timeout_seconds} seconds',
            'error_code': 'TIMEOUT',
            'duration_ms': duration_ms,
        }
    except aiohttp.ClientError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"OAuth2 client error: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'CLIENT_ERROR',
            'duration_ms': duration_ms,
        }
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"OAuth2 token exchange failed: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'EXCHANGE_ERROR',
            'duration_ms': duration_ms,
        }
