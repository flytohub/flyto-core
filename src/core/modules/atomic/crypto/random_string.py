"""
Crypto Random String Module
Generate cryptographically secure random string.
"""
from typing import Any, Dict
import secrets
import string

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='crypto.random_string',
    version='1.0.0',
    category='crypto',
    tags=['crypto', 'random', 'string', 'password', 'token', 'advanced'],
    label='Random String',
    label_key='modules.crypto.random_string.label',
    description='Generate cryptographically secure random string',
    description_key='modules.crypto.random_string.description',
    icon='Key',
    color='#DC2626',
    input_types=[],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'string.*', 'flow.*'],

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
            label_key='modules.crypto.random_string.params.length.label',
            description='String length',
            description_key='modules.crypto.random_string.params.length.description',
            required=True,
            default=16,
            min=1,
            max=256,
            placeholder='16',
            group=FieldGroup.BASIC,
        ),
        field(
            'charset',
            type='string',
            label='Character Set',
            label_key='modules.crypto.random_string.params.charset.label',
            description='Characters to use',
            description_key='modules.crypto.random_string.params.charset.description',
            default='alphanumeric',
            options=[
                {'value': 'alphanumeric', 'label': 'Alphanumeric (A-Za-z0-9)'},
                {'value': 'alpha', 'label': 'Letters only (A-Za-z)'},
                {'value': 'numeric', 'label': 'Numbers only (0-9)'},
                {'value': 'hex', 'label': 'Hexadecimal (0-9a-f)'},
                {'value': 'alphanumeric_symbols', 'label': 'With symbols'},
            ],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'uppercase',
            type='boolean',
            label='Uppercase Only',
            label_key='modules.crypto.random_string.params.uppercase.label',
            description='Convert to uppercase',
            description_key='modules.crypto.random_string.params.uppercase.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'string': {
            'type': 'string',
            'description': 'Random string',
            'description_key': 'modules.crypto.random_string.output.string.description'
        },
        'length': {
            'type': 'number',
            'description': 'String length',
            'description_key': 'modules.crypto.random_string.output.length.description'
        }
    },
    timeout_ms=5000,
)
async def crypto_random_string(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate cryptographically secure random string."""
    params = context['params']
    length = params.get('length', 16)
    charset = params.get('charset', 'alphanumeric')
    uppercase = params.get('uppercase', False)

    length = int(length)

    if length < 1 or length > 256:
        raise ValidationError("Length must be between 1 and 256", field="length")

    # Define character sets
    charsets = {
        'alphanumeric': string.ascii_letters + string.digits,
        'alpha': string.ascii_letters,
        'numeric': string.digits,
        'hex': string.hexdigits[:16],
        'alphanumeric_symbols': string.ascii_letters + string.digits + '!@#$%^&*()_+-=[]{}|;:,.<>?',
    }

    chars = charsets.get(charset, charsets['alphanumeric'])

    # Generate random string
    result = ''.join(secrets.choice(chars) for _ in range(length))

    if uppercase:
        result = result.upper()

    return {
        'ok': True,
        'data': {
            'string': result,
            'length': len(result)
        }
    }
