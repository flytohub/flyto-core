"""
Statistics Percentile Module
Calculate percentile of numbers.
"""
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='stats.percentile',
    version='1.0.0',
    category='stats',
    tags=['stats', 'percentile', 'quantile', 'math', 'advanced'],
    label='Percentile',
    label_key='modules.stats.percentile.label',
    description='Calculate percentile of numbers',
    description_key='modules.stats.percentile.description',
    icon='Percent',
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
            label_key='modules.stats.percentile.params.numbers.label',
            description='Array of numbers',
            description_key='modules.stats.percentile.params.numbers.description',
            required=True,
            placeholder='[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]',
            group=FieldGroup.BASIC,
        ),
        field(
            'percentile',
            type='number',
            label='Percentile',
            label_key='modules.stats.percentile.params.percentile.label',
            description='Percentile to calculate (0-100)',
            description_key='modules.stats.percentile.params.percentile.description',
            required=True,
            default=50,
            min=0,
            max=100,
            placeholder='50',
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'value': {
            'type': 'number',
            'description': 'Percentile value',
            'description_key': 'modules.stats.percentile.output.value.description'
        },
        'percentile': {
            'type': 'number',
            'description': 'Percentile requested',
            'description_key': 'modules.stats.percentile.output.percentile.description'
        }
    },
    timeout_ms=5000,
)
async def stats_percentile(context: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate percentile of numbers."""
    params = context['params']
    numbers = params.get('numbers')
    percentile = params.get('percentile', 50)

    if numbers is None:
        raise ValidationError("Missing required parameter: numbers", field="numbers")

    if not isinstance(numbers, list):
        raise ValidationError("Parameter must be an array", field="numbers")

    valid_numbers = sorted([n for n in numbers if isinstance(n, (int, float))])
    n = len(valid_numbers)

    if n == 0:
        raise ValidationError("Array must contain at least one number", field="numbers")

    percentile = float(percentile)
    if percentile < 0 or percentile > 100:
        raise ValidationError("Percentile must be between 0 and 100", field="percentile")

    # Linear interpolation method
    k = (n - 1) * (percentile / 100)
    f = int(k)
    c = f + 1 if f + 1 < n else f

    if f == c:
        value = valid_numbers[f]
    else:
        value = valid_numbers[f] + (k - f) * (valid_numbers[c] - valid_numbers[f])

    return {
        'ok': True,
        'data': {
            'value': value,
            'percentile': percentile
        }
    }
