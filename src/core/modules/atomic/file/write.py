"""
File Operation Modules
Basic file system operations
"""

from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_path_with_env_config, PathTraversalError
from ...errors import ModuleError
import os
import shutil


@register_module(
    module_id='file.write',
    version='1.0.0',
    category='atomic',
    subcategory='file',
    tags=['file', 'io', 'write', 'atomic', 'path_restricted'],
    label='Write File',
    label_key='modules.file.write.label',
    description='Write content to a file',
    description_key='modules.file.write.description',
    icon='FileText',
    color='#6B7280',


    # Type definitions for connection validation
    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['*'],    # Execution settings
    timeout_ms=30000,
    retryable=False,
    concurrent_safe=False,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['filesystem.write'],

    # Schema-driven params
    params_schema=compose(
        presets.FILE_PATH(key='path', required=True, placeholder='/path/to/file.txt'),
        presets.FILE_CONTENT(required=True),
        presets.ENCODING(default='utf-8'),
        presets.WRITE_MODE(default='overwrite'),
    ),
    output_schema={
        'path': {
            'type': 'string',
            'description': 'File path'
        ,
                'description_key': 'modules.file.write.output.path.description'},
        'bytes_written': {
            'type': 'number',
            'description': 'Number of bytes written'
        ,
                'description_key': 'modules.file.write.output.bytes_written.description'}
    },
    examples=[
        {
            'title': 'Write text file',
            'title_key': 'modules.file.write.examples.text.title',
            'params': {
                'path': '/tmp/output.txt',
                'content': 'Hello World',
                'mode': 'overwrite'
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
async def file_write(context):
    """Write file content"""
    params = context['params']
    path = params['path']
    content = params['content']
    encoding = params.get('encoding', 'utf-8')
    mode = 'w' if params.get('mode', 'overwrite') == 'overwrite' else 'a'

    # SECURITY: Validate path to prevent path traversal attacks
    try:
        safe_path = validate_path_with_env_config(path)
    except PathTraversalError as e:
        raise ModuleError(str(e), code="PATH_TRAVERSAL")

    # Create parent directory if it doesn't exist
    parent_dir = os.path.dirname(safe_path)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    with open(safe_path, mode, encoding=encoding) as f:
        f.write(content)

    return {
        'ok': True,
        'data': {
            'path': safe_path,
            'bytes_written': len(content.encode(encoding))
        }
    }


