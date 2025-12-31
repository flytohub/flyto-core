"""
File Operation Modules
Basic file system operations
"""

from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
import os
import shutil


@register_module(
    module_id='file.write',
    version='1.0.0',
    category='atomic',
    subcategory='file',
    tags=['file', 'io', 'write', 'atomic'],
    label='Write File',
    label_key='modules.file.write.label',
    description='Write content to a file',
    description_key='modules.file.write.description',
    icon='FileText',
    color='#6B7280',

    # Execution settings
    timeout=30,
    retryable=False,
    concurrent_safe=False,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['file.write'],

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
        },
        'bytes_written': {
            'type': 'number',
            'description': 'Number of bytes written'
        }
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
    author='Flyto2 Team',
    license='MIT'
)
async def file_write(context):
    """Write file content"""
    params = context['params']
    path = params['path']
    content = params['content']
    encoding = params.get('encoding', 'utf-8')
    mode = 'w' if params.get('mode', 'overwrite') == 'overwrite' else 'a'

    with open(path, mode, encoding=encoding) as f:
        bytes_written = f.write(content)

    return {
        'path': path,
        'bytes_written': len(content.encode(encoding))
    }


