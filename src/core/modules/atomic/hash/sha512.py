"""
SHA512 Hash Module
Calculate SHA-512 cryptographic hash of text.
"""
from typing import Any, Dict
import hashlib

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='hash.sha512',
    version='1.0.0',
    category='hash',
    tags=['hash', 'sha512', 'crypto', 'checksum', 'security'],
    label='SHA-512 Hash',
    label_key='modules.hash.sha512.label',
    description='Calculate SHA-512 cryptographic hash of text',
    description_key='modules.hash.sha512.description',
    icon='Lock',
    color='#8B5CF6',
    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'string.*', 'file.*', 'api.*', 'notification.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'text',
            type='text',
            label='Text',
            label_key='modules.hash.sha512.params.text.label',
            description='Text to hash',
            description_key='modules.hash.sha512.params.text.description',
            required=True,
            placeholder='Hello World',
            group=FieldGroup.BASIC,
        ),
        field(
            'encoding',
            type='string',
            label='Encoding',
            label_key='modules.hash.sha512.params.encoding.label',
            description='Text encoding',
            description_key='modules.hash.sha512.params.encoding.description',
            default='utf-8',
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'hash': {
            'type': 'string',
            'description': 'SHA-512 hash (128 hex characters)',
            'description_key': 'modules.hash.sha512.output.hash.description'
        },
        'algorithm': {
            'type': 'string',
            'description': 'Hash algorithm used',
            'description_key': 'modules.hash.sha512.output.algorithm.description'
        }
    },
    timeout_ms=5000,
)
async def hash_sha512(context: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate SHA-512 hash of text."""
    params = context['params']
    text = params.get('text')
    encoding = params.get('encoding', 'utf-8')

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    hash_obj = hashlib.sha512(str(text).encode(encoding))
    hash_hex = hash_obj.hexdigest()

    return {
        'ok': True,
        'data': {
            'hash': hash_hex,
            'algorithm': 'sha512'
        }
    }
