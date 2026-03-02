# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Crypto JWT Verify Module
Verify and decode JWT (JSON Web Token) tokens.
"""
import logging
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError


logger = logging.getLogger(__name__)


@register_module(
    module_id='crypto.jwt_verify',
    version='1.0.0',
    category='crypto',
    tags=['crypto', 'jwt', 'token', 'verify', 'auth', 'security', 'advanced'],
    label='Verify JWT',
    label_key='modules.crypto.jwt_verify.label',
    description='Verify and decode JWT tokens',
    description_key='modules.crypto.jwt_verify.description',
    icon='ShieldCheck',
    color='#10B981',
    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'logic.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,
    timeout_ms=5000,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=[],

    params_schema=compose(
        field(
            'token',
            type='string',
            label='JWT Token',
            label_key='modules.crypto.jwt_verify.params.token.label',
            description='JWT token to verify and decode',
            description_key='modules.crypto.jwt_verify.params.token.description',
            required=True,
            placeholder='eyJhbGciOiJIUzI1NiIs...',
            group=FieldGroup.BASIC,
        ),
        field(
            'secret',
            type='string',
            format='password',
            label='Secret Key',
            label_key='modules.crypto.jwt_verify.params.secret.label',
            description='Secret key for verifying the token signature',
            description_key='modules.crypto.jwt_verify.params.secret.description',
            required=True,
            placeholder='your-jwt-secret',
            group=FieldGroup.BASIC,
        ),
        field(
            'algorithms',
            type='array',
            label='Allowed Algorithms',
            label_key='modules.crypto.jwt_verify.params.algorithms.label',
            description='List of allowed signing algorithms',
            description_key='modules.crypto.jwt_verify.params.algorithms.description',
            default=['HS256'],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'verify_exp',
            type='boolean',
            label='Verify Expiration',
            label_key='modules.crypto.jwt_verify.params.verify_exp.label',
            description='Whether to verify the token expiration',
            description_key='modules.crypto.jwt_verify.params.verify_exp.description',
            default=True,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'audience',
            type='string',
            label='Audience',
            label_key='modules.crypto.jwt_verify.params.audience.label',
            description='Expected audience (aud claim)',
            description_key='modules.crypto.jwt_verify.params.audience.description',
            required=False,
            placeholder='https://api.example.com',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'issuer',
            type='string',
            label='Issuer',
            label_key='modules.crypto.jwt_verify.params.issuer.label',
            description='Expected issuer (iss claim)',
            description_key='modules.crypto.jwt_verify.params.issuer.description',
            required=False,
            placeholder='https://example.com',
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'valid': {
            'type': 'boolean',
            'description': 'Whether the token is valid',
            'description_key': 'modules.crypto.jwt_verify.output.valid.description',
        },
        'payload': {
            'type': 'object',
            'description': 'Decoded JWT payload',
            'description_key': 'modules.crypto.jwt_verify.output.payload.description',
        },
        'header': {
            'type': 'object',
            'description': 'Decoded JWT header',
            'description_key': 'modules.crypto.jwt_verify.output.header.description',
        },
    },
    examples=[
        {
            'title': 'Verify a JWT token',
            'title_key': 'modules.crypto.jwt_verify.examples.basic.title',
            'params': {
                'token': 'eyJhbGciOiJIUzI1NiIs...',
                'secret': 'my-jwt-secret',
                'algorithms': ['HS256'],
                'verify_exp': True,
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def crypto_jwt_verify(context: Dict[str, Any]) -> Dict[str, Any]:
    """Verify and decode a JWT token."""
    try:
        import jwt
    except ImportError:
        raise ModuleError(
            "PyJWT is required for crypto.jwt_verify. "
            "Install with: pip install PyJWT"
        )

    params = context['params']
    token = params.get('token')
    secret = params.get('secret')
    algorithms = params.get('algorithms', ['HS256'])
    verify_exp = params.get('verify_exp', True)
    audience = params.get('audience')
    issuer = params.get('issuer')

    if not token:
        raise ValidationError("Missing required parameter: token", field="token")
    if not secret:
        raise ValidationError("Missing required parameter: secret", field="secret")

    # Ensure algorithms is a list
    if isinstance(algorithms, str):
        algorithms = [algorithms]

    # Get header without verification first (for reporting)
    try:
        header = jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError as e:
        return {
            'ok': True,
            'data': {
                'valid': False,
                'payload': {},
                'header': {},
                'error': f"Malformed token: {e}",
            },
        }

    # Build decode options
    decode_options = {}
    if not verify_exp:
        decode_options['verify_exp'] = False

    decode_kwargs = {
        'algorithms': algorithms,
        'options': decode_options,
    }
    if audience:
        decode_kwargs['audience'] = audience
    if issuer:
        decode_kwargs['issuer'] = issuer

    try:
        payload = jwt.decode(token, secret, **decode_kwargs)
        logger.info(f"JWT verified successfully (alg={header.get('alg')})")

        return {
            'ok': True,
            'data': {
                'valid': True,
                'payload': payload,
                'header': header,
            },
        }

    except jwt.ExpiredSignatureError:
        # Decode without verification to return payload
        payload = jwt.decode(token, secret, algorithms=algorithms, options={'verify_exp': False})
        return {
            'ok': True,
            'data': {
                'valid': False,
                'payload': payload,
                'header': header,
                'error': 'Token has expired',
            },
        }

    except jwt.InvalidAudienceError:
        payload = jwt.decode(token, secret, algorithms=algorithms, options={'verify_exp': False, 'verify_aud': False})
        return {
            'ok': True,
            'data': {
                'valid': False,
                'payload': payload,
                'header': header,
                'error': 'Invalid audience',
            },
        }

    except jwt.InvalidIssuerError:
        payload = jwt.decode(token, secret, algorithms=algorithms, options={'verify_exp': False, 'verify_iss': False})
        return {
            'ok': True,
            'data': {
                'valid': False,
                'payload': payload,
                'header': header,
                'error': 'Invalid issuer',
            },
        }

    except jwt.InvalidSignatureError:
        return {
            'ok': True,
            'data': {
                'valid': False,
                'payload': {},
                'header': header,
                'error': 'Invalid signature',
            },
        }

    except jwt.DecodeError as e:
        return {
            'ok': True,
            'data': {
                'valid': False,
                'payload': {},
                'header': header,
                'error': f"Decode error: {e}",
            },
        }

    except Exception as e:
        return {
            'ok': True,
            'data': {
                'valid': False,
                'payload': {},
                'header': header,
                'error': f"Verification failed: {e}",
            },
        }
