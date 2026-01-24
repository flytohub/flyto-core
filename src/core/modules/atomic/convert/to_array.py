"""
Convert To Array Module
Convert value to array.
"""
from typing import Any, Dict
import json

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='convert.to_array',
    version='1.0.0',
    category='convert',
    tags=['convert', 'array', 'list', 'cast', 'type', 'transform'],
    label='To Array',
    label_key='modules.convert.to_array.label',
    description='Convert value to array',
    description_key='modules.convert.to_array.description',
    icon='List',
    color='#06B6D4',
    input_types=['any'],
    output_types=['array'],

    can_receive_from=['*'],
    can_connect_to=['array.*', 'data.*', 'flow.*'],

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
            label_key='modules.convert.to_array.params.value.label',
            description='Value to convert',
            description_key='modules.convert.to_array.params.value.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'split_string',
            type='boolean',
            label='Split String',
            label_key='modules.convert.to_array.params.split_string.label',
            description='Split string into characters',
            description_key='modules.convert.to_array.params.split_string.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'delimiter',
            type='string',
            label='Delimiter',
            label_key='modules.convert.to_array.params.delimiter.label',
            description='Delimiter for string splitting',
            description_key='modules.convert.to_array.params.delimiter.description',
            default='',
            placeholder=',',
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'array',
            'description': 'Converted array',
            'description_key': 'modules.convert.to_array.output.result.description'
        },
        'length': {
            'type': 'number',
            'description': 'Array length',
            'description_key': 'modules.convert.to_array.output.length.description'
        },
        'original_type': {
            'type': 'string',
            'description': 'Original value type',
            'description_key': 'modules.convert.to_array.output.original_type.description'
        }
    },
    timeout_ms=5000,
)
async def convert_to_array(context: Dict[str, Any]) -> Dict[str, Any]:
    """Convert value to array."""
    params = context['params']
    value = params.get('value')
    split_string = params.get('split_string', False)
    delimiter = params.get('delimiter', '')

    original_type = type(value).__name__ if value is not None else 'null'

    if value is None:
        result = []
    elif isinstance(value, list):
        result = value
    elif isinstance(value, dict):
        result = list(value.items())
    elif isinstance(value, str):
        if split_string:
            if delimiter:
                result = value.split(delimiter)
            else:
                result = list(value)
        else:
            # Try to parse as JSON array
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    result = parsed
                else:
                    result = [value]
            except (json.JSONDecodeError, ValueError):
                result = [value]
    else:
        result = [value]

    return {
        'ok': True,
        'data': {
            'result': result,
            'length': len(result),
            'original_type': original_type
        }
    }
