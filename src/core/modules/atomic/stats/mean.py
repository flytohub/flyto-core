"""
Statistics Mean Module
Calculate arithmetic mean (average) of numbers.
"""
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='stats.mean',
    version='1.0.0',
    category='stats',
    tags=['stats', 'mean', 'average', 'math', 'advanced'],
    label='Mean (Average)',
    label_key='modules.stats.mean.label',
    description='Calculate arithmetic mean of numbers',
    description_key='modules.stats.mean.description',
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
            label_key='modules.stats.mean.params.numbers.label',
            description='Array of numbers',
            description_key='modules.stats.mean.params.numbers.description',
            required=True,
            placeholder='[1, 2, 3, 4, 5]',
            group=FieldGroup.BASIC,
        ),
        field(
            'precision',
            type='number',
            label='Precision',
            label_key='modules.stats.mean.params.precision.label',
            description='Decimal places',
            description_key='modules.stats.mean.params.precision.description',
            default=2,
            min=0,
            max=10,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'mean': {
            'type': 'number',
            'description': 'Arithmetic mean',
            'description_key': 'modules.stats.mean.output.mean.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of values',
            'description_key': 'modules.stats.mean.output.count.description'
        },
        'sum': {
            'type': 'number',
            'description': 'Sum of values',
            'description_key': 'modules.stats.mean.output.sum.description'
        }
    },
    timeout_ms=5000,
)
async def stats_mean(context: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate arithmetic mean of numbers."""
    params = context['params']
    numbers = params.get('numbers')
    precision = params.get('precision', 2)

    if numbers is None:
        raise ValidationError("Missing required parameter: numbers", field="numbers")

    if not isinstance(numbers, list):
        raise ValidationError("Parameter must be an array", field="numbers")

    # Filter to only numbers
    valid_numbers = [n for n in numbers if isinstance(n, (int, float))]

    if len(valid_numbers) == 0:
        raise ValidationError("Array must contain at least one number", field="numbers")

    total = sum(valid_numbers)
    mean = round(total / len(valid_numbers), int(precision))

    return {
        'ok': True,
        'data': {
            'mean': mean,
            'count': len(valid_numbers),
            'sum': total
        }
    }
