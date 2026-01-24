"""
Statistics Min/Max Module
Find minimum and maximum values in array.
"""
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='stats.min_max',
    version='1.0.0',
    category='stats',
    tags=['stats', 'min', 'max', 'range', 'math', 'advanced'],
    label='Min/Max',
    label_key='modules.stats.min_max.label',
    description='Find minimum and maximum values',
    description_key='modules.stats.min_max.description',
    icon='ArrowUpDown',
    color='#3B82F6',
    input_types=['array'],
    output_types=['object'],

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
            label_key='modules.stats.min_max.params.numbers.label',
            description='Array of numbers',
            description_key='modules.stats.min_max.params.numbers.description',
            required=True,
            placeholder='[3, 1, 4, 1, 5, 9, 2, 6]',
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'min': {
            'type': 'number',
            'description': 'Minimum value',
            'description_key': 'modules.stats.min_max.output.min.description'
        },
        'max': {
            'type': 'number',
            'description': 'Maximum value',
            'description_key': 'modules.stats.min_max.output.max.description'
        },
        'range': {
            'type': 'number',
            'description': 'Range (max - min)',
            'description_key': 'modules.stats.min_max.output.range.description'
        },
        'min_index': {
            'type': 'number',
            'description': 'Index of minimum',
            'description_key': 'modules.stats.min_max.output.min_index.description'
        },
        'max_index': {
            'type': 'number',
            'description': 'Index of maximum',
            'description_key': 'modules.stats.min_max.output.max_index.description'
        }
    },
    timeout_ms=5000,
)
async def stats_min_max(context: Dict[str, Any]) -> Dict[str, Any]:
    """Find minimum and maximum values."""
    params = context['params']
    numbers = params.get('numbers')

    if numbers is None:
        raise ValidationError("Missing required parameter: numbers", field="numbers")

    if not isinstance(numbers, list):
        raise ValidationError("Parameter must be an array", field="numbers")

    valid_numbers = [(i, n) for i, n in enumerate(numbers) if isinstance(n, (int, float))]

    if len(valid_numbers) == 0:
        raise ValidationError("Array must contain at least one number", field="numbers")

    min_idx, min_val = min(valid_numbers, key=lambda x: x[1])
    max_idx, max_val = max(valid_numbers, key=lambda x: x[1])

    return {
        'ok': True,
        'data': {
            'min': min_val,
            'max': max_val,
            'range': max_val - min_val,
            'min_index': min_idx,
            'max_index': max_idx
        }
    }
