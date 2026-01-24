"""
Set Unique Module
Remove duplicate elements from array
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
    module_id='set.unique',
    version='1.0.0',
    category='set',
    tags=['set', 'unique', 'distinct', 'dedupe', 'array'],
    label='Set Unique',
    label_key='modules.set.unique.label',
    description='Remove duplicate elements from array',
    description_key='modules.set.unique.description',
    icon='Filter',
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
        'array': {
            'type': 'array',
            'label': 'Array',
            'label_key': 'modules.set.unique.params.array.label',
            'description': 'Array to deduplicate',
            'description_key': 'modules.set.unique.params.array.description',
            'placeholder': '[1, 2, 2, 3, 3, 3]',
            'required': True
        },
        'preserve_order': {
            'type': 'boolean',
            'label': 'Preserve Order',
            'label_key': 'modules.set.unique.params.preserve_order.label',
            'description': 'Keep first occurrence order',
            'description_key': 'modules.set.unique.params.preserve_order.description',
            'default': True,
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'array',
            'description': 'Array with unique elements',
            'description_key': 'modules.set.unique.output.result.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of unique elements',
            'description_key': 'modules.set.unique.output.count.description'
        },
        'duplicates_removed': {
            'type': 'number',
            'description': 'Number of duplicates removed',
            'description_key': 'modules.set.unique.output.duplicates_removed.description'
        }
    },
    timeout_ms=5000,
)
async def set_unique(context: Dict[str, Any]) -> Dict[str, Any]:
    """Remove duplicate elements from array."""
    params = context['params']
    array = params.get('array')
    preserve_order = params.get('preserve_order', True)

    if array is None:
        raise ValidationError("Missing required parameter: array", field="array")

    if not isinstance(array, list):
        array = [array]

    original_count = len(array)

    if preserve_order:
        seen = set()
        result = []
        for item in array:
            hashable = make_hashable(item)
            if hashable not in seen:
                seen.add(hashable)
                result.append(item)
    else:
        seen = {}
        for item in array:
            hashable = make_hashable(item)
            if hashable not in seen:
                seen[hashable] = item
        result = list(seen.values())

    duplicates_removed = original_count - len(result)

    return {
        'ok': True,
        'data': {
            'result': result,
            'count': len(result),
            'duplicates_removed': duplicates_removed
        }
    }
