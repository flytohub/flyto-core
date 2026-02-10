"""
Base64 Encode Module
Encode text or binary data to Base64
"""
from typing import Any, Dict
import base64

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='encode.base64',
    version='1.0.0',
    category='encode',
    tags=['encode', 'base64', 'encoding', 'conversion'],
    label='Base64 Encode',
    label_key='modules.encode.base64.label',
    description='Encode text to Base64',
    description_key='modules.encode.base64.description',
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
            'label_key': 'modules.encode.base64.params.text.label',
            'description': 'Text to encode',
            'description_key': 'modules.encode.base64.params.text.description',
            'placeholder': 'Hello World',
            'required': True
        },
        'encoding': {
            'type': 'string',
            'label': 'Encoding',
            'label_key': 'modules.encode.base64.params.encoding.label',
            'description': 'Character encoding',
            'description_key': 'modules.encode.base64.params.encoding.description',
            'default': 'utf-8',
            'required': False,
            'placeholder': 'Enter Encoding...',
        },
        'url_safe': {
            'type': 'boolean',
            'label': 'URL Safe',
            'label_key': 'modules.encode.base64.params.url_safe.label',
            'description': 'Use URL-safe Base64 encoding',
            'description_key': 'modules.encode.base64.params.url_safe.description',
            'default': False,
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Base64 encoded string',
            'description_key': 'modules.encode.base64.output.result.description'
        },
        'original': {
            'type': 'string',
            'description': 'Original input',
            'description_key': 'modules.encode.base64.output.original.description'
        },
        'length': {
            'type': 'number',
            'description': 'Length of encoded string',
            'description_key': 'modules.encode.base64.output.length.description'
        }
    },
    timeout_ms=5000,
)
async def encode_base64(context: Dict[str, Any]) -> Dict[str, Any]:
    """Encode text to Base64."""
    params = context['params']
    text = params.get('text')
    encoding = params.get('encoding', 'utf-8')
    url_safe = params.get('url_safe', False)

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    text_bytes = str(text).encode(encoding)

    if url_safe:
        result = base64.urlsafe_b64encode(text_bytes).decode('ascii')
    else:
        result = base64.b64encode(text_bytes).decode('ascii')

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': text,
            'length': len(result)
        }
    }
