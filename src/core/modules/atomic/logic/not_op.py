"""
Logic NOT Module
Perform logical NOT operation
"""
from typing import Any, Dict

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='logic.not',
    version='1.0.0',
    category='logic',
    tags=['logic', 'not', 'negate', 'boolean', 'condition'],
    label='Logic NOT',
    label_key='modules.logic.not.label',
    description='Perform logical NOT operation',
    description_key='modules.logic.not.description',
    icon='XCircle',
    color='#14B8A6',
    input_types=['boolean'],
    output_types=['boolean'],

    can_receive_from=['*'],
    can_connect_to=['flow.*', 'data.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'value': {
            'type': 'boolean',
            'label': 'Value',
            'label_key': 'modules.logic.not.params.value.label',
            'description': 'Boolean value to negate',
            'description_key': 'modules.logic.not.params.value.description',
            'default': False,
            'required': True
        }
    },
    output_schema={
        'result': {
            'type': 'boolean',
            'description': 'Negated result',
            'description_key': 'modules.logic.not.output.result.description'
        },
        'original': {
            'type': 'boolean',
            'description': 'Original value',
            'description_key': 'modules.logic.not.output.original.description'
        }
    },
    timeout_ms=5000,
)
async def logic_not(context: Dict[str, Any]) -> Dict[str, Any]:
    """Perform logical NOT operation."""
    params = context['params']
    value = params.get('value')

    if value is None:
        raise ValidationError("Missing required parameter: value", field="value")

    bool_value = bool(value)
    result = not bool_value

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': bool_value
        }
    }
