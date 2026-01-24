"""
Path Is Absolute Module
Check if path is absolute
"""
from typing import Any, Dict
import os

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='path.is_absolute',
    version='1.0.0',
    category='path',
    tags=['path', 'absolute', 'check', 'file'],
    label='Path Is Absolute',
    label_key='modules.path.is_absolute.label',
    description='Check if path is absolute',
    description_key='modules.path.is_absolute.description',
    icon='Folder',
    color='#3B82F6',
    input_types=['string'],
    output_types=['boolean'],

    can_receive_from=['*'],
    can_connect_to=['flow.*', 'data.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'path': {
            'type': 'string',
            'label': 'Path',
            'label_key': 'modules.path.is_absolute.params.path.label',
            'description': 'File path to check',
            'description_key': 'modules.path.is_absolute.params.path.description',
            'placeholder': '/home/user/file.txt',
            'required': True
        }
    },
    output_schema={
        'result': {
            'type': 'boolean',
            'description': 'Whether path is absolute',
            'description_key': 'modules.path.is_absolute.output.result.description'
        },
        'path': {
            'type': 'string',
            'description': 'The checked path',
            'description_key': 'modules.path.is_absolute.output.path.description'
        },
        'absolute': {
            'type': 'string',
            'description': 'Absolute version of the path',
            'description_key': 'modules.path.is_absolute.output.absolute.description'
        }
    },
    timeout_ms=5000,
)
async def path_is_absolute(context: Dict[str, Any]) -> Dict[str, Any]:
    """Check if path is absolute."""
    params = context['params']
    path = params.get('path')

    if path is None:
        raise ValidationError("Missing required parameter: path", field="path")

    path = str(path)
    is_abs = os.path.isabs(path)
    absolute = os.path.abspath(path)

    return {
        'ok': True,
        'data': {
            'result': is_abs,
            'path': path,
            'absolute': absolute
        }
    }
