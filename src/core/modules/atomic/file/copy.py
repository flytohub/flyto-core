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
    module_id='file.copy',
    version='1.0.0',
    category='file',
    subcategory='operations',
    tags=['file', 'copy', 'duplicate'],
    label='Copy File',
    label_key='modules.file.copy.label',
    description='Copy a file to another location',
    description_key='modules.file.copy.description',
    icon='Copy',
    color='#10B981',

    # Connection types
    input_types=['file_path', 'text'],
    output_types=['file_path', 'text'],

    # Phase 2: Execution settings
    timeout=30,  # Large files may take time
    retryable=True,
    max_retries=2,
    concurrent_safe=False,

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['file.read', 'file.write'],

    params_schema={
        'source': {
            'type': 'string',
            'label': 'Source Path',
            'label_key': 'modules.file.copy.params.source.label',
            'description': 'Path to the source file',
            'description_key': 'modules.file.copy.params.source.description',
            'required': True
        },
        'destination': {
            'type': 'string',
            'label': 'Destination Path',
            'label_key': 'modules.file.copy.params.destination.label',
            'description': 'Path to copy the file to',
            'description_key': 'modules.file.copy.params.destination.description',
            'required': True
        },
        'overwrite': {
            'type': 'boolean',
            'label': 'Overwrite',
            'label_key': 'modules.file.copy.params.overwrite.label',
            'description': 'Overwrite destination if it exists',
            'description_key': 'modules.file.copy.params.overwrite.description',
            'default': False,
            'required': False
        }
    },
    output_schema={
        'copied': {'type': 'boolean'},
        'source': {'type': 'string'},
        'destination': {'type': 'string'},
        'size': {'type': 'number'}
    },
    examples=[
        {
            'title': 'Backup file',
            'params': {
                'source': 'data/important.csv',
                'destination': 'backup/important.csv',
                'overwrite': True
            }
        },
        {
            'title': 'Duplicate configuration',
            'params': {
                'source': 'config.yaml',
                'destination': 'config.backup.yaml'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class FileCopyModule(BaseModule):
    """Copy File Module"""

    def validate_params(self):
        self.source = self.params.get('source')
        self.destination = self.params.get('destination')
        self.overwrite = self.params.get('overwrite', False)

        if not self.source or not self.destination:
            raise ValueError("source and destination are required")

    async def execute(self) -> Any:
        try:
            if not os.path.exists(self.source):
                raise FileNotFoundError(f"Source file not found: {self.source}")

            if os.path.exists(self.destination) and not self.overwrite:
                raise FileExistsError(f"Destination already exists: {self.destination}")

            # Create destination directory if needed
            dest_dir = os.path.dirname(self.destination)
            if dest_dir and not os.path.exists(dest_dir):
                os.makedirs(dest_dir, exist_ok=True)

            shutil.copy2(self.source, self.destination)
            file_size = os.path.getsize(self.destination)

            return {
                "copied": True,
                "source": self.source,
                "destination": self.destination,
                "size": file_size
            }
        except Exception as e:
            raise RuntimeError(f"Failed to copy file: {str(e)}")
