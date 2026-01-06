"""
Object Values Module
Get all values from an object
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='object.values',
    version='1.0.0',
    category='data',
    subcategory='object',
    tags=['object', 'values', 'dictionary'],
    label='Object Values',
    label_key='modules.object.values.label',
    description='Get all values from an object',
    description_key='modules.object.values.description',
    icon='List',
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
        'values': {
            'type': 'array',
            'description': 'List of object values'
        },
        'count': {
            'type': 'number',
            'description': 'Number of values'
        }
    },
    examples=[
        {
            'title': 'Get object values',
            'params': {
                'object': {'name': 'John', 'age': 30, 'city': 'NYC'}
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def object_values(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get all values from an object."""
    params = context['params']
    obj = params.get('object')

    if not isinstance(obj, dict):
        return {
            'ok': False,
            'error': 'object must be a dictionary',
            'error_code': 'INVALID_TYPE'
        }

    values = list(obj.values())

    return {
        'values': values,
        'count': len(values)
    }
