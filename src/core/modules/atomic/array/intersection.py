"""
Array Intersection Module

Find common elements between arrays.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets
from ...errors import ValidationError, InvalidValueError


@register_module(
    module_id='array.intersection',
    version='1.0.0',
    category='array',
    subcategory='set',
    tags=['array', 'intersection', 'common'],
    label='Array Intersection',
    label_key='modules.array.intersection.label',
    description='Find common elements between arrays',
    description_key='modules.array.intersection.description',
    icon='Intersect',
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
        presets.ARRAYS(required=True),
    ),
    output_schema={
        'result': {
            'type': 'array',
            'description': 'Common elements'
        ,
                'description_key': 'modules.array.intersection.output.result.description'},
        'length': {
            'type': 'number',
            'description': 'Number of common elements'
        ,
                'description_key': 'modules.array.intersection.output.length.description'}
    },
    examples=[
        {
            'title': 'Find common elements',
            'params': {
                'arrays': [[1, 2, 3, 4], [2, 3, 5], [2, 3, 6]]
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def array_intersection(context: Dict[str, Any]) -> Dict[str, Any]:
    """Find common elements between arrays."""
    params = context['params']
    arrays = params.get('arrays', [])

    if not isinstance(arrays, list) or len(arrays) < 2:
        raise InvalidValueError("arrays must be a list with at least 2 arrays", field="arrays")

    # Convert first array to set
    result = set(arrays[0])

    # Intersect with remaining arrays
    for arr in arrays[1:]:
        result = result.intersection(set(arr))

    result_list = list(result)

    return {
        'ok': True,
        'data': {
            'result': result_list,
            'length': len(result_list)
        }
    }
