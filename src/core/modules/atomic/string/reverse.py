"""
String Reverse Module
Reverse the characters in a string
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='string.reverse',
    version='1.0.0',
    category='string',
    tags=['string', 'reverse', 'text'],
    label='String Reverse',
    label_key='modules.string.reverse.label',
    description='Reverse the characters in a string',
    description_key='modules.string.reverse.description',
    icon='ArrowLeftRight',
    color='#6366F1',
    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'ai.*', 'notification.*', 'flow.*'],

    # Execution settings
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.INPUT_TEXT(required=True),
    ),
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Reversed string'
        },
        'original': {
            'type': 'string',
            'description': 'Original input string'
        },
        'length': {
            'type': 'number',
            'description': 'String length'
        }
    }
)
async def string_reverse(context: Dict[str, Any]) -> Dict[str, Any]:
    """Reverse the characters in a string."""
    params = context['params']
    text = params.get('text')

    if text is None:
        return {
            'ok': False,
            'error': 'Missing required parameter: text',
            'error_code': 'MISSING_PARAM'
        }

    text_str = str(text)
    result = text_str[::-1]

    return {
        'result': result,
        'original': text,
        'length': len(text_str)
    }
