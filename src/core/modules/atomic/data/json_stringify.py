"""
JSON Stringify Module
Convert object to JSON string
"""
from typing import Any, Dict
import json

from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='data.json.stringify',
    version='1.0.0',
    category='data',
    tags=['data', 'json', 'stringify', 'serialize'],
    label='JSON Stringify',
    label_key='modules.data.json.stringify.label',
    description='Convert object to JSON string',
    description_key='modules.data.json.stringify.description',
    icon='FileCode',
    color='#F59E0B',

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
        presets.DATA_OBJECT(required=True),
        presets.PRETTY_PRINT(default=False),
        presets.INDENT_SIZE(default=2),
    ),
    output_schema={
        'status': {
            'type': 'string',
            'description': 'Operation status'
        ,
                'description_key': 'modules.data.json.stringify.output.status.description'},
        'json': {
            'type': 'string',
            'description': 'JSON string'
        ,
                'description_key': 'modules.data.json.stringify.output.json.description'}
    },
    examples=[
        {
            'name': 'Stringify object',
            'params': {
                'data': {'name': 'John', 'age': 30},
                'pretty': True
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def json_stringify(context: Dict[str, Any]) -> Dict[str, Any]:
    """Convert object to JSON string."""
    params = context['params']
    data = params.get('data')
    pretty = params.get('pretty', False)
    indent = params.get('indent', 2)

    if data is None:
        return {
            'ok': False,
            'error': 'Missing required parameter: data',
            'error_code': 'MISSING_PARAM'
        }

    try:
        if pretty:
            json_str = json.dumps(data, indent=indent, ensure_ascii=False)
        else:
            json_str = json.dumps(data, ensure_ascii=False)

        return {
            'status': 'success',
            'json': json_str
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Failed to stringify: {str(e)}'
        }
