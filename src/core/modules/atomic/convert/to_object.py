"""
Convert To Object Module
Convert value to object (dictionary).
"""
from typing import Any, Dict
import json

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='convert.to_object',
    version='1.0.0',
    category='convert',
    tags=['convert', 'object', 'dict', 'cast', 'type', 'transform'],
    label='To Object',
    label_key='modules.convert.to_object.label',
    description='Convert value to object',
    description_key='modules.convert.to_object.description',
    icon='Braces',
    color='#06B6D4',
    input_types=['any'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['object.*', 'data.*', 'flow.*'],

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
            label_key='modules.convert.to_object.params.value.label',
            description='Value to convert',
            description_key='modules.convert.to_object.params.value.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'key_name',
            type='string',
            label='Key Name',
            label_key='modules.convert.to_object.params.key_name.label',
            description='Key name for wrapping non-objects',
            description_key='modules.convert.to_object.params.key_name.description',
            default='value',
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'object',
            'description': 'Converted object',
            'description_key': 'modules.convert.to_object.output.result.description'
        },
        'keys': {
            'type': 'array',
            'description': 'Object keys',
            'description_key': 'modules.convert.to_object.output.keys.description'
        },
        'original_type': {
            'type': 'string',
            'description': 'Original value type',
            'description_key': 'modules.convert.to_object.output.original_type.description'
        }
    },
    timeout_ms=5000,
)
async def convert_to_object(context: Dict[str, Any]) -> Dict[str, Any]:
    """Convert value to object."""
    params = context['params']
    value = params.get('value')
    key_name = params.get('key_name', 'value')

    original_type = type(value).__name__ if value is not None else 'null'

    if value is None:
        result = {}
    elif isinstance(value, dict):
        result = value
    elif isinstance(value, list):
        # Convert list of pairs to object
        if all(isinstance(item, (list, tuple)) and len(item) == 2 for item in value):
            result = dict(value)
        else:
            # Index-based object
            result = {str(i): item for i, item in enumerate(value)}
    elif isinstance(value, str):
        # Try to parse as JSON object
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                result = parsed
            else:
                result = {key_name: value}
        except (json.JSONDecodeError, ValueError):
            result = {key_name: value}
    else:
        result = {key_name: value}

    return {
        'ok': True,
        'data': {
            'result': result,
            'keys': list(result.keys()),
            'original_type': original_type
        }
    }
