"""
Array Take Module
Take first N elements from array.
"""
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='array.take',
    version='1.0.0',
    category='array',
    tags=['array', 'take', 'slice', 'first', 'advanced'],
    label='Take',
    label_key='modules.array.take.label',
    description='Take first N elements from array',
    description_key='modules.array.take.description',
    icon='ArrowUp',
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
            label_key='modules.array.take.params.array.label',
            description='Source array',
            description_key='modules.array.take.params.array.description',
            required=True,
            placeholder='[1, 2, 3, 4, 5]',
            group=FieldGroup.BASIC,
        ),
        field(
            'count',
            type='number',
            label='Count',
            label_key='modules.array.take.params.count.label',
            description='Number of elements to take',
            description_key='modules.array.take.params.count.description',
            required=True,
            default=1,
            min=0,
            placeholder='3',
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'result': {
            'type': 'array',
            'description': 'Taken elements',
            'description_key': 'modules.array.take.output.result.description'
        },
        'length': {
            'type': 'number',
            'description': 'Number of elements taken',
            'description_key': 'modules.array.take.output.length.description'
        }
    },
    timeout_ms=5000,
)
async def array_take(context: Dict[str, Any]) -> Dict[str, Any]:
    """Take first N elements from array."""
    params = context['params']
    array = params.get('array')
    count = params.get('count', 1)

    if array is None:
        raise ValidationError("Missing required parameter: array", field="array")

    if not isinstance(array, list):
        raise ValidationError("Parameter must be an array", field="array")

    count = int(count)
    result = array[:count]

    return {
        'ok': True,
        'data': {
            'result': result,
            'length': len(result)
        }
    }
