"""
Hex Decode Module
Decode hexadecimal text to string
"""
from typing import Any, Dict
import re

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='decode.hex',
    version='1.0.0',
    category='encode',
    tags=['decode', 'hex', 'hexadecimal', 'encoding', 'conversion'],
    label='Hex Decode',
    label_key='modules.decode.hex.label',
    description='Decode hexadecimal to text',
    description_key='modules.decode.hex.description',
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
            'label': 'Hex Text',
            'label_key': 'modules.decode.hex.params.text.label',
            'description': 'Hexadecimal text to decode',
            'description_key': 'modules.decode.hex.params.text.description',
            'placeholder': '48656c6c6f',
            'required': True
        },
        'encoding': {
            'type': 'string',
            'label': 'Encoding',
            'label_key': 'modules.decode.hex.params.encoding.label',
            'description': 'Character encoding for output',
            'description_key': 'modules.decode.hex.params.encoding.description',
            'default': 'utf-8',
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Decoded string',
            'description_key': 'modules.decode.hex.output.result.description'
        },
        'original': {
            'type': 'string',
            'description': 'Original hex input',
            'description_key': 'modules.decode.hex.output.original.description'
        },
        'valid': {
            'type': 'boolean',
            'description': 'Whether decoding was successful',
            'description_key': 'modules.decode.hex.output.valid.description'
        }
    },
    timeout_ms=5000,
)
async def decode_hex(context: Dict[str, Any]) -> Dict[str, Any]:
    """Decode hexadecimal to text."""
    params = context['params']
    text = params.get('text')
    encoding = params.get('encoding', 'utf-8')

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    hex_clean = re.sub(r'[\s\-:,]', '', str(text))

    try:
        decoded_bytes = bytes.fromhex(hex_clean)
        result = decoded_bytes.decode(encoding)

        return {
            'ok': True,
            'data': {
                'result': result,
                'original': text,
                'valid': True
            }
        }
    except Exception:
        return {
            'ok': True,
            'data': {
                'result': '',
                'original': text,
                'valid': False
            }
        }
