# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Crypto JWT Create Module
Create JWT (JSON Web Token) tokens.
"""
import logging
import time
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError


logger = logging.getLogger(__name__)


@register_module(
    module_id='crypto.jwt_create',
    version='1.0.0',
    category='crypto',
    tags=['crypto', 'jwt', 'token', 'auth', 'security', 'advanced'],
    label='Create JWT',
    label_key='modules.crypto.jwt_create.label',
    description='Create JWT (JSON Web Token) tokens',
    description_key='modules.crypto.jwt_create.description',
    icon='Key',
    color='#F59E0B',
    input_types=['object'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['http.*', 'data.*', 'crypto.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,
    timeout_ms=5000,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=[],

    params_schema=compose(
        field(
            'payload',
            type='object',
            label='Payload',
            label_key='modules.crypto.jwt_create.params.payload.label',
            description='JWT payload claims (JSON object)',
            description_key='modules.crypto.jwt_create.params.payload.description',
            required=True,
            placeholder='{"sub": "user123", "role": "admin"}',
            group=FieldGroup.BASIC,
        ),
        field(
            'secret',
            type='password',
            label='Secret Key',
            label_key='modules.crypto.jwt_create.params.secret.label',
            description='Secret key for signing the token',
            description_key='modules.crypto.jwt_create.params.secret.description',
            required=True,
            placeholder='your-jwt-secret',
            group=FieldGroup.BASIC,
        ),
        field(
            'algorithm',
            type='string',
            label='Algorithm',
            label_key='modules.crypto.jwt_create.params.algorithm.label',
            description='Signing algorithm',
            description_key='modules.crypto.jwt_create.params.algorithm.description',
            default='HS256',
            options=[
                {'value': 'HS256', 'label': 'HS256 (HMAC-SHA256)'},
                {'value': 'HS384', 'label': 'HS384 (HMAC-SHA384)'},
                {'value': 'HS512', 'label': 'HS512 (HMAC-SHA512)'},
                {'value': 'RS256', 'label': 'RS256 (RSA-SHA256)'},
            ],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'expires_in',
            type='number',
            label='Expires In (seconds)',
            label_key='modules.crypto.jwt_create.params.expires_in.label',
            description='Token expiration time in seconds (optional)',
            description_key='modules.crypto.jwt_create.params.expires_in.description',
            required=False,
            placeholder='3600',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'issuer',
            type='string',
            label='Issuer',
            label_key='modules.crypto.jwt_create.params.issuer.label',
            description='Token issuer (iss claim)',
            description_key='modules.crypto.jwt_create.params.issuer.description',
            required=False,
            placeholder='https://example.com',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'audience',
            type='string',
            label='Audience',
            label_key='modules.crypto.jwt_create.params.audience.label',
            description='Token audience (aud claim)',
            description_key='modules.crypto.jwt_create.params.audience.description',
            required=False,
            placeholder='https://api.example.com',
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'token': {
            'type': 'string',
            'description': 'Signed JWT token',
            'description_key': 'modules.crypto.jwt_create.output.token.description',
        },
        'algorithm': {
            'type': 'string',
            'description': 'Algorithm used for signing',
            'description_key': 'modules.crypto.jwt_create.output.algorithm.description',
        },
        'expires_at': {
            'type': 'string',
            'description': 'Token expiration timestamp (ISO 8601) or null',
            'description_key': 'modules.crypto.jwt_create.output.expires_at.description',
        },
    },
    examples=[
        {
            'title': 'Create a JWT with expiration',
            'title_key': 'modules.crypto.jwt_create.examples.basic.title',
            'params': {
                'payload': {'sub': 'user123', 'role': 'admin'},
                'secret': 'my-jwt-secret',
                'algorithm': 'HS256',
                'expires_in': 3600,
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def crypto_jwt_create(context: Dict[str, Any]) -> Dict[str, Any]:
    """Create a signed JWT token."""
    try:
        import jwt
    except ImportError:
        raise ModuleError(
            "PyJWT is required for crypto.jwt_create. "
            "Install with: pip install PyJWT"
        )

    params = context['params']
    payload = params.get('payload')
    secret = params.get('secret')
    algorithm = params.get('algorithm', 'HS256')
    expires_in = params.get('expires_in')
    issuer = params.get('issuer')
    audience = params.get('audience')

    if not payload:
        raise ValidationError("Missing required parameter: payload", field="payload")
    if not secret:
        raise ValidationError("Missing required parameter: secret", field="secret")

    if not isinstance(payload, dict):
        raise ValidationError("payload must be a JSON object (dict)", field="payload")

    # Build claims - copy to avoid mutating input
    claims = dict(payload)
    now = int(time.time())

    # Add standard claims
    claims['iat'] = now

    expires_at = None
    if expires_in is not None:
        expires_in = int(expires_in)
        if expires_in <= 0:
            raise ValidationError("expires_in must be a positive integer", field="expires_in")
        exp_timestamp = now + expires_in
        claims['exp'] = exp_timestamp
        from datetime import datetime, timezone
        expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc).isoformat()

    if issuer:
        claims['iss'] = issuer

    if audience:
        claims['aud'] = audience

    try:
        token = jwt.encode(claims, secret, algorithm=algorithm)
    except Exception as e:
        raise ModuleError(f"Failed to create JWT: {e}")

    logger.info(f"Created JWT token using {algorithm}, expires_at={expires_at}")

    return {
        'ok': True,
        'data': {
            'token': token,
            'algorithm': algorithm,
            'expires_at': expires_at,
        },
    }
