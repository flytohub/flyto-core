"""
Array Difference Module

Find elements in first array not in others.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets
from ...errors import ValidationError, InvalidTypeError


@register_module(
    module_id='array.difference',
    version='1.0.0',
    category='array',
    subcategory='set',
    tags=['array', 'difference', 'subtract'],
    label='Array Difference',
    label_key='modules.array.difference.label',
    description='Find elements in first array not in others',
    description_key='modules.array.difference.description',
    icon='Minus',
    color='#8B5CF6',

    # Connection types
    input_types=['array'],
    output_types=['array'],

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
        presets.SUBTRACT_ARRAYS(required=True),
    ),
    output_schema={
        'result': {
            'type': 'array',
            'description': 'Elements unique to first array'
        ,
                'description_key': 'modules.array.difference.output.result.description'},
        'length': {
            'type': 'number',
            'description': 'Number of unique elements'
        ,
                'description_key': 'modules.array.difference.output.length.description'}
    },
    examples=[
        {
            'title': 'Find unique elements',
            'params': {
                'array': [1, 2, 3, 4, 5],
                'subtract': [[2, 4], [5]]
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def array_difference(context: Dict[str, Any]) -> Dict[str, Any]:
    """Find elements in first array not in others."""
    params = context['params']
    array = params.get('array', [])
    subtract = params.get('subtract', [])

    if not isinstance(array, list):
        raise InvalidTypeError("array must be a list", field="array", expected_type="list")

    if not isinstance(subtract, list):
        raise InvalidTypeError("subtract must be a list of arrays", field="subtract", expected_type="list")

    result = set(array)

    # Subtract all arrays
    for arr in subtract:
        if isinstance(arr, list):
            result = result.difference(set(arr))

    result_list = list(result)

    return {
        'ok': True,
        'data': {
            'result': result_list,
            'length': len(result_list)
        }
    }
