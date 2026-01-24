"""
HTML Encode Module
Encode text to HTML entities
"""
from typing import Any, Dict
import html

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='encode.html',
    version='1.0.0',
    category='encode',
    tags=['encode', 'html', 'entities', 'escape', 'encoding'],
    label='HTML Encode',
    label_key='modules.encode.html.label',
    description='Encode text to HTML entities',
    description_key='modules.encode.html.description',
    icon='Code',
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
            'label_key': 'modules.encode.html.params.text.label',
            'description': 'Text to encode as HTML entities',
            'description_key': 'modules.encode.html.params.text.description',
            'placeholder': '<script>alert("XSS")</script>',
            'required': True
        },
        'quote': {
            'type': 'boolean',
            'label': 'Encode Quotes',
            'label_key': 'modules.encode.html.params.quote.label',
            'description': 'Also encode quote characters',
            'description_key': 'modules.encode.html.params.quote.description',
            'default': True,
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'HTML encoded string',
            'description_key': 'modules.encode.html.output.result.description'
        },
        'original': {
            'type': 'string',
            'description': 'Original input',
            'description_key': 'modules.encode.html.output.original.description'
        }
    },
    timeout_ms=5000,
)
async def encode_html(context: Dict[str, Any]) -> Dict[str, Any]:
    """Encode text to HTML entities."""
    params = context['params']
    text = params.get('text')
    quote_param = params.get('quote', True)

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    text = str(text)
    result = html.escape(text, quote=quote_param)

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': text
        }
    }
