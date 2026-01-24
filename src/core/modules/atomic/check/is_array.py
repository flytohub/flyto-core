"""
Check Is Array Module
Check if a value is an array.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


@register_module(
    module_id='check.is_array',
    version='1.0.0',
    category='check',
    tags=['check', 'array', 'list', 'validate', 'condition', 'advanced'],
    label='Is Array',
    label_key='modules.check.is_array.label',
    description='Check if a value is an array',
    description_key='modules.check.is_array.description',
    icon='List',
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
            label_key='modules.check.is_array.params.value.label',
            description='Value to check',
            description_key='modules.check.is_array.params.value.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'is_array': {
            'type': 'boolean',
            'description': 'Whether value is an array',
            'description_key': 'modules.check.is_array.output.is_array.description'
        },
        'length': {
            'type': 'number',
            'description': 'Array length (if array)',
            'description_key': 'modules.check.is_array.output.length.description'
        }
    },
    timeout_ms=5000,
)
async def check_is_array(context: Dict[str, Any]) -> Dict[str, Any]:
    """Check if a value is an array."""
    params = context['params']
    value = params.get('value')

    is_array = isinstance(value, list)
    length = len(value) if is_array else 0

    return {
        'ok': True,
        'data': {
            'is_array': is_array,
            'length': length
        }
    }
