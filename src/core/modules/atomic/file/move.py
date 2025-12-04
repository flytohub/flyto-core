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
    module_id='file.move',
    version='1.0.0',
    category='file',
    subcategory='operations',
    tags=['file', 'move', 'rename'],
    label='Move File',
    label_key='modules.file.move.label',
    description='Move or rename a file',
    description_key='modules.file.move.description',
    icon='Move',
    color='#8B5CF6',

    # Connection types
    input_types=['file_path', 'text'],
    output_types=['file_path', 'text'],

    # Phase 2: Execution settings
    timeout=10,
    retryable=False,
    concurrent_safe=False,

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['file.read', 'file.write'],

    params_schema={
        'source': {
            'type': 'string',
            'label': 'Source Path',
            'label_key': 'modules.file.move.params.source.label',
            'description': 'Path to the source file',
            'description_key': 'modules.file.move.params.source.description',
            'required': True
        },
        'destination': {
            'type': 'string',
            'label': 'Destination Path',
            'label_key': 'modules.file.move.params.destination.label',
            'description': 'Path to the destination',
            'description_key': 'modules.file.move.params.destination.description',
            'required': True
        }
    },
    output_schema={
        'moved': {'type': 'boolean'},
        'source': {'type': 'string'},
        'destination': {'type': 'string'}
    },
    examples=[
        {
            'title': 'Move file to archive',
            'params': {
                'source': 'data/input.csv',
                'destination': 'archive/input_2024.csv'
            }
        },
        {
            'title': 'Rename file',
            'params': {
                'source': 'report.txt',
                'destination': 'report_final.txt'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class FileMoveModule(BaseModule):
    """Move File Module"""

    def validate_params(self):
        self.source = self.params.get('source')
        self.destination = self.params.get('destination')

        if not self.source or not self.destination:
            raise ValueError("source and destination are required")

    async def execute(self) -> Any:
        try:
            if not os.path.exists(self.source):
                raise FileNotFoundError(f"Source file not found: {self.source}")

            # Create destination directory if needed
            dest_dir = os.path.dirname(self.destination)
            if dest_dir and not os.path.exists(dest_dir):
                os.makedirs(dest_dir, exist_ok=True)

            shutil.move(self.source, self.destination)

            return {
                "moved": True,
                "source": self.source,
                "destination": self.destination
            }
        except Exception as e:
            raise RuntimeError(f"Failed to move file: {str(e)}")


