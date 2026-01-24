"""
Convert To Number Module
Convert value to number.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='convert.to_number',
    version='1.0.0',
    category='convert',
    tags=['convert', 'number', 'cast', 'type', 'transform'],
    label='To Number',
    label_key='modules.convert.to_number.label',
    description='Convert value to number',
    description_key='modules.convert.to_number.description',
    icon='Hash',
    color='#06B6D4',
    input_types=['any'],
    output_types=['number'],

    can_receive_from=['*'],
    can_connect_to=['math.*', 'data.*', 'flow.*'],

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
            label_key='modules.convert.to_number.params.value.label',
            description='Value to convert',
            description_key='modules.convert.to_number.params.value.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'default',
            type='number',
            label='Default',
            label_key='modules.convert.to_number.params.default.label',
            description='Default value if conversion fails',
            description_key='modules.convert.to_number.params.default.description',
            default=0,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'integer',
            type='boolean',
            label='Integer',
            label_key='modules.convert.to_number.params.integer.label',
            description='Convert to integer',
            description_key='modules.convert.to_number.params.integer.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'number',
            'description': 'Converted number',
            'description_key': 'modules.convert.to_number.output.result.description'
        },
        'success': {
            'type': 'boolean',
            'description': 'Whether conversion succeeded',
            'description_key': 'modules.convert.to_number.output.success.description'
        },
        'original_type': {
            'type': 'string',
            'description': 'Original value type',
            'description_key': 'modules.convert.to_number.output.original_type.description'
        }
    },
    timeout_ms=5000,
)
async def convert_to_number(context: Dict[str, Any]) -> Dict[str, Any]:
    """Convert value to number."""
    params = context['params']
    value = params.get('value')
    default = params.get('default', 0)
    integer = params.get('integer', False)

    original_type = type(value).__name__ if value is not None else 'null'
    success = True

    try:
        if value is None:
            result = default
            success = False
        elif isinstance(value, bool):
            result = 1 if value else 0
        elif isinstance(value, (int, float)):
            result = value
        elif isinstance(value, str):
            value = value.strip()
            if value == '':
                result = default
                success = False
            else:
                result = float(value)
        elif isinstance(value, list):
            result = len(value)
        else:
            result = default
            success = False
    except (ValueError, TypeError):
        result = default
        success = False

    if integer and success:
        result = int(result)

    return {
        'ok': True,
        'data': {
            'result': result,
            'success': success,
            'original_type': original_type
        }
    }
