"""
Check Is Number Module
Check if a value is a number.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


@register_module(
    module_id='check.is_number',
    version='1.0.0',
    category='check',
    tags=['check', 'number', 'numeric', 'validate', 'condition', 'advanced'],
    label='Is Number',
    label_key='modules.check.is_number.label',
    description='Check if a value is a number',
    description_key='modules.check.is_number.description',
    icon='Hash',
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
            label_key='modules.check.is_number.params.value.label',
            description='Value to check',
            description_key='modules.check.is_number.params.value.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'parse_string',
            type='boolean',
            label='Parse String',
            label_key='modules.check.is_number.params.parse_string.label',
            description='Consider numeric strings as numbers',
            description_key='modules.check.is_number.params.parse_string.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'integer_only',
            type='boolean',
            label='Integer Only',
            label_key='modules.check.is_number.params.integer_only.label',
            description='Only accept integers',
            description_key='modules.check.is_number.params.integer_only.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'is_number': {
            'type': 'boolean',
            'description': 'Whether value is a number',
            'description_key': 'modules.check.is_number.output.is_number.description'
        },
        'is_integer': {
            'type': 'boolean',
            'description': 'Whether value is an integer',
            'description_key': 'modules.check.is_number.output.is_integer.description'
        },
        'is_float': {
            'type': 'boolean',
            'description': 'Whether value is a float',
            'description_key': 'modules.check.is_number.output.is_float.description'
        }
    },
    timeout_ms=5000,
)
async def check_is_number(context: Dict[str, Any]) -> Dict[str, Any]:
    """Check if a value is a number."""
    params = context['params']
    value = params.get('value')
    parse_string = params.get('parse_string', False)
    integer_only = params.get('integer_only', False)

    is_number = False
    is_integer = False
    is_float = False

    if isinstance(value, bool):
        # Booleans are not numbers in this context
        pass
    elif isinstance(value, int):
        is_number = True
        is_integer = True
    elif isinstance(value, float):
        is_number = True
        is_float = True
        is_integer = value.is_integer()
    elif isinstance(value, str) and parse_string:
        try:
            parsed = float(value)
            is_number = True
            is_float = '.' in value
            is_integer = parsed.is_integer()
        except (ValueError, TypeError):
            pass

    if integer_only and not is_integer:
        is_number = False

    return {
        'ok': True,
        'data': {
            'is_number': is_number,
            'is_integer': is_integer,
            'is_float': is_float
        }
    }
