"""
Path Dirname Module
Get directory name from path
"""
from typing import Any, Dict
import os

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='path.dirname',
    version='1.0.0',
    category='path',
    tags=['path', 'dirname', 'directory', 'file'],
    label='Path Dirname',
    label_key='modules.path.dirname.label',
    description='Get directory name from path',
    description_key='modules.path.dirname.description',
    icon='Folder',
    color='#3B82F6',
    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['file.*', 'data.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'path': {
            'type': 'string',
            'label': 'Path',
            'label_key': 'modules.path.dirname.params.path.label',
            'description': 'File path',
            'description_key': 'modules.path.dirname.params.path.description',
            'placeholder': '/home/user/file.txt',
            'required': True
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Directory name',
            'description_key': 'modules.path.dirname.output.result.description'
        },
        'original': {
            'type': 'string',
            'description': 'Original path',
            'description_key': 'modules.path.dirname.output.original.description'
        }
    },
    timeout_ms=5000,
)
async def path_dirname(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get directory name from path."""
    params = context['params']
    path = params.get('path')

    if path is None:
        raise ValidationError("Missing required parameter: path", field="path")

    path = str(path)
    result = os.path.dirname(path)

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': path
        }
    }
