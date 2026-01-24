"""
Array Drop Module
Drop first N elements from array.
"""
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='array.drop',
    version='1.0.0',
    category='array',
    tags=['array', 'drop', 'skip', 'slice', 'advanced'],
    label='Drop',
    label_key='modules.array.drop.label',
    description='Drop first N elements from array',
    description_key='modules.array.drop.description',
    icon='ArrowDown',
    color='#8B5CF6',
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
            label_key='modules.array.drop.params.array.label',
            description='Source array',
            description_key='modules.array.drop.params.array.description',
            required=True,
            placeholder='[1, 2, 3, 4, 5]',
            group=FieldGroup.BASIC,
        ),
        field(
            'count',
            type='number',
            label='Count',
            label_key='modules.array.drop.params.count.label',
            description='Number of elements to drop',
            description_key='modules.array.drop.params.count.description',
            required=True,
            default=1,
            min=0,
            placeholder='2',
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'result': {
            'type': 'array',
            'description': 'Remaining elements',
            'description_key': 'modules.array.drop.output.result.description'
        },
        'dropped': {
            'type': 'number',
            'description': 'Number of elements dropped',
            'description_key': 'modules.array.drop.output.dropped.description'
        }
    },
    timeout_ms=5000,
)
async def array_drop(context: Dict[str, Any]) -> Dict[str, Any]:
    """Drop first N elements from array."""
    params = context['params']
    array = params.get('array')
    count = params.get('count', 1)

    if array is None:
        raise ValidationError("Missing required parameter: array", field="array")

    if not isinstance(array, list):
        raise ValidationError("Parameter must be an array", field="array")

    count = int(count)
    dropped = min(count, len(array))
    result = array[count:]

    return {
        'ok': True,
        'data': {
            'result': result,
            'dropped': dropped
        }
    }
