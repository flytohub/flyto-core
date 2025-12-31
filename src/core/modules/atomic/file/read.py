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

    # Execution settings
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
        },
        'size': {
            'type': 'number',
            'description': 'File size in bytes'
        }
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

    with open(path, 'r', encoding=encoding) as f:
        content = f.read()

    size = os.path.getsize(path)

    return {
        'content': content,
        'size': size
    }


