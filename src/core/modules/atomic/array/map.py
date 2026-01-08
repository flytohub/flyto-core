"""
Array Map Module

Transform each element in an array using various operations.
"""
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose, presets
from ...errors import ValidationError, InvalidTypeError


@register_module(
    module_id='array.map',
    version='1.0.0',
    category='array',
    subcategory='transform',
    tags=['array', 'map', 'transform'],
    label='Array Map',
    label_key='modules.array.map.label',
    description='Transform each element in an array',
    description_key='modules.array.map.description',
    icon='MapPin',
    color='#8B5CF6',

    # Connection types
    input_types=['array', 'json'],
    output_types=['array', 'json'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'ai.*', 'notification.*', 'flow.*'],

    # Execution settings
    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.INPUT_ARRAY(required=True),
        presets.ARRAY_OPERATION(required=True),
        presets.OPERATION_VALUE(),
    ),
    output_schema={
        'result': {
            'type': 'array',
            'description': 'Transformed array'
        ,
                'description_key': 'modules.array.map.output.result.description'},
        'length': {
            'type': 'number',
            'description': 'Length of result array'
        ,
                'description_key': 'modules.array.map.output.length.description'}
    },
    examples=[
        {
            'title': 'Multiply numbers',
            'params': {
                'array': [1, 2, 3, 4, 5],
                'operation': 'multiply',
                'value': 2
            }
        },
        {
            'title': 'Extract field from objects',
            'params': {
                'array': [{'name': 'Alice', 'age': 30}, {'name': 'Bob', 'age': 25}],
                'operation': 'extract',
                'value': 'name'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def array_map(context: Dict[str, Any]) -> Dict[str, Any]:
    """Transform each element in an array."""
    params = context['params']
    array = params.get('array', [])
    operation = params.get('operation')
    value = params.get('value')

    if not isinstance(array, list):
        raise InvalidTypeError("array must be a list", field="array", expected_type="list")

    result = []

    for item in array:
        if operation == 'multiply':
            result.append(item * (value or 1))
        elif operation == 'add':
            result.append(item + (value or 0))
        elif operation == 'extract':
            if isinstance(item, dict) and value:
                result.append(item.get(value))
            else:
                result.append(None)
        elif operation == 'uppercase':
            result.append(str(item).upper())
        elif operation == 'lowercase':
            result.append(str(item).lower())
        else:
            result.append(item)

    return {
        'ok': True,
        'data': {
            'result': result,
            'length': len(result)
        }
    }
