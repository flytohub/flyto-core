"""
Convert To Boolean Module
Convert value to boolean.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


@register_module(
    module_id='convert.to_boolean',
    version='1.0.0',
    category='convert',
    tags=['convert', 'boolean', 'cast', 'type', 'transform'],
    label='To Boolean',
    label_key='modules.convert.to_boolean.label',
    description='Convert value to boolean',
    description_key='modules.convert.to_boolean.description',
    icon='ToggleLeft',
    color='#06B6D4',
    input_types=['any'],
    output_types=['boolean'],

    can_receive_from=['*'],
    can_connect_to=['logic.*', 'flow.*', 'data.*'],

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
            label_key='modules.convert.to_boolean.params.value.label',
            description='Value to convert',
            description_key='modules.convert.to_boolean.params.value.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'strict',
            type='boolean',
            label='Strict Mode',
            label_key='modules.convert.to_boolean.params.strict.label',
            description='Only accept true/false strings',
            description_key='modules.convert.to_boolean.params.strict.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'boolean',
            'description': 'Converted boolean',
            'description_key': 'modules.convert.to_boolean.output.result.description'
        },
        'original_type': {
            'type': 'string',
            'description': 'Original value type',
            'description_key': 'modules.convert.to_boolean.output.original_type.description'
        }
    },
    timeout_ms=5000,
)
async def convert_to_boolean(context: Dict[str, Any]) -> Dict[str, Any]:
    """Convert value to boolean."""
    params = context['params']
    value = params.get('value')
    strict = params.get('strict', False)

    original_type = type(value).__name__ if value is not None else 'null'

    if value is None:
        result = False
    elif isinstance(value, bool):
        result = value
    elif isinstance(value, (int, float)):
        result = value != 0
    elif isinstance(value, str):
        lower = value.lower().strip()
        if strict:
            result = lower == 'true'
        else:
            # Truthy strings
            result = lower in ('true', '1', 'yes', 'on', 'y')
    elif isinstance(value, (list, dict)):
        result = len(value) > 0
    else:
        result = bool(value)

    return {
        'ok': True,
        'data': {
            'result': result,
            'original_type': original_type
        }
    }
