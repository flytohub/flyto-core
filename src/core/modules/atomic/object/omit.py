"""
Object Omit Module
Omit specific keys from an object
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='object.omit',
    version='1.0.0',
    category='data',
    subcategory='object',
    tags=['object', 'omit', 'exclude'],
    label='Object Omit',
    label_key='modules.object.omit.label',
    description='Omit specific keys from an object',
    description_key='modules.object.omit.description',
    icon='X',
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
            'description': 'Object without omitted keys'
        }
    },
    examples=[
        {
            'title': 'Omit sensitive fields',
            'params': {
                'object': {'name': 'John', 'age': 30, 'password': 'secret', 'ssn': '123-45-6789'},
                'keys': ['password', 'ssn']
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def object_omit(context: Dict[str, Any]) -> Dict[str, Any]:
    """Omit specific keys from an object."""
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

    result = {key: value for key, value in obj.items() if key not in keys}

    return {
        'result': result
    }
