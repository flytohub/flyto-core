"""
Statistics Median Module
Calculate median (middle value) of numbers.
"""
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='stats.median',
    version='1.0.0',
    category='stats',
    tags=['stats', 'median', 'middle', 'math', 'advanced'],
    label='Median',
    label_key='modules.stats.median.label',
    description='Calculate median (middle value) of numbers',
    description_key='modules.stats.median.description',
    icon='Calculator',
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
            label_key='modules.stats.median.params.numbers.label',
            description='Array of numbers',
            description_key='modules.stats.median.params.numbers.description',
            required=True,
            placeholder='[1, 3, 5, 7, 9]',
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'median': {
            'type': 'number',
            'description': 'Median value',
            'description_key': 'modules.stats.median.output.median.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of values',
            'description_key': 'modules.stats.median.output.count.description'
        }
    },
    timeout_ms=5000,
)
async def stats_median(context: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate median of numbers."""
    params = context['params']
    numbers = params.get('numbers')

    if numbers is None:
        raise ValidationError("Missing required parameter: numbers", field="numbers")

    if not isinstance(numbers, list):
        raise ValidationError("Parameter must be an array", field="numbers")

    valid_numbers = sorted([n for n in numbers if isinstance(n, (int, float))])

    if len(valid_numbers) == 0:
        raise ValidationError("Array must contain at least one number", field="numbers")

    n = len(valid_numbers)
    mid = n // 2

    if n % 2 == 0:
        median = (valid_numbers[mid - 1] + valid_numbers[mid]) / 2
    else:
        median = valid_numbers[mid]

    return {
        'ok': True,
        'data': {
            'median': median,
            'count': n
        }
    }
