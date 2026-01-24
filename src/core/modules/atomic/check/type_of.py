"""
Check Type Of Module
Get the type of a value.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


@register_module(
    module_id='check.type_of',
    version='1.0.0',
    category='check',
    tags=['check', 'type', 'typeof', 'validate', 'condition', 'advanced'],
    label='Type Of',
    label_key='modules.check.type_of.label',
    description='Get the type of a value',
    description_key='modules.check.type_of.description',
    icon='HelpCircle',
    color='#F97316',
    input_types=['any'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['flow.*', 'logic.*', 'data.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'value',
            type='any',
            label='Value',
            label_key='modules.check.type_of.params.value.label',
            description='Value to check',
            description_key='modules.check.type_of.params.value.description',
            required=False,
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'type': {
            'type': 'string',
            'description': 'Type name',
            'description_key': 'modules.check.type_of.output.type.description'
        },
        'is_primitive': {
            'type': 'boolean',
            'description': 'Whether type is primitive',
            'description_key': 'modules.check.type_of.output.is_primitive.description'
        }
    },
    timeout_ms=5000,
)
async def check_type_of(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get the type of a value."""
    params = context['params']
    value = params.get('value')

    # Map Python types to JavaScript-like type names
    if value is None:
        type_name = 'null'
    elif isinstance(value, bool):
        type_name = 'boolean'
    elif isinstance(value, int):
        type_name = 'integer'
    elif isinstance(value, float):
        type_name = 'number'
    elif isinstance(value, str):
        type_name = 'string'
    elif isinstance(value, list):
        type_name = 'array'
    elif isinstance(value, dict):
        type_name = 'object'
    else:
        type_name = type(value).__name__

    primitives = {'null', 'boolean', 'integer', 'number', 'string'}
    is_primitive = type_name in primitives

    return {
        'ok': True,
        'data': {
            'type': type_name,
            'is_primitive': is_primitive
        }
    }
