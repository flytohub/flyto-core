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
    module_id='file.exists',
    version='1.0.0',
    category='atomic',
    subcategory='file',
    tags=['file', 'io', 'check', 'atomic', 'path_restricted'],
    label='Check File Exists',
    label_key='modules.file.exists.label',
    description='Check if a file or directory exists',
    description_key='modules.file.exists.description',
    icon='FileSearch',
    color='#6B7280',


    can_receive_from=['start', 'flow.*'],
    can_connect_to=['*'],    # Execution settings
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['filesystem.read'],

    # Schema-driven params
    params_schema=compose(
        presets.FILE_PATH(key='path', required=True, label='Path', placeholder='/path/to/file'),
    ),
    output_schema={
        'exists': {
            'type': 'boolean',
            'description': 'Whether path exists'
        ,
                'description_key': 'modules.file.exists.output.exists.description'},
        'is_file': {
            'type': 'boolean',
            'description': 'Whether path is a file'
        ,
                'description_key': 'modules.file.exists.output.is_file.description'},
        'is_directory': {
            'type': 'boolean',
            'description': 'Whether path is a directory'
        ,
                'description_key': 'modules.file.exists.output.is_directory.description'}
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
    license='MIT',
    timeout_ms=30000,
)
async def file_exists(context):
    """Check if file exists"""
    params = context['params']
    path = params['path']

    exists = os.path.exists(path)
    is_file = os.path.isfile(path) if exists else False
    is_directory = os.path.isdir(path) if exists else False

    return {
        'ok': True,
        'data': {
            'exists': exists,
            'is_file': is_file,
            'is_directory': is_directory
        }
    }
