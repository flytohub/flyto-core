"""
Random Choice Module
Select random element(s) from an array.
"""
from typing import Any, Dict, List
import random

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='random.choice',
    version='1.0.0',
    category='random',
    tags=['random', 'choice', 'select', 'pick', 'array'],
    label='Random Choice',
    label_key='modules.random.choice.label',
    description='Select random element(s) from an array',
    description_key='modules.random.choice.description',
    icon='Shuffle',
    color='#F59E0B',
    input_types=['array'],
    output_types=['any'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'flow.*'],

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
            label_key='modules.random.choice.params.array.label',
            description='Array to pick from',
            description_key='modules.random.choice.params.array.description',
            required=True,
            placeholder='["apple", "banana", "cherry"]',
            group=FieldGroup.BASIC,
        ),
        field(
            'count',
            type='number',
            label='Count',
            label_key='modules.random.choice.params.count.label',
            description='Number of elements to pick',
            description_key='modules.random.choice.params.count.description',
            default=1,
            min=1,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'unique',
            type='boolean',
            label='Unique',
            label_key='modules.random.choice.params.unique.label',
            description='Pick unique elements (no duplicates)',
            description_key='modules.random.choice.params.unique.description',
            default=True,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'choice': {
            'type': 'any',
            'description': 'Selected element(s)',
            'description_key': 'modules.random.choice.output.choice.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of elements selected',
            'description_key': 'modules.random.choice.output.count.description'
        }
    },
    timeout_ms=5000,
)
async def random_choice(context: Dict[str, Any]) -> Dict[str, Any]:
    """Select random element(s) from an array."""
    params = context['params']
    array = params.get('array')
    count = params.get('count', 1)
    unique = params.get('unique', True)

    if array is None:
        raise ValidationError("Missing required parameter: array", field="array")

    if not isinstance(array, list):
        raise ValidationError("Parameter must be an array", field="array")

    if len(array) == 0:
        raise ValidationError("Array cannot be empty", field="array")

    count = int(count)

    if unique and count > len(array):
        raise ValidationError(
            f"Cannot pick {count} unique elements from array of {len(array)}",
            field="count"
        )

    if count == 1:
        choice = random.choice(array)
    elif unique:
        choice = random.sample(array, count)
    else:
        choice = random.choices(array, k=count)

    return {
        'ok': True,
        'data': {
            'choice': choice,
            'count': 1 if count == 1 else len(choice)
        }
    }
