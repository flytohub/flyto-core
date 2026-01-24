"""
Path Normalize Module
Normalize a file path
"""
from typing import Any, Dict
import os

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='path.normalize',
    version='1.0.0',
    category='path',
    tags=['path', 'normalize', 'clean', 'file'],
    label='Path Normalize',
    label_key='modules.path.normalize.label',
    description='Normalize a file path',
    description_key='modules.path.normalize.description',
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
            'label_key': 'modules.path.normalize.params.path.label',
            'description': 'File path to normalize',
            'description_key': 'modules.path.normalize.params.path.description',
            'placeholder': '/home/user/../user/./file.txt',
            'required': True
        },
        'resolve': {
            'type': 'boolean',
            'label': 'Resolve',
            'label_key': 'modules.path.normalize.params.resolve.label',
            'description': 'Resolve to absolute path',
            'description_key': 'modules.path.normalize.params.resolve.description',
            'default': False,
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Normalized path',
            'description_key': 'modules.path.normalize.output.result.description'
        },
        'original': {
            'type': 'string',
            'description': 'Original path',
            'description_key': 'modules.path.normalize.output.original.description'
        },
        'is_absolute': {
            'type': 'boolean',
            'description': 'Whether result is absolute',
            'description_key': 'modules.path.normalize.output.is_absolute.description'
        }
    },
    timeout_ms=5000,
)
async def path_normalize(context: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a file path."""
    params = context['params']
    path = params.get('path')
    resolve = params.get('resolve', False)

    if path is None:
        raise ValidationError("Missing required parameter: path", field="path")

    path = str(path)

    if resolve:
        result = os.path.abspath(path)
    else:
        result = os.path.normpath(path)

    is_absolute = os.path.isabs(result)

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': path,
            'is_absolute': is_absolute
        }
    }
