"""
Path Basename Module
Get file name from path
"""
from typing import Any, Dict
import os

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='path.basename',
    version='1.0.0',
    category='path',
    tags=['path', 'basename', 'filename', 'file'],
    label='Path Basename',
    label_key='modules.path.basename.label',
    description='Get file name from path',
    description_key='modules.path.basename.description',
    icon='File',
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
            'label_key': 'modules.path.basename.params.path.label',
            'description': 'File path',
            'description_key': 'modules.path.basename.params.path.description',
            'placeholder': '/home/user/file.txt',
            'required': True
        },
        'remove_extension': {
            'type': 'boolean',
            'label': 'Remove Extension',
            'label_key': 'modules.path.basename.params.remove_extension.label',
            'description': 'Remove file extension from result',
            'description_key': 'modules.path.basename.params.remove_extension.description',
            'default': False,
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'File name',
            'description_key': 'modules.path.basename.output.result.description'
        },
        'original': {
            'type': 'string',
            'description': 'Original path',
            'description_key': 'modules.path.basename.output.original.description'
        },
        'extension': {
            'type': 'string',
            'description': 'File extension',
            'description_key': 'modules.path.basename.output.extension.description'
        }
    },
    timeout_ms=5000,
)
async def path_basename(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get file name from path."""
    params = context['params']
    path = params.get('path')
    remove_extension = params.get('remove_extension', False)

    if path is None:
        raise ValidationError("Missing required parameter: path", field="path")

    path = str(path)
    basename = os.path.basename(path)
    name, ext = os.path.splitext(basename)

    result = name if remove_extension else basename

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': path,
            'extension': ext
        }
    }
