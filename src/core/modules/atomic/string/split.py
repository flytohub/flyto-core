"""
String Split Module
Split a string into an array using a delimiter
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='string.split',
    version='1.0.0',
    category='string',
    tags=['string', 'split', 'array'],
    label='Split String',
    label_key='modules.string.split.label',
    description='Split a string into an array using a delimiter',
    description_key='modules.string.split.description',
    icon='Scissors',
    color='#3B82F6',

    # Connection types
    input_types=['string'],
    output_types=['array'],

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
        presets.STRING_DELIMITER(default=' '),
    ),
    output_schema={
        'parts': {
            'type': 'array',
            'description': 'Array of split string parts'
        ,
                'description_key': 'modules.string.split.output.parts.description'},
        'result': {
            'type': 'array',
            'description': 'Alias for parts - array of split string parts'
        ,
                'description_key': 'modules.string.split.output.result.description'},
        'length': {
            'type': 'number',
            'description': 'Number of parts after split'
        ,
                'description_key': 'modules.string.split.output.length.description'},
        'original': {
            'type': 'string',
            'description': 'Original input string'
        ,
                'description_key': 'modules.string.split.output.original.description'},
        'delimiter': {
            'type': 'string',
            'description': 'Delimiter used for splitting'
        ,
                'description_key': 'modules.string.split.output.delimiter.description'},
        'status': {
            'type': 'string',
            'description': 'Operation status'
        ,
                'description_key': 'modules.string.split.output.status.description'}
    }
)
async def string_split(context: Dict[str, Any]) -> Dict[str, Any]:
    """Split a string into an array using a delimiter."""
    params = context['params']
    text = params.get('text')
    delimiter = params.get('delimiter', ' ')

    if text is None:
        return {
            'ok': False,
            'error': 'Missing required parameter: text',
            'error_code': 'MISSING_PARAM'
        }

    parts = str(text).split(delimiter)

    return {
        'parts': parts,
        'result': parts,
        'length': len(parts),
        'original': text,
        'delimiter': delimiter,
        'status': 'success'
    }
