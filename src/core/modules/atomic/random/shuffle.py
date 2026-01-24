"""
Random Shuffle Module
Randomly shuffle array elements.
"""
from typing import Any, Dict, List
import random

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='random.shuffle',
    version='1.0.0',
    category='random',
    tags=['random', 'shuffle', 'reorder', 'array', 'permutation'],
    label='Shuffle Array',
    label_key='modules.random.shuffle.label',
    description='Randomly shuffle array elements',
    description_key='modules.random.shuffle.description',
    icon='Shuffle',
    color='#F59E0B',
    input_types=['array'],
    output_types=['array'],

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
            label_key='modules.random.shuffle.params.array.label',
            description='Array to shuffle',
            description_key='modules.random.shuffle.params.array.description',
            required=True,
            placeholder='[1, 2, 3, 4, 5]',
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'result': {
            'type': 'array',
            'description': 'Shuffled array',
            'description_key': 'modules.random.shuffle.output.result.description'
        },
        'length': {
            'type': 'number',
            'description': 'Array length',
            'description_key': 'modules.random.shuffle.output.length.description'
        }
    },
    timeout_ms=5000,
)
async def random_shuffle(context: Dict[str, Any]) -> Dict[str, Any]:
    """Randomly shuffle array elements."""
    params = context['params']
    array = params.get('array')

    if array is None:
        raise ValidationError("Missing required parameter: array", field="array")

    if not isinstance(array, list):
        raise ValidationError("Parameter must be an array", field="array")

    # Create a copy to avoid mutating input
    shuffled = list(array)
    random.shuffle(shuffled)

    return {
        'ok': True,
        'data': {
            'result': shuffled,
            'length': len(shuffled)
        }
    }
