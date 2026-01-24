"""
Array Group By Module
Group array elements by a key.
"""
from typing import Any, Dict, List
from collections import defaultdict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='array.group_by',
    version='1.0.0',
    category='array',
    tags=['array', 'group', 'categorize', 'aggregate', 'advanced'],
    label='Group By',
    label_key='modules.array.group_by.label',
    description='Group array elements by a key',
    description_key='modules.array.group_by.description',
    icon='Layers',
    color='#8B5CF6',
    input_types=['array'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'array',
            type='array',
            label='Array',
            label_key='modules.array.group_by.params.array.label',
            description='Array of objects to group',
            description_key='modules.array.group_by.params.array.description',
            required=True,
            placeholder='[{"type": "a", "val": 1}, {"type": "b", "val": 2}]',
            group=FieldGroup.BASIC,
        ),
        field(
            'key',
            type='string',
            label='Group Key',
            label_key='modules.array.group_by.params.key.label',
            description='Property name to group by',
            description_key='modules.array.group_by.params.key.description',
            required=True,
            placeholder='type',
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'groups': {
            'type': 'object',
            'description': 'Grouped results',
            'description_key': 'modules.array.group_by.output.groups.description'
        },
        'keys': {
            'type': 'array',
            'description': 'Group keys',
            'description_key': 'modules.array.group_by.output.keys.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of groups',
            'description_key': 'modules.array.group_by.output.count.description'
        }
    },
    timeout_ms=5000,
)
async def array_group_by(context: Dict[str, Any]) -> Dict[str, Any]:
    """Group array elements by a key."""
    params = context['params']
    array = params.get('array')
    key = params.get('key')

    if array is None:
        raise ValidationError("Missing required parameter: array", field="array")

    if not isinstance(array, list):
        raise ValidationError("Parameter must be an array", field="array")

    if key is None:
        raise ValidationError("Missing required parameter: key", field="key")

    groups = defaultdict(list)

    for item in array:
        if isinstance(item, dict):
            group_key = str(item.get(key, 'undefined'))
        else:
            group_key = 'undefined'
        groups[group_key].append(item)

    groups_dict = dict(groups)

    return {
        'ok': True,
        'data': {
            'groups': groups_dict,
            'keys': list(groups_dict.keys()),
            'count': len(groups_dict)
        }
    }
