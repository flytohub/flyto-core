"""
JSON Parse Module
Parse JSON string into object
"""
from typing import Any, Dict
import json

from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='data.json.parse',
    version='1.0.0',
    category='data',
    tags=['data', 'json', 'parse', 'transform'],
    label='Parse JSON',
    label_key='modules.data.json.parse.label',
    description='Parse JSON string into object',
    description_key='modules.data.json.parse.description',
    icon='Code',
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
        presets.JSON_STRING(required=True),
    ),
    output_schema={
        'status': {
            'type': 'string',
            'description': 'Operation status'
        ,
                'description_key': 'modules.data.json.parse.output.status.description'},
        'data': {
            'type': 'object',
            'description': 'Parsed object'
        ,
                'description_key': 'modules.data.json.parse.output.data.description'}
    },
    examples=[
        {
            'name': 'Parse JSON string',
            'params': {
                'json_string': '{"name": "John", "age": 30}'
            },
            'expected_output': {
                'status': 'success',
                'data': {'name': 'John', 'age': 30}
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def json_parse(context: Dict[str, Any]) -> Dict[str, Any]:
    """Parse JSON string into object."""
    params = context['params']
    json_string = params.get('json_string')

    if json_string is None:
        return {
            'ok': False,
            'error': 'Missing required parameter: json_string',
            'error_code': 'MISSING_PARAM'
        }

    try:
        data = json.loads(json_string)
        return {
            'status': 'success',
            'data': data
        }
    except json.JSONDecodeError as e:
        return {
            'status': 'error',
            'message': f'Invalid JSON: {str(e)}'
        }
