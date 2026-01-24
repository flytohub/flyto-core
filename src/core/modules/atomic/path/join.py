"""
Path Join Module
Join path components
"""
from typing import Any, Dict, List
import os

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='path.join',
    version='1.0.0',
    category='path',
    tags=['path', 'join', 'file', 'directory'],
    label='Path Join',
    label_key='modules.path.join.label',
    description='Join path components',
    description_key='modules.path.join.description',
    icon='Folder',
    color='#3B82F6',
    input_types=['string', 'array'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['file.*', 'data.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'parts': {
            'type': 'array',
            'label': 'Path Parts',
            'label_key': 'modules.path.join.params.parts.label',
            'description': 'Path components to join',
            'description_key': 'modules.path.join.params.parts.description',
            'placeholder': '["/home", "user", "file.txt"]',
            'required': True
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Joined path',
            'description_key': 'modules.path.join.output.result.description'
        },
        'parts': {
            'type': 'array',
            'description': 'Original path parts',
            'description_key': 'modules.path.join.output.parts.description'
        }
    },
    timeout_ms=5000,
)
async def path_join(context: Dict[str, Any]) -> Dict[str, Any]:
    """Join path components."""
    params = context['params']
    parts = params.get('parts')

    if parts is None:
        raise ValidationError("Missing required parameter: parts", field="parts")

    if isinstance(parts, str):
        parts = [parts]

    if not isinstance(parts, list):
        raise ValidationError("parts must be an array", field="parts")

    str_parts = [str(p) for p in parts if p is not None]
    result = os.path.join(*str_parts) if str_parts else ''

    return {
        'ok': True,
        'data': {
            'result': result,
            'parts': str_parts
        }
    }
