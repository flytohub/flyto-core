"""
Statistics Sum Module
Calculate sum of numbers.
"""
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='stats.sum',
    version='1.0.0',
    category='stats',
    tags=['stats', 'sum', 'total', 'math', 'advanced'],
    label='Sum',
    label_key='modules.stats.sum.label',
    description='Calculate sum of numbers',
    description_key='modules.stats.sum.description',
    icon='Plus',
    color='#3B82F6',
    input_types=['array'],
    output_types=['number'],

    can_receive_from=['*'],
    can_connect_to=['math.*', 'data.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'numbers',
            type='array',
            label='Numbers',
            label_key='modules.stats.sum.params.numbers.label',
            description='Array of numbers',
            description_key='modules.stats.sum.params.numbers.description',
            required=True,
            placeholder='[1, 2, 3, 4, 5]',
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'sum': {
            'type': 'number',
            'description': 'Sum of numbers',
            'description_key': 'modules.stats.sum.output.sum.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of values',
            'description_key': 'modules.stats.sum.output.count.description'
        }
    },
    timeout_ms=5000,
)
async def stats_sum(context: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate sum of numbers."""
    params = context['params']
    numbers = params.get('numbers')

    if numbers is None:
        raise ValidationError("Missing required parameter: numbers", field="numbers")

    if not isinstance(numbers, list):
        raise ValidationError("Parameter must be an array", field="numbers")

    valid_numbers = [n for n in numbers if isinstance(n, (int, float))]

    return {
        'ok': True,
        'data': {
            'sum': sum(valid_numbers),
            'count': len(valid_numbers)
        }
    }
