"""
String Lowercase Module
Convert a string to lowercase
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='string.lowercase',
    version='1.0.0',
    category='string',
    tags=['string', 'lowercase', 'case', 'text'],
    label='String Lowercase',
    label_key='modules.string.lowercase.label',
    description='Convert a string to lowercase',
    description_key='modules.string.lowercase.description',
    icon='CaseLower',
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
            'description': 'Lowercase converted string'
        ,
                'description_key': 'modules.string.lowercase.output.result.description'},
        'original': {
            'type': 'string',
            'description': 'Original input string'
        ,
                'description_key': 'modules.string.lowercase.output.original.description'},
        'status': {
            'type': 'string',
            'description': 'Operation status'
        ,
                'description_key': 'modules.string.lowercase.output.status.description'}
    }
)
async def string_lowercase(context: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a string to lowercase."""
    params = context['params']
    text = params.get('text')

    if text is None:
        return {
            'ok': False,
            'error': 'Missing required parameter: text',
            'error_code': 'MISSING_PARAM'
        }

    result = str(text).lower()

    return {
        'result': result,
        'original': text,
        'status': 'success'
    }
