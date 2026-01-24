"""
Check Is Object Module
Check if a value is an object (dict).
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


@register_module(
    module_id='check.is_object',
    version='1.0.0',
    category='check',
    tags=['check', 'object', 'dict', 'validate', 'condition', 'advanced'],
    label='Is Object',
    label_key='modules.check.is_object.label',
    description='Check if a value is an object',
    description_key='modules.check.is_object.description',
    icon='Braces',
    color='#F97316',
    input_types=['any'],
    output_types=['boolean'],

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
            label_key='modules.check.is_object.params.value.label',
            description='Value to check',
            description_key='modules.check.is_object.params.value.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'is_object': {
            'type': 'boolean',
            'description': 'Whether value is an object',
            'description_key': 'modules.check.is_object.output.is_object.description'
        },
        'keys': {
            'type': 'array',
            'description': 'Object keys (if object)',
            'description_key': 'modules.check.is_object.output.keys.description'
        }
    },
    timeout_ms=5000,
)
async def check_is_object(context: Dict[str, Any]) -> Dict[str, Any]:
    """Check if a value is an object."""
    params = context['params']
    value = params.get('value')

    is_object = isinstance(value, dict)
    keys = list(value.keys()) if is_object else []

    return {
        'ok': True,
        'data': {
            'is_object': is_object,
            'keys': keys
        }
    }
