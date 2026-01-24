"""
Convert To String Module
Convert any value to string representation.
"""
from typing import Any, Dict
import json

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='convert.to_string',
    version='1.0.0',
    category='convert',
    tags=['convert', 'string', 'cast', 'type', 'transform'],
    label='To String',
    label_key='modules.convert.to_string.label',
    description='Convert any value to string',
    description_key='modules.convert.to_string.description',
    icon='Type',
    color='#06B6D4',
    input_types=['any'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['string.*', 'data.*', 'flow.*'],

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
            label_key='modules.convert.to_string.params.value.label',
            description='Value to convert',
            description_key='modules.convert.to_string.params.value.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'pretty',
            type='boolean',
            label='Pretty Print',
            label_key='modules.convert.to_string.params.pretty.label',
            description='Format objects/arrays with indentation',
            description_key='modules.convert.to_string.params.pretty.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'string',
            'description': 'String representation',
            'description_key': 'modules.convert.to_string.output.result.description'
        },
        'original_type': {
            'type': 'string',
            'description': 'Original value type',
            'description_key': 'modules.convert.to_string.output.original_type.description'
        }
    },
    timeout_ms=5000,
)
async def convert_to_string(context: Dict[str, Any]) -> Dict[str, Any]:
    """Convert any value to string."""
    params = context['params']
    value = params.get('value')
    pretty = params.get('pretty', False)

    if value is None:
        result = ''
        original_type = 'null'
    elif isinstance(value, bool):
        result = 'true' if value else 'false'
        original_type = 'boolean'
    elif isinstance(value, (int, float)):
        result = str(value)
        original_type = 'number'
    elif isinstance(value, str):
        result = value
        original_type = 'string'
    elif isinstance(value, (list, dict)):
        if pretty:
            result = json.dumps(value, indent=2, ensure_ascii=False)
        else:
            result = json.dumps(value, ensure_ascii=False)
        original_type = 'array' if isinstance(value, list) else 'object'
    else:
        result = str(value)
        original_type = type(value).__name__

    return {
        'ok': True,
        'data': {
            'result': result,
            'original_type': original_type
        }
    }
