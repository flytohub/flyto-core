"""
Hex Encode Module
Encode text to hexadecimal representation
"""
from typing import Any, Dict

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='encode.hex',
    version='1.0.0',
    category='encode',
    tags=['encode', 'hex', 'hexadecimal', 'encoding', 'conversion'],
    label='Hex Encode',
    label_key='modules.encode.hex.label',
    description='Encode text to hexadecimal',
    description_key='modules.encode.hex.description',
    icon='Binary',
    color='#8B5CF6',
    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'string.*', 'file.*', 'api.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'text': {
            'type': 'text',
            'label': 'Text',
            'label_key': 'modules.encode.hex.params.text.label',
            'description': 'Text to encode to hex',
            'description_key': 'modules.encode.hex.params.text.description',
            'placeholder': 'Hello',
            'required': True
        },
        'encoding': {
            'type': 'string',
            'label': 'Encoding',
            'label_key': 'modules.encode.hex.params.encoding.label',
            'description': 'Character encoding',
            'description_key': 'modules.encode.hex.params.encoding.description',
            'default': 'utf-8',
            'required': False
        },
        'uppercase': {
            'type': 'boolean',
            'label': 'Uppercase',
            'label_key': 'modules.encode.hex.params.uppercase.label',
            'description': 'Use uppercase hex letters',
            'description_key': 'modules.encode.hex.params.uppercase.description',
            'default': False,
            'required': False
        },
        'separator': {
            'type': 'string',
            'label': 'Separator',
            'label_key': 'modules.encode.hex.params.separator.label',
            'description': 'Separator between hex bytes',
            'description_key': 'modules.encode.hex.params.separator.description',
            'default': '',
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Hex encoded string',
            'description_key': 'modules.encode.hex.output.result.description'
        },
        'original': {
            'type': 'string',
            'description': 'Original input',
            'description_key': 'modules.encode.hex.output.original.description'
        },
        'byte_count': {
            'type': 'number',
            'description': 'Number of bytes encoded',
            'description_key': 'modules.encode.hex.output.byte_count.description'
        }
    },
    timeout_ms=5000,
)
async def encode_hex(context: Dict[str, Any]) -> Dict[str, Any]:
    """Encode text to hexadecimal."""
    params = context['params']
    text = params.get('text')
    encoding = params.get('encoding', 'utf-8')
    uppercase = params.get('uppercase', False)
    separator = params.get('separator', '')

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    text = str(text)
    text_bytes = text.encode(encoding)

    if separator:
        hex_parts = [f'{b:02x}' for b in text_bytes]
        result = separator.join(hex_parts)
    else:
        result = text_bytes.hex()

    if uppercase:
        result = result.upper()

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': text,
            'byte_count': len(text_bytes)
        }
    }
