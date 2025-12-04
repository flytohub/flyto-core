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

    # Phase 2: Execution settings
    timeout=30,  # File writes can timeout on network filesystems
    retryable=False,  # Don't retry writes (could cause duplicates)
    concurrent_safe=False,  # Writing to same file is not thread-safe

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=True,  # File content may be sensitive
    required_permissions=['file.write'],

    params_schema={
        'path': {
            'type': 'string',
            'label': 'File Path',
            'label_key': 'modules.file.write.params.path.label',
            'description': 'Path to the file to write',
            'description_key': 'modules.file.write.params.path.description',
            'required': True,
            'placeholder': '/path/to/file.txt'
        },
        'content': {
            'type': 'string',
            'label': 'Content',
            'label_key': 'modules.file.write.params.content.label',
            'description': 'Content to write',
            'description_key': 'modules.file.write.params.content.description',
            'required': True,
            'multiline': True
        },
        'encoding': {
            'type': 'string',
            'label': 'Encoding',
            'label_key': 'modules.file.write.params.encoding.label',
            'description': 'File encoding',
            'description_key': 'modules.file.write.params.encoding.description',
            'default': 'utf-8',
            'required': False
        },
        'mode': {
            'type': 'string',
            'label': 'Write Mode',
            'label_key': 'modules.file.write.params.mode.label',
            'description': 'Write mode: overwrite or append',
            'description_key': 'modules.file.write.params.mode.description',
            'default': 'overwrite',
            'required': False,
            'options': [
                {'value': 'overwrite', 'label': 'Overwrite'},
                {'value': 'append', 'label': 'Append'}
            ]
        }
    },
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


