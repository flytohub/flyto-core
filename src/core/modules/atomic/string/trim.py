"""
String Trim Module
Remove whitespace from both ends of a string
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='string.trim',
    version='1.0.0',
    category='string',
    tags=['string', 'trim', 'whitespace', 'text'],
    label='String Trim',
    label_key='modules.string.trim.label',
    description='Remove whitespace from both ends of a string',
    description_key='modules.string.trim.description',
    icon='Scissors',
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
            'description': 'Trimmed string with whitespace removed'
        },
        'original': {
            'type': 'string',
            'description': 'Original input string'
        },
        'status': {
            'type': 'string',
            'description': 'Operation status'
        }
    }
)
async def string_trim(context: Dict[str, Any]) -> Dict[str, Any]:
    """Remove whitespace from both ends of a string."""
    params = context['params']
    text = params.get('text')

    if text is None:
        return {
            'ok': False,
            'error': 'Missing required parameter: text',
            'error_code': 'MISSING_PARAM'
        }

    result = str(text).strip()

    return {
        'result': result,
        'original': text,
        'status': 'success'
    }
