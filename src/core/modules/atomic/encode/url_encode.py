"""
URL Encode Module
Encode text for use in URLs (percent encoding)
"""
from typing import Any, Dict
from urllib.parse import quote, quote_plus

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='encode.url',
    version='1.0.0',
    category='encode',
    tags=['encode', 'url', 'percent', 'encoding', 'conversion'],
    label='URL Encode',
    label_key='modules.encode.url.label',
    description='URL encode text (percent encoding)',
    description_key='modules.encode.url.description',
    icon='Link',
    color='#8B5CF6',
    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'string.*', 'browser.*', 'api.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'text': {
            'type': 'text',
            'label': 'Text',
            'label_key': 'modules.encode.url.params.text.label',
            'description': 'Text to URL encode',
            'description_key': 'modules.encode.url.params.text.description',
            'placeholder': 'Hello World!',
            'required': True
        },
        'plus_spaces': {
            'type': 'boolean',
            'label': 'Plus for Spaces',
            'label_key': 'modules.encode.url.params.plus_spaces.label',
            'description': 'Use + instead of %20 for spaces (form encoding)',
            'description_key': 'modules.encode.url.params.plus_spaces.description',
            'default': False,
            'required': False
        },
        'safe': {
            'type': 'string',
            'label': 'Safe Characters',
            'label_key': 'modules.encode.url.params.safe.label',
            'description': 'Characters that should not be encoded',
            'description_key': 'modules.encode.url.params.safe.description',
            'default': '',
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'URL encoded string',
            'description_key': 'modules.encode.url.output.result.description'
        },
        'original': {
            'type': 'string',
            'description': 'Original input',
            'description_key': 'modules.encode.url.output.original.description'
        }
    },
    timeout_ms=5000,
)
async def encode_url(context: Dict[str, Any]) -> Dict[str, Any]:
    """URL encode text."""
    params = context['params']
    text = params.get('text')
    plus_spaces = params.get('plus_spaces', False)
    safe = params.get('safe', '')

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    text = str(text)

    if plus_spaces:
        result = quote_plus(text, safe=safe)
    else:
        result = quote(text, safe=safe)

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': text
        }
    }
