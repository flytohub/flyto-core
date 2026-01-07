"""
Object Pick Module
Pick specific keys from an object
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='object.pick',
    version='1.0.0',
    category='data',
    subcategory='object',
    tags=['object', 'pick', 'select'],
    label='Object Pick',
    label_key='modules.object.pick.label',
    description='Pick specific keys from an object',
    description_key='modules.object.pick.description',
    icon='Check',
    color='#F59E0B',

    # Connection types
    input_types=['json'],
    output_types=['json'],

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
        presets.INPUT_OBJECT(required=True),
        presets.OBJECT_KEYS(required=True),
    ),
    output_schema={
        'result': {
            'type': 'json',
            'description': 'Object with only picked keys'
        ,
                'description_key': 'modules.object.pick.output.result.description'}
    },
    examples=[
        {
            'title': 'Pick user fields',
            'params': {
                'object': {'name': 'John', 'age': 30, 'email': 'john@example.com', 'password': 'secret'},
                'keys': ['name', 'email']
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def object_pick(context: Dict[str, Any]) -> Dict[str, Any]:
    """Pick specific keys from an object."""
    params = context['params']
    obj = params.get('object')
    keys = params.get('keys', [])

    if not isinstance(obj, dict):
        return {
            'ok': False,
            'error': 'object must be a dictionary',
            'error_code': 'INVALID_TYPE'
        }

    if not isinstance(keys, list):
        return {
            'ok': False,
            'error': 'keys must be an array',
            'error_code': 'INVALID_TYPE'
        }

    result = {key: obj[key] for key in keys if key in obj}

    return {
        'result': result
    }
