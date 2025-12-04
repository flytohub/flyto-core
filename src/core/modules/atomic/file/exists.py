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
    module_id='file.exists',
    version='1.0.0',
    category='atomic',
    subcategory='file',
    tags=['file', 'io', 'check', 'atomic'],
    label='Check File Exists',
    label_key='modules.file.exists.label',
    description='Check if a file or directory exists',
    description_key='modules.file.exists.description',
    icon='FileSearch',
    color='#6B7280',

    # Phase 2: Execution settings
    # No timeout needed - file existence check is instant
    retryable=True,  # Can retry if filesystem temporarily unavailable
    max_retries=2,
    concurrent_safe=True,  # Stateless check operation

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['file.read'],

    params_schema={
        'path': {
            'type': 'string',
            'label': 'Path',
            'label_key': 'modules.file.exists.params.path.label',
            'description': 'Path to check',
            'description_key': 'modules.file.exists.params.path.description',
            'required': True,
            'placeholder': '/path/to/file'
        }
    },
    output_schema={
        'exists': {
            'type': 'boolean',
            'description': 'Whether path exists'
        },
        'is_file': {
            'type': 'boolean',
            'description': 'Whether path is a file'
        },
        'is_directory': {
            'type': 'boolean',
            'description': 'Whether path is a directory'
        }
    },
    examples=[
        {
            'title': 'Check file exists',
            'title_key': 'modules.file.exists.examples.check.title',
            'params': {
                'path': '/tmp/data.txt'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def file_exists(context):
    """Check if file exists"""
    params = context['params']
    path = params['path']

    exists = os.path.exists(path)
    is_file = os.path.isfile(path) if exists else False
    is_directory = os.path.isdir(path) if exists else False

    return {
        'exists': exists,
        'is_file': is_file,
        'is_directory': is_directory
    }
