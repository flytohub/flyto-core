"""
String Replace Module
Replace occurrences of a substring in a string
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='string.replace',
    version='1.0.0',
    category='string',
    tags=['string', 'replace', 'text'],
    label='String Replace',
    label_key='modules.string.replace.label',
    description='Replace occurrences of a substring in a string',
    description_key='modules.string.replace.description',
    icon='Replace',
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
        presets.SEARCH_STRING(required=True),
        presets.REPLACE_STRING(required=True),
    ),
    output_schema={
        'result': {
            'type': 'string',
            'description': 'String with replacements applied'
        ,
                'description_key': 'modules.string.replace.output.result.description'},
        'original': {
            'type': 'string',
            'description': 'Original input string'
        ,
                'description_key': 'modules.string.replace.output.original.description'},
        'search': {
            'type': 'string',
            'description': 'Search string that was replaced'
        ,
                'description_key': 'modules.string.replace.output.search.description'},
        'replace': {
            'type': 'string',
            'description': 'Replacement string used'
        ,
                'description_key': 'modules.string.replace.output.replace.description'},
        'status': {
            'type': 'string',
            'description': 'Operation status'
        ,
                'description_key': 'modules.string.replace.output.status.description'}
    }
)
async def string_replace(context: Dict[str, Any]) -> Dict[str, Any]:
    """Replace occurrences of a substring in a string."""
    params = context['params']
    text = params.get('text')
    search = params.get('search')
    replace_with = params.get('replace')

    if text is None:
        return {
            'ok': False,
            'error': 'Missing required parameter: text',
            'error_code': 'MISSING_PARAM'
        }

    if search is None:
        return {
            'ok': False,
            'error': 'Missing required parameter: search',
            'error_code': 'MISSING_PARAM'
        }

    if replace_with is None:
        return {
            'ok': False,
            'error': 'Missing required parameter: replace',
            'error_code': 'MISSING_PARAM'
        }

    result = str(text).replace(str(search), str(replace_with))

    return {
        'result': result,
        'original': text,
        'search': search,
        'replace': replace_with,
        'status': 'success'
    }
