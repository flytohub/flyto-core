"""
Advanced File Operations Modules

Provides extended file manipulation capabilities.
"""
import os
import shutil
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='file.move',
    version='1.0.0',
    category='file',
    subcategory='operations',
    tags=['file', 'move', 'rename', 'path_restricted'],
    label='Move File',
    label_key='modules.file.move.label',
    description='Move or rename a file',
    description_key='modules.file.move.description',
    icon='Move',
    color='#8B5CF6',

    # Connection types
    input_types=['file_path', 'text'],
    output_types=['file_path', 'text'],


    can_receive_from=['*'],
    can_connect_to=['file.*', 'data.*', 'document.*', 'image.*', 'ai.*', 'notification.*', 'flow.*'],    # Execution settings
    timeout_ms=10000,
    retryable=False,
    concurrent_safe=False,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['filesystem.write'],

    # Schema-driven params
    params_schema=compose(
        presets.SOURCE_PATH(required=True),
        presets.DESTINATION_PATH(required=True),
    ),
    output_schema={
        'moved': {'type': 'boolean', 'description': 'The moved',
                'description_key': 'modules.file.move.output.moved.description'},
        'source': {'type': 'string', 'description': 'The source',
                'description_key': 'modules.file.move.output.source.description'},
        'destination': {'type': 'string', 'description': 'The destination',
                'description_key': 'modules.file.move.output.destination.description'}
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
    author='Flyto Team',
    license='MIT'
)
class FileMoveModule(BaseModule):
    """Move File Module"""

    def validate_params(self) -> None:
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


