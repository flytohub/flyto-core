"""
File Operation Modules
Basic file system operations
"""

from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
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
    output_types=['text', 'binary'],
    can_connect_to=['data.*', 'string.*'],

    # Phase 2: Execution settings
    timeout=30,  # File reads can timeout on network filesystems
    retryable=True,  # Can retry failed reads
    max_retries=2,
    concurrent_safe=True,  # Reading different files is safe

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=True,  # Files may contain sensitive data
    required_permissions=['file.read'],

    params_schema={
        'path': {
            'type': 'string',
            'label': 'File Path',
            'label_key': 'modules.file.read.params.path.label',
            'description': 'Path to the file to read',
            'description_key': 'modules.file.read.params.path.description',
            'required': True,
            'placeholder': '/path/to/file.txt'
        },
        'encoding': {
            'type': 'string',
            'label': 'Encoding',
            'label_key': 'modules.file.read.params.encoding.label',
            'description': 'File encoding',
            'description_key': 'modules.file.read.params.encoding.description',
            'default': 'utf-8',
            'required': False
        }
    },
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


