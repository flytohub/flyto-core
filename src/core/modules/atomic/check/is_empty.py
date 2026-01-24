"""
Check Is Empty Module
Check if a value is empty.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


@register_module(
    module_id='check.is_empty',
    version='1.0.0',
    category='check',
    tags=['check', 'empty', 'validate', 'condition', 'advanced'],
    label='Is Empty',
    label_key='modules.check.is_empty.label',
    description='Check if a value is empty',
    description_key='modules.check.is_empty.description',
    icon='Circle',
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
            label_key='modules.check.is_empty.params.value.label',
            description='Value to check',
            description_key='modules.check.is_empty.params.value.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'trim_strings',
            type='boolean',
            label='Trim Strings',
            label_key='modules.check.is_empty.params.trim_strings.label',
            description='Treat whitespace-only strings as empty',
            description_key='modules.check.is_empty.params.trim_strings.description',
            default=True,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'is_empty': {
            'type': 'boolean',
            'description': 'Whether value is empty',
            'description_key': 'modules.check.is_empty.output.is_empty.description'
        },
        'type': {
            'type': 'string',
            'description': 'Type of value',
            'description_key': 'modules.check.is_empty.output.type.description'
        }
    },
    timeout_ms=5000,
)
async def check_is_empty(context: Dict[str, Any]) -> Dict[str, Any]:
    """Check if a value is empty."""
    params = context['params']
    value = params.get('value')
    trim_strings = params.get('trim_strings', True)

    value_type = type(value).__name__

    if value is None:
        is_empty = True
    elif isinstance(value, bool):
        is_empty = False  # Booleans are never "empty"
    elif isinstance(value, str):
        is_empty = len(value.strip() if trim_strings else value) == 0
    elif isinstance(value, (list, dict, set, tuple)):
        is_empty = len(value) == 0
    elif isinstance(value, (int, float)):
        is_empty = False  # Numbers are never "empty"
    else:
        is_empty = not bool(value)

    return {
        'ok': True,
        'data': {
            'is_empty': is_empty,
            'type': value_type
        }
    }
