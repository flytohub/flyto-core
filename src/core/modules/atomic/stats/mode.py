"""
Statistics Mode Module
Calculate mode (most frequent value) of data.
"""
from typing import Any, Dict, List
from collections import Counter

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='stats.mode',
    version='1.0.0',
    category='stats',
    tags=['stats', 'mode', 'frequency', 'math', 'advanced'],
    label='Mode',
    label_key='modules.stats.mode.label',
    description='Calculate mode (most frequent value)',
    description_key='modules.stats.mode.description',
    icon='Calculator',
    color='#3B82F6',
    input_types=['array'],
    output_types=['any'],

    can_receive_from=['*'],
    can_connect_to=['math.*', 'data.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'values',
            type='array',
            label='Values',
            label_key='modules.stats.mode.params.values.label',
            description='Array of values',
            description_key='modules.stats.mode.params.values.description',
            required=True,
            placeholder='[1, 2, 2, 3, 3, 3]',
            group=FieldGroup.BASIC,
        ),
        field(
            'all_modes',
            type='boolean',
            label='Return All Modes',
            label_key='modules.stats.mode.params.all_modes.label',
            description='Return all modes if multiple exist',
            description_key='modules.stats.mode.params.all_modes.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'mode': {
            'type': 'any',
            'description': 'Most frequent value(s)',
            'description_key': 'modules.stats.mode.output.mode.description'
        },
        'frequency': {
            'type': 'number',
            'description': 'Frequency of mode',
            'description_key': 'modules.stats.mode.output.frequency.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of values',
            'description_key': 'modules.stats.mode.output.count.description'
        }
    },
    timeout_ms=5000,
)
async def stats_mode(context: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate mode of values."""
    params = context['params']
    values = params.get('values')
    all_modes = params.get('all_modes', False)

    if values is None:
        raise ValidationError("Missing required parameter: values", field="values")

    if not isinstance(values, list):
        raise ValidationError("Parameter must be an array", field="values")

    if len(values) == 0:
        raise ValidationError("Array cannot be empty", field="values")

    # Convert unhashable types to strings for counting
    def make_hashable(v):
        if isinstance(v, (list, dict)):
            return str(v)
        return v

    hashable_values = [make_hashable(v) for v in values]
    counter = Counter(hashable_values)
    max_freq = max(counter.values())

    modes = [v for v, freq in counter.items() if freq == max_freq]

    if all_modes:
        mode = modes
    else:
        mode = modes[0]

    return {
        'ok': True,
        'data': {
            'mode': mode,
            'frequency': max_freq,
            'count': len(values)
        }
    }
