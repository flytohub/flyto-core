"""
Path Extension Module
Get file extension from path
"""
from typing import Any, Dict
import os

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='path.extension',
    version='1.0.0',
    category='path',
    tags=['path', 'extension', 'file', 'suffix'],
    label='Path Extension',
    label_key='modules.path.extension.label',
    description='Get file extension from path',
    description_key='modules.path.extension.description',
    icon='FileType',
    color='#3B82F6',
    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['file.*', 'data.*', 'string.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'path': {
            'type': 'string',
            'label': 'Path',
            'label_key': 'modules.path.extension.params.path.label',
            'description': 'File path',
            'description_key': 'modules.path.extension.params.path.description',
            'placeholder': '/home/user/file.txt',
            'required': True
        },
        'include_dot': {
            'type': 'boolean',
            'label': 'Include Dot',
            'label_key': 'modules.path.extension.params.include_dot.label',
            'description': 'Include the dot in extension',
            'description_key': 'modules.path.extension.params.include_dot.description',
            'default': True,
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'File extension',
            'description_key': 'modules.path.extension.output.result.description'
        },
        'original': {
            'type': 'string',
            'description': 'Original path',
            'description_key': 'modules.path.extension.output.original.description'
        },
        'has_extension': {
            'type': 'boolean',
            'description': 'Whether file has extension',
            'description_key': 'modules.path.extension.output.has_extension.description'
        }
    },
    timeout_ms=5000,
)
async def path_extension(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get file extension from path."""
    params = context['params']
    path = params.get('path')
    include_dot = params.get('include_dot', True)

    if path is None:
        raise ValidationError("Missing required parameter: path", field="path")

    path = str(path)
    _, ext = os.path.splitext(path)

    has_extension = bool(ext)

    if not include_dot and ext.startswith('.'):
        ext = ext[1:]

    return {
        'ok': True,
        'data': {
            'result': ext,
            'original': path,
            'has_extension': has_extension
        }
    }
