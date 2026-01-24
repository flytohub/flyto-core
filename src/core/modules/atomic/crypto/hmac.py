"""
Crypto HMAC Module
Generate HMAC (Hash-based Message Authentication Code).
"""
from typing import Any, Dict
import hmac as hmac_lib
import hashlib

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='crypto.hmac',
    version='1.0.0',
    category='crypto',
    tags=['crypto', 'hmac', 'hash', 'security', 'auth', 'advanced'],
    label='HMAC',
    label_key='modules.crypto.hmac.label',
    description='Generate HMAC signature',
    description_key='modules.crypto.hmac.description',
    icon='Shield',
    color='#DC2626',
    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'api.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=[],

    params_schema=compose(
        field(
            'message',
            type='text',
            label='Message',
            label_key='modules.crypto.hmac.params.message.label',
            description='Message to sign',
            description_key='modules.crypto.hmac.params.message.description',
            required=True,
            placeholder='Hello World',
            group=FieldGroup.BASIC,
        ),
        field(
            'key',
            type='password',
            label='Secret Key',
            label_key='modules.crypto.hmac.params.key.label',
            description='Secret key for HMAC',
            description_key='modules.crypto.hmac.params.key.description',
            required=True,
            placeholder='your-secret-key',
            group=FieldGroup.BASIC,
        ),
        field(
            'algorithm',
            type='string',
            label='Algorithm',
            label_key='modules.crypto.hmac.params.algorithm.label',
            description='Hash algorithm',
            description_key='modules.crypto.hmac.params.algorithm.description',
            default='sha256',
            options=[
                {'value': 'sha256', 'label': 'SHA-256'},
                {'value': 'sha512', 'label': 'SHA-512'},
                {'value': 'sha1', 'label': 'SHA-1'},
                {'value': 'md5', 'label': 'MD5'},
            ],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'encoding',
            type='string',
            label='Output Encoding',
            label_key='modules.crypto.hmac.params.encoding.label',
            description='Output encoding format',
            description_key='modules.crypto.hmac.params.encoding.description',
            default='hex',
            options=[
                {'value': 'hex', 'label': 'Hexadecimal'},
                {'value': 'base64', 'label': 'Base64'},
            ],
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'signature': {
            'type': 'string',
            'description': 'HMAC signature',
            'description_key': 'modules.crypto.hmac.output.signature.description'
        },
        'algorithm': {
            'type': 'string',
            'description': 'Algorithm used',
            'description_key': 'modules.crypto.hmac.output.algorithm.description'
        }
    },
    timeout_ms=5000,
)
async def crypto_hmac(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate HMAC signature."""
    import base64

    params = context['params']
    message = params.get('message')
    key = params.get('key')
    algorithm = params.get('algorithm', 'sha256')
    encoding = params.get('encoding', 'hex')

    if message is None:
        raise ValidationError("Missing required parameter: message", field="message")

    if key is None:
        raise ValidationError("Missing required parameter: key", field="key")

    # Get hash function
    hash_funcs = {
        'sha256': hashlib.sha256,
        'sha512': hashlib.sha512,
        'sha1': hashlib.sha1,
        'md5': hashlib.md5,
    }

    if algorithm not in hash_funcs:
        raise ValidationError(f"Unsupported algorithm: {algorithm}", field="algorithm")

    # Generate HMAC
    signature = hmac_lib.new(
        key.encode('utf-8'),
        message.encode('utf-8'),
        hash_funcs[algorithm]
    )

    if encoding == 'base64':
        result = base64.b64encode(signature.digest()).decode('utf-8')
    else:
        result = signature.hexdigest()

    return {
        'ok': True,
        'data': {
            'signature': result,
            'algorithm': algorithm
        }
    }
