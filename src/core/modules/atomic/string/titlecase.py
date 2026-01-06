"""
String Titlecase Module
Convert string to title case
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='string.titlecase',
    version='1.0.0',
    category='string',
    subcategory='transform',
    tags=['string', 'titlecase', 'case'],
    label='Title Case String',
    label_key='modules.string.titlecase.label',
    description='Convert string to title case',
    description_key='modules.string.titlecase.description',
    icon='Type',
    color='#8B5CF6',

    # Connection types
    input_types=['text', 'string'],
    output_types=['text', 'string'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'ai.*', 'notification.*', 'flow.*'],

    # Execution settings
    timeout=None,
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
            'description': 'Title case converted string'
        }
    },
    examples=[
        {
            'title': 'Convert to title case',
            'params': {
                'text': 'hello world from flyto2'
            }
        },
        {
            'title': 'Format name',
            'params': {
                'text': 'john doe'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def string_titlecase(context: Dict[str, Any]) -> Dict[str, Any]:
    """Convert string to title case."""
    params = context['params']
    text = params.get('text', '')

    if text is None:
        return {
            'ok': False,
            'error': 'Missing required parameter: text',
            'error_code': 'MISSING_PARAM'
        }

    return {
        'result': str(text).title()
    }
