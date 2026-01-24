"""
Check Is String Module
Check if a value is a string.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


@register_module(
    module_id='check.is_string',
    version='1.0.0',
    category='check',
    tags=['check', 'string', 'text', 'validate', 'condition', 'advanced'],
    label='Is String',
    label_key='modules.check.is_string.label',
    description='Check if a value is a string',
    description_key='modules.check.is_string.description',
    icon='Type',
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
            label_key='modules.check.is_string.params.value.label',
            description='Value to check',
            description_key='modules.check.is_string.params.value.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'is_string': {
            'type': 'boolean',
            'description': 'Whether value is a string',
            'description_key': 'modules.check.is_string.output.is_string.description'
        },
        'length': {
            'type': 'number',
            'description': 'String length (if string)',
            'description_key': 'modules.check.is_string.output.length.description'
        }
    },
    timeout_ms=5000,
)
async def check_is_string(context: Dict[str, Any]) -> Dict[str, Any]:
    """Check if a value is a string."""
    params = context['params']
    value = params.get('value')

    is_string = isinstance(value, str)
    length = len(value) if is_string else 0

    return {
        'ok': True,
        'data': {
            'is_string': is_string,
            'length': length
        }
    }
