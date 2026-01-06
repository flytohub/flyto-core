"""
Object Keys Module
Get all keys from an object
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='object.keys',
    version='1.0.0',
    category='data',
    subcategory='object',
    tags=['object', 'keys', 'dictionary'],
    label='Object Keys',
    label_key='modules.object.keys.label',
    description='Get all keys from an object',
    description_key='modules.object.keys.description',
    icon='Key',
    color='#F59E0B',

    # Connection types
    input_types=['json'],
    output_types=['array'],

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
    ),
    output_schema={
        'keys': {
            'type': 'array',
            'description': 'List of object keys'
        },
        'count': {
            'type': 'number',
            'description': 'Number of keys'
        }
    },
    examples=[
        {
            'title': 'Get object keys',
            'params': {
                'object': {'name': 'John', 'age': 30, 'city': 'NYC'}
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def object_keys(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get all keys from an object."""
    params = context['params']
    obj = params.get('object')

    if not isinstance(obj, dict):
        return {
            'ok': False,
            'error': 'object must be a dictionary',
            'error_code': 'INVALID_TYPE'
        }

    keys = list(obj.keys())

    return {
        'keys': keys,
        'count': len(keys)
    }
