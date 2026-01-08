"""
String Uppercase Module
Convert a string to uppercase
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets
from ...errors import ValidationError


@register_module(
    module_id='string.uppercase',
    version='1.0.0',
    category='string',
    tags=['string', 'uppercase', 'case', 'text'],
    label='String Uppercase',
    label_key='modules.string.uppercase.label',
    description='Convert a string to uppercase',
    description_key='modules.string.uppercase.description',
    icon='CaseUpper',
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
            'description': 'Uppercase converted string'
        ,
                'description_key': 'modules.string.uppercase.output.result.description'},
        'original': {
            'type': 'string',
            'description': 'Original input string'
        ,
                'description_key': 'modules.string.uppercase.output.original.description'},
        'status': {
            'type': 'string',
            'description': 'Operation status'
        ,
                'description_key': 'modules.string.uppercase.output.status.description'}
    },
    timeout_ms=5000,
)
async def string_uppercase(context: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a string to uppercase."""
    params = context['params']
    text = params.get('text')

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    result = str(text).upper()

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': text
        }
    }
