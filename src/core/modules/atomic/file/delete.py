"""
Advanced File Operations Modules

Provides extended file manipulation capabilities.
"""
import os
import shutil
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='file.delete',
    version='1.0.0',
    category='file',
    subcategory='operations',
    tags=['file', 'delete', 'remove'],
    label='Delete File',
    label_key='modules.file.delete.label',
    description='Delete a file from the filesystem',
    description_key='modules.file.delete.description',
    icon='Trash2',
    color='#EF4444',

    # Connection types
    input_types=['file_path', 'text'],
    output_types=['boolean'],

    # Phase 2: Execution settings
    timeout=5,
    retryable=False,  # Don't retry deletes
    concurrent_safe=False,  # File operations not thread-safe

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['file.delete'],

    params_schema={
        'file_path': {
            'type': 'string',
            'label': 'File Path',
            'label_key': 'modules.file.delete.params.file_path.label',
            'description': 'Path to the file to delete',
            'description_key': 'modules.file.delete.params.file_path.description',
            'required': True
        },
        'ignore_missing': {
            'type': 'boolean',
            'label': 'Ignore Missing',
            'label_key': 'modules.file.delete.params.ignore_missing.label',
            'description': 'Do not raise error if file does not exist',
            'description_key': 'modules.file.delete.params.ignore_missing.description',
            'default': False,
            'required': False
        }
    },
    output_schema={
        'deleted': {'type': 'boolean'},
        'file_path': {'type': 'string'}
    },
    examples=[
        {
            'title': 'Delete temporary file',
            'params': {
                'file_path': '/tmp/temp.txt',
                'ignore_missing': True
            }
        },
        {
            'title': 'Delete log file',
            'params': {
                'file_path': 'logs/app.log'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class FileDeleteModule(BaseModule):
    """Delete File Module"""

    def validate_params(self):
        self.file_path = self.params.get('file_path')
        self.ignore_missing = self.params.get('ignore_missing', False)

        if not self.file_path:
            raise ValueError("file_path is required")

    async def execute(self) -> Any:
        try:
            if os.path.exists(self.file_path):
                os.remove(self.file_path)
                return {
                    "deleted": True,
                    "file_path": self.file_path
                }
            elif self.ignore_missing:
                return {
                    "deleted": False,
                    "file_path": self.file_path
                }
            else:
                raise FileNotFoundError(f"File not found: {self.file_path}")
        except Exception as e:
            raise RuntimeError(f"Failed to delete file: {str(e)}")


