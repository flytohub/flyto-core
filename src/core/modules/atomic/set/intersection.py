"""
Set Intersection Module
Get intersection of two or more arrays
"""
from typing import Any, Dict, List

from ...registry import register_module
from ...errors import ValidationError


def make_hashable(item):
    """Convert item to hashable type for set operations."""
    if isinstance(item, dict):
        return tuple(sorted((k, make_hashable(v)) for k, v in item.items()))
    elif isinstance(item, list):
        return tuple(make_hashable(i) for i in item)
    return item


@register_module(
    module_id='set.intersection',
    version='1.0.0',
    category='set',
    tags=['set', 'intersection', 'common', 'array'],
    label='Set Intersection',
    label_key='modules.set.intersection.label',
    description='Get intersection of two or more arrays',
    description_key='modules.set.intersection.description',
    icon='Intersect',
    color='#A855F7',
    input_types=['array'],
    output_types=['array'],

    can_receive_from=['*'],
    can_connect_to=['array.*', 'data.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'arrays': {
            'type': 'array',
            'label': 'Arrays',
            'label_key': 'modules.set.intersection.params.arrays.label',
            'description': 'Arrays to intersect (array of arrays)',
            'description_key': 'modules.set.intersection.params.arrays.description',
            'placeholder': '[[1, 2, 3], [2, 3, 4], [3, 4, 5]]',
            'required': True
        }
    },
    output_schema={
        'result': {
            'type': 'array',
            'description': 'Intersection of all arrays',
            'description_key': 'modules.set.intersection.output.result.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of common elements',
            'description_key': 'modules.set.intersection.output.count.description'
        }
    },
    timeout_ms=5000,
)
async def set_intersection(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get intersection of two or more arrays."""
    params = context['params']
    arrays = params.get('arrays')

    if arrays is None:
        raise ValidationError("Missing required parameter: arrays", field="arrays")

    if not isinstance(arrays, list):
        raise ValidationError("arrays must be an array of arrays", field="arrays")

    valid_arrays = [arr for arr in arrays if isinstance(arr, list)]

    if not valid_arrays:
        return {
            'ok': True,
            'data': {
                'result': [],
                'count': 0
            }
        }

    first = valid_arrays[0]
    first_map = {make_hashable(item): item for item in first}

    common = set(first_map.keys())
    for arr in valid_arrays[1:]:
        arr_set = {make_hashable(item) for item in arr}
        common = common.intersection(arr_set)

    result = [first_map[h] for h in common if h in first_map]

    return {
        'ok': True,
        'data': {
            'result': result,
            'count': len(result)
        }
    }
