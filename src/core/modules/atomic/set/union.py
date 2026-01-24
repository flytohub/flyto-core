"""
Set Union Module
Get union of two or more arrays
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


def restore_type(item, original_items):
    """Restore original type from hashable."""
    for orig in original_items:
        if make_hashable(orig) == item:
            return orig
    return item


@register_module(
    module_id='set.union',
    version='1.0.0',
    category='set',
    tags=['set', 'union', 'combine', 'merge', 'array'],
    label='Set Union',
    label_key='modules.set.union.label',
    description='Get union of two or more arrays',
    description_key='modules.set.union.description',
    icon='Union',
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
            'label_key': 'modules.set.union.params.arrays.label',
            'description': 'Arrays to combine (array of arrays)',
            'description_key': 'modules.set.union.params.arrays.description',
            'placeholder': '[[1, 2], [2, 3], [3, 4]]',
            'required': True
        }
    },
    output_schema={
        'result': {
            'type': 'array',
            'description': 'Union of all arrays',
            'description_key': 'modules.set.union.output.result.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of unique elements',
            'description_key': 'modules.set.union.output.count.description'
        }
    },
    timeout_ms=5000,
)
async def set_union(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get union of two or more arrays."""
    params = context['params']
    arrays = params.get('arrays')

    if arrays is None:
        raise ValidationError("Missing required parameter: arrays", field="arrays")

    if not isinstance(arrays, list):
        raise ValidationError("arrays must be an array of arrays", field="arrays")

    all_items = []
    for arr in arrays:
        if isinstance(arr, list):
            all_items.extend(arr)

    seen = set()
    result = []
    for item in all_items:
        hashable = make_hashable(item)
        if hashable not in seen:
            seen.add(hashable)
            result.append(item)

    return {
        'ok': True,
        'data': {
            'result': result,
            'count': len(result)
        }
    }
