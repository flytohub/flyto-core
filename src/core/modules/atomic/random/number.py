"""
Random Number Module
Generate random number within a range.
"""
from typing import Any, Dict
import random

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='random.number',
    version='1.0.0',
    category='random',
    tags=['random', 'number', 'generate', 'integer', 'float'],
    label='Random Number',
    label_key='modules.random.number.label',
    description='Generate random number within a range',
    description_key='modules.random.number.description',
    icon='Hash',
    color='#F59E0B',
    input_types=[],
    output_types=['number'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'math.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'min',
            type='number',
            label='Minimum',
            label_key='modules.random.number.params.min.label',
            description='Minimum value (inclusive)',
            description_key='modules.random.number.params.min.description',
            default=0,
            group=FieldGroup.BASIC,
        ),
        field(
            'max',
            type='number',
            label='Maximum',
            label_key='modules.random.number.params.max.label',
            description='Maximum value (inclusive)',
            description_key='modules.random.number.params.max.description',
            default=100,
            group=FieldGroup.BASIC,
        ),
        field(
            'integer',
            type='boolean',
            label='Integer Only',
            label_key='modules.random.number.params.integer.label',
            description='Generate integers only',
            description_key='modules.random.number.params.integer.description',
            default=True,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'precision',
            type='number',
            label='Decimal Precision',
            label_key='modules.random.number.params.precision.label',
            description='Decimal places for float',
            description_key='modules.random.number.params.precision.description',
            default=2,
            min=0,
            max=10,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'number': {
            'type': 'number',
            'description': 'Generated random number',
            'description_key': 'modules.random.number.output.number.description'
        },
        'min': {
            'type': 'number',
            'description': 'Minimum bound used',
            'description_key': 'modules.random.number.output.min.description'
        },
        'max': {
            'type': 'number',
            'description': 'Maximum bound used',
            'description_key': 'modules.random.number.output.max.description'
        }
    },
    timeout_ms=5000,
)
async def random_number(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate random number within a range."""
    params = context['params']
    min_val = params.get('min', 0)
    max_val = params.get('max', 100)
    integer = params.get('integer', True)
    precision = params.get('precision', 2)

    min_val = float(min_val)
    max_val = float(max_val)

    if min_val > max_val:
        raise ValidationError("Minimum cannot be greater than maximum", field="min")

    if integer:
        result = random.randint(int(min_val), int(max_val))
    else:
        result = round(random.uniform(min_val, max_val), int(precision))

    return {
        'ok': True,
        'data': {
            'number': result,
            'min': min_val,
            'max': max_val
        }
    }
