"""
Crypto Random Bytes Module
Generate cryptographically secure random bytes.
"""
from typing import Any, Dict
import secrets
import base64

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='crypto.random_bytes',
    version='1.0.0',
    category='crypto',
    tags=['crypto', 'random', 'bytes', 'security', 'advanced'],
    label='Random Bytes',
    label_key='modules.crypto.random_bytes.label',
    description='Generate cryptographically secure random bytes',
    description_key='modules.crypto.random_bytes.description',
    icon='Shuffle',
    color='#DC2626',
    input_types=[],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'crypto.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'length',
            type='number',
            label='Length',
            label_key='modules.crypto.random_bytes.params.length.label',
            description='Number of bytes',
            description_key='modules.crypto.random_bytes.params.length.description',
            required=True,
            default=32,
            min=1,
            max=1024,
            placeholder='32',
            group=FieldGroup.BASIC,
        ),
        field(
            'encoding',
            type='string',
            label='Encoding',
            label_key='modules.crypto.random_bytes.params.encoding.label',
            description='Output encoding',
            description_key='modules.crypto.random_bytes.params.encoding.description',
            default='hex',
            options=[
                {'value': 'hex', 'label': 'Hexadecimal'},
                {'value': 'base64', 'label': 'Base64'},
                {'value': 'base64url', 'label': 'Base64 URL-safe'},
            ],
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'bytes': {
            'type': 'string',
            'description': 'Random bytes (encoded)',
            'description_key': 'modules.crypto.random_bytes.output.bytes.description'
        },
        'length': {
            'type': 'number',
            'description': 'Number of bytes generated',
            'description_key': 'modules.crypto.random_bytes.output.length.description'
        }
    },
    timeout_ms=5000,
)
async def crypto_random_bytes(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate cryptographically secure random bytes."""
    params = context['params']
    length = params.get('length', 32)
    encoding = params.get('encoding', 'hex')

    length = int(length)

    if length < 1 or length > 1024:
        raise ValidationError("Length must be between 1 and 1024", field="length")

    # Generate random bytes
    random_bytes = secrets.token_bytes(length)

    # Encode
    if encoding == 'base64':
        result = base64.b64encode(random_bytes).decode('utf-8')
    elif encoding == 'base64url':
        result = base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')
    else:
        result = random_bytes.hex()

    return {
        'ok': True,
        'data': {
            'bytes': result,
            'length': length
        }
    }
