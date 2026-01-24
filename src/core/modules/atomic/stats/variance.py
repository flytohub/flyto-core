"""
Statistics Variance Module
Calculate variance of numbers.
"""
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='stats.variance',
    version='1.0.0',
    category='stats',
    tags=['stats', 'variance', 'dispersion', 'math', 'advanced'],
    label='Variance',
    label_key='modules.stats.variance.label',
    description='Calculate variance of numbers',
    description_key='modules.stats.variance.description',
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
            label_key='modules.stats.variance.params.numbers.label',
            description='Array of numbers',
            description_key='modules.stats.variance.params.numbers.description',
            required=True,
            placeholder='[2, 4, 4, 4, 5, 5, 7, 9]',
            group=FieldGroup.BASIC,
        ),
        field(
            'population',
            type='boolean',
            label='Population',
            label_key='modules.stats.variance.params.population.label',
            description='Use population formula',
            description_key='modules.stats.variance.params.population.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'precision',
            type='number',
            label='Precision',
            label_key='modules.stats.variance.params.precision.label',
            description='Decimal places',
            description_key='modules.stats.variance.params.precision.description',
            default=4,
            min=0,
            max=10,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'variance': {
            'type': 'number',
            'description': 'Variance value',
            'description_key': 'modules.stats.variance.output.variance.description'
        },
        'mean': {
            'type': 'number',
            'description': 'Mean value',
            'description_key': 'modules.stats.variance.output.mean.description'
        }
    },
    timeout_ms=5000,
)
async def stats_variance(context: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate variance of numbers."""
    params = context['params']
    numbers = params.get('numbers')
    population = params.get('population', False)
    precision = params.get('precision', 4)

    if numbers is None:
        raise ValidationError("Missing required parameter: numbers", field="numbers")

    if not isinstance(numbers, list):
        raise ValidationError("Parameter must be an array", field="numbers")

    valid_numbers = [n for n in numbers if isinstance(n, (int, float))]
    n = len(valid_numbers)

    if n == 0:
        raise ValidationError("Array must contain at least one number", field="numbers")

    if n == 1 and not population:
        raise ValidationError("Sample variance requires at least 2 numbers", field="numbers")

    mean = sum(valid_numbers) / n
    squared_diff_sum = sum((x - mean) ** 2 for x in valid_numbers)

    if population:
        variance = squared_diff_sum / n
    else:
        variance = squared_diff_sum / (n - 1)

    return {
        'ok': True,
        'data': {
            'variance': round(variance, int(precision)),
            'mean': round(mean, int(precision))
        }
    }
