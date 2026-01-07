"""
File Operation Modules
Basic file system operations
"""

from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_path_with_env_config, PathTraversalError
import os
import shutil


@register_module(
    module_id='file.read',
    version='1.0.0',
    category='atomic',
    subcategory='file',
    tags=['file', 'io', 'read', 'atomic'],
    label='Read File',
    label_key='modules.file.read.label',
    description='Read content from a file',
    description_key='modules.file.read.description',
    icon='FileText',
    color='#6B7280',

    # Connection types
    input_types=['string'],
    output_types=['string', 'binary'],


    can_receive_from=['start', 'flow.*'],
    can_connect_to=['*'],    # Execution settings
    timeout=30,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['file.read'],

    # Schema-driven params
    params_schema=compose(
        presets.FILE_PATH(key='path', required=True, placeholder='/path/to/file.txt'),
        presets.ENCODING(default='utf-8'),
    ),
    output_schema={
        'content': {
            'type': 'string',
            'description': 'File content'
        ,
                'description_key': 'modules.file.read.output.content.description'},
        'size': {
            'type': 'number',
            'description': 'File size in bytes'
        ,
                'description_key': 'modules.file.read.output.size.description'}
    },
    examples=[
        {
            'title': 'Read text file',
            'title_key': 'modules.file.read.examples.text.title',
            'params': {
                'path': '/tmp/data.txt',
                'encoding': 'utf-8'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def file_read(context):
    """Read file content"""
    params = context['params']
    path = params['path']
    encoding = params.get('encoding', 'utf-8')

    # SECURITY: Validate path to prevent path traversal attacks
    try:
        safe_path = validate_path_with_env_config(path)
    except PathTraversalError as e:
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'PATH_TRAVERSAL'
        }

    if not os.path.exists(safe_path):
        return {
            'ok': False,
            'error': f'File not found: {path}',
            'error_code': 'FILE_NOT_FOUND'
        }

    with open(safe_path, 'r', encoding=encoding) as f:
        content = f.read()

    size = os.path.getsize(safe_path)

    return {
        'content': content,
        'size': size
    }


