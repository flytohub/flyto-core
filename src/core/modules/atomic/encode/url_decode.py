"""
URL Decode Module
Decode URL encoded text (percent decoding)
"""
from typing import Any, Dict
from urllib.parse import unquote, unquote_plus

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='decode.url',
    version='1.0.0',
    category='encode',
    tags=['decode', 'url', 'percent', 'encoding', 'conversion'],
    label='URL Decode',
    label_key='modules.decode.url.label',
    description='Decode URL encoded text',
    description_key='modules.decode.url.description',
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
            'label': 'URL Encoded Text',
            'label_key': 'modules.decode.url.params.text.label',
            'description': 'URL encoded text to decode',
            'description_key': 'modules.decode.url.params.text.description',
            'placeholder': 'Hello%20World%21',
            'required': True
        },
        'plus_spaces': {
            'type': 'boolean',
            'label': 'Plus as Spaces',
            'label_key': 'modules.decode.url.params.plus_spaces.label',
            'description': 'Treat + as space (form decoding)',
            'description_key': 'modules.decode.url.params.plus_spaces.description',
            'default': False,
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Decoded string',
            'description_key': 'modules.decode.url.output.result.description'
        },
        'original': {
            'type': 'string',
            'description': 'Original URL encoded input',
            'description_key': 'modules.decode.url.output.original.description'
        }
    },
    timeout_ms=5000,
)
async def decode_url(context: Dict[str, Any]) -> Dict[str, Any]:
    """Decode URL encoded text."""
    params = context['params']
    text = params.get('text')
    plus_spaces = params.get('plus_spaces', False)

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    text = str(text)

    if plus_spaces:
        result = unquote_plus(text)
    else:
        result = unquote(text)

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': text
        }
    }
