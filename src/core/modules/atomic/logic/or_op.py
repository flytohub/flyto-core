"""
Logic OR Module
Perform logical OR operation
"""
from typing import Any, Dict, List

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='logic.or',
    version='1.0.0',
    category='logic',
    tags=['logic', 'or', 'boolean', 'condition'],
    label='Logic OR',
    label_key='modules.logic.or.label',
    description='Perform logical OR operation',
    description_key='modules.logic.or.description',
    icon='GitBranch',
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
            'label_key': 'modules.logic.or.params.values.label',
            'description': 'Boolean values to OR together',
            'description_key': 'modules.logic.or.params.values.description',
            'placeholder': '[true, false, false]',
            'required': True
        }
    },
    output_schema={
        'result': {
            'type': 'boolean',
            'description': 'Result of OR operation',
            'description_key': 'modules.logic.or.output.result.description'
        },
        'true_count': {
            'type': 'number',
            'description': 'Number of true values',
            'description_key': 'modules.logic.or.output.true_count.description'
        },
        'total_count': {
            'type': 'number',
            'description': 'Total number of values',
            'description_key': 'modules.logic.or.output.total_count.description'
        }
    },
    timeout_ms=5000,
)
async def logic_or(context: Dict[str, Any]) -> Dict[str, Any]:
    """Perform logical OR operation."""
    params = context['params']
    values = params.get('values')

    if values is None:
        raise ValidationError("Missing required parameter: values", field="values")

    if not isinstance(values, list):
        values = [values]

    bool_values = [bool(v) for v in values]
    result = any(bool_values) if bool_values else False
    true_count = sum(1 for v in bool_values if v)

    return {
        'ok': True,
        'data': {
            'result': result,
            'true_count': true_count,
            'total_count': len(bool_values)
        }
    }
