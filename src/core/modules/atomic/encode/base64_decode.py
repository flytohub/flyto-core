"""
Base64 Decode Module
Decode Base64 encoded text
"""
from typing import Any, Dict
import base64

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='decode.base64',
    version='1.0.0',
    category='encode',
    tags=['decode', 'base64', 'encoding', 'conversion'],
    label='Base64 Decode',
    label_key='modules.decode.base64.label',
    description='Decode Base64 encoded text',
    description_key='modules.decode.base64.description',
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
            'label': 'Base64 Text',
            'label_key': 'modules.decode.base64.params.text.label',
            'description': 'Base64 encoded text to decode',
            'description_key': 'modules.decode.base64.params.text.description',
            'placeholder': 'SGVsbG8gV29ybGQ=',
            'required': True
        },
        'encoding': {
            'type': 'string',
            'label': 'Encoding',
            'label_key': 'modules.decode.base64.params.encoding.label',
            'description': 'Character encoding for output',
            'description_key': 'modules.decode.base64.params.encoding.description',
            'default': 'utf-8',
            'required': False,
            'placeholder': 'Enter Encoding...',
        },
        'url_safe': {
            'type': 'boolean',
            'label': 'URL Safe',
            'label_key': 'modules.decode.base64.params.url_safe.label',
            'description': 'Input is URL-safe Base64',
            'description_key': 'modules.decode.base64.params.url_safe.description',
            'default': False,
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Decoded string',
            'description_key': 'modules.decode.base64.output.result.description'
        },
        'original': {
            'type': 'string',
            'description': 'Original Base64 input',
            'description_key': 'modules.decode.base64.output.original.description'
        },
        'valid': {
            'type': 'boolean',
            'description': 'Whether decoding was successful',
            'description_key': 'modules.decode.base64.output.valid.description'
        }
    },
    timeout_ms=5000,
)
async def decode_base64(context: Dict[str, Any]) -> Dict[str, Any]:
    """Decode Base64 encoded text."""
    params = context['params']
    text = params.get('text')
    encoding = params.get('encoding', 'utf-8')
    url_safe = params.get('url_safe', False)

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    try:
        if url_safe:
            decoded_bytes = base64.urlsafe_b64decode(text)
        else:
            decoded_bytes = base64.b64decode(text)

        result = decoded_bytes.decode(encoding)

        return {
            'ok': True,
            'data': {
                'result': result,
                'original': text,
                'valid': True
            }
        }
    except Exception as e:
        return {
            'ok': True,
            'data': {
                'result': '',
                'original': text,
                'valid': False
            }
        }
