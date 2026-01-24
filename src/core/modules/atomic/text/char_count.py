"""
Character Count Module
Count characters in text
"""
from typing import Any, Dict

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='text.char_count',
    version='1.0.0',
    category='text',
    tags=['text', 'character', 'count', 'analysis', 'statistics'],
    label='Character Count',
    label_key='modules.text.char_count.label',
    description='Count characters in text',
    description_key='modules.text.char_count.description',
    icon='FileText',
    color='#F59E0B',
    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'flow.*', 'notification.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'text': {
            'type': 'text',
            'label': 'Text',
            'label_key': 'modules.text.char_count.params.text.label',
            'description': 'Text to analyze',
            'description_key': 'modules.text.char_count.params.text.description',
            'placeholder': 'Enter text to count characters',
            'required': True
        }
    },
    output_schema={
        'total': {
            'type': 'number',
            'description': 'Total character count',
            'description_key': 'modules.text.char_count.output.total.description'
        },
        'without_spaces': {
            'type': 'number',
            'description': 'Count without spaces',
            'description_key': 'modules.text.char_count.output.without_spaces.description'
        },
        'letters': {
            'type': 'number',
            'description': 'Letter count',
            'description_key': 'modules.text.char_count.output.letters.description'
        },
        'digits': {
            'type': 'number',
            'description': 'Digit count',
            'description_key': 'modules.text.char_count.output.digits.description'
        },
        'spaces': {
            'type': 'number',
            'description': 'Space count',
            'description_key': 'modules.text.char_count.output.spaces.description'
        },
        'lines': {
            'type': 'number',
            'description': 'Line count',
            'description_key': 'modules.text.char_count.output.lines.description'
        }
    },
    timeout_ms=5000,
)
async def text_char_count(context: Dict[str, Any]) -> Dict[str, Any]:
    """Count characters in text."""
    params = context['params']
    text = params.get('text')

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    text = str(text)

    total = len(text)
    spaces = sum(1 for c in text if c.isspace())
    without_spaces = total - spaces
    letters = sum(1 for c in text if c.isalpha())
    digits = sum(1 for c in text if c.isdigit())
    lines = text.count('\n') + 1 if text else 0

    return {
        'ok': True,
        'data': {
            'total': total,
            'without_spaces': without_spaces,
            'letters': letters,
            'digits': digits,
            'spaces': spaces,
            'lines': lines
        }
    }
