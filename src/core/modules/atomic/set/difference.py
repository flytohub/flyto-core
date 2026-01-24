"""
Set Difference Module
Get difference between arrays (elements in first but not in others)
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
    module_id='set.difference',
    version='1.0.0',
    category='set',
    tags=['set', 'difference', 'subtract', 'exclude', 'array'],
    label='Set Difference',
    label_key='modules.set.difference.label',
    description='Get elements in first array but not in others',
    description_key='modules.set.difference.description',
    icon='Minus',
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
        'source': {
            'type': 'array',
            'label': 'Source Array',
            'label_key': 'modules.set.difference.params.source.label',
            'description': 'Source array',
            'description_key': 'modules.set.difference.params.source.description',
            'placeholder': '[1, 2, 3, 4, 5]',
            'required': True
        },
        'exclude': {
            'type': 'array',
            'label': 'Exclude Arrays',
            'label_key': 'modules.set.difference.params.exclude.label',
            'description': 'Arrays of elements to exclude',
            'description_key': 'modules.set.difference.params.exclude.description',
            'placeholder': '[[2, 4], [5]]',
            'required': True
        }
    },
    output_schema={
        'result': {
            'type': 'array',
            'description': 'Elements in source but not in exclude arrays',
            'description_key': 'modules.set.difference.output.result.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of remaining elements',
            'description_key': 'modules.set.difference.output.count.description'
        },
        'removed_count': {
            'type': 'number',
            'description': 'Number of elements removed',
            'description_key': 'modules.set.difference.output.removed_count.description'
        }
    },
    timeout_ms=5000,
)
async def set_difference(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get elements in first array but not in others."""
    params = context['params']
    source = params.get('source')
    exclude = params.get('exclude')

    if source is None:
        raise ValidationError("Missing required parameter: source", field="source")
    if exclude is None:
        raise ValidationError("Missing required parameter: exclude", field="exclude")

    if not isinstance(source, list):
        source = [source]

    exclude_set = set()
    if isinstance(exclude, list):
        for item in exclude:
            if isinstance(item, list):
                for sub_item in item:
                    exclude_set.add(make_hashable(sub_item))
            else:
                exclude_set.add(make_hashable(item))

    result = []
    for item in source:
        if make_hashable(item) not in exclude_set:
            result.append(item)

    removed_count = len(source) - len(result)

    return {
        'ok': True,
        'data': {
            'result': result,
            'count': len(result),
            'removed_count': removed_count
        }
    }
