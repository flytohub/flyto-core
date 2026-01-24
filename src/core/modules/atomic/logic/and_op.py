"""
Logic AND Module
Perform logical AND operation
"""
from typing import Any, Dict, List

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='logic.and',
    version='1.0.0',
    category='logic',
    tags=['logic', 'and', 'boolean', 'condition'],
    label='Logic AND',
    label_key='modules.logic.and.label',
    description='Perform logical AND operation',
    description_key='modules.logic.and.description',
    icon='GitMerge',
    color='#14B8A6',
    input_types=['boolean', 'array'],
    output_types=['boolean'],

    can_receive_from=['*'],
    can_connect_to=['flow.*', 'data.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'values': {
            'type': 'array',
            'label': 'Values',
            'label_key': 'modules.logic.and.params.values.label',
            'description': 'Boolean values to AND together',
            'description_key': 'modules.logic.and.params.values.description',
            'placeholder': '[true, true, false]',
            'required': True
        }
    },
    output_schema={
        'result': {
            'type': 'boolean',
            'description': 'Result of AND operation',
            'description_key': 'modules.logic.and.output.result.description'
        },
        'true_count': {
            'type': 'number',
            'description': 'Number of true values',
            'description_key': 'modules.logic.and.output.true_count.description'
        },
        'total_count': {
            'type': 'number',
            'description': 'Total number of values',
            'description_key': 'modules.logic.and.output.total_count.description'
        }
    },
    timeout_ms=5000,
)
async def logic_and(context: Dict[str, Any]) -> Dict[str, Any]:
    """Perform logical AND operation."""
    params = context['params']
    values = params.get('values')

    if values is None:
        raise ValidationError("Missing required parameter: values", field="values")

    if not isinstance(values, list):
        values = [values]

    bool_values = [bool(v) for v in values]
    result = all(bool_values) if bool_values else True
    true_count = sum(1 for v in bool_values if v)

    return {
        'ok': True,
        'data': {
            'result': result,
            'true_count': true_count,
            'total_count': len(bool_values)
        }
    }
