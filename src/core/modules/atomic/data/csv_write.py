"""
Data Processing Modules
Handle CSV, JSON, text processing, data transformation, etc.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
import json
import csv
import io
import os


@register_module(
    module_id='data.csv.write',
    version='1.0.0',
    category='data',
    tags=['data', 'csv', 'file', 'write', 'export'],
    label='Write CSV File',
    label_key='modules.data.csv.write.label',
    description='Write array of objects to CSV file',
    description_key='modules.data.csv.write.description',
    icon='Save',
    color='#10B981',

    # Phase 2: Execution settings
    timeout=30,  # File writes can timeout on network filesystems
    retryable=False,  # Don't retry writes (could cause duplicates)
    concurrent_safe=False,  # Writing to same file is not thread-safe

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=True,  # CSV data may be sensitive
    required_permissions=['file.write'],

    params_schema={
        'file_path': {
            'type': 'string',
            'label': 'File Path',
            'label_key': 'modules.data.csv.write.params.file_path.label',
            'description': 'Output CSV file path',
            'description_key': 'modules.data.csv.write.params.file_path.description',
            'placeholder': '/path/to/output.csv',
            'required': True
        },
        'data': {
            'type': 'array',
            'label': 'Data',
            'label_key': 'modules.data.csv.write.params.data.label',
            'description': 'Array of objects to write',
            'description_key': 'modules.data.csv.write.params.data.description',
            'required': True
        },
        'delimiter': {
            'type': 'string',
            'label': 'Delimiter',
            'label_key': 'modules.data.csv.write.params.delimiter.label',
            'description': 'CSV delimiter character',
            'description_key': 'modules.data.csv.write.params.delimiter.description',
            'default': ',',
            'required': False
        },
        'encoding': {
            'type': 'string',
            'label': 'Encoding',
            'label_key': 'modules.data.csv.write.params.encoding.label',
            'description': 'File encoding',
            'description_key': 'modules.data.csv.write.params.encoding.description',
            'default': 'utf-8',
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'file_path': {'type': 'string'},
        'rows_written': {'type': 'number'}
    },
    examples=[
        {
            'name': 'Write CSV file',
            'params': {
                'file_path': 'output/results.csv',
                'data': [
                    {'name': 'John', 'score': 95},
                    {'name': 'Jane', 'score': 87}
                ]
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class CSVWriteModule(BaseModule):
    """Write array to CSV file"""

    module_name = "Write CSV File"
    module_description = "Write array of objects to CSV file"

    def validate_params(self):
        if 'file_path' not in self.params or not self.params['file_path']:
            raise ValueError("Missing required parameter: file_path")
        if 'data' not in self.params or not isinstance(self.params['data'], list):
            raise ValueError("Missing or invalid parameter: data (must be array)")

        self.file_path = self.params['file_path']
        self.data = self.params['data']
        self.delimiter = self.params.get('delimiter', ',')
        self.encoding = self.params.get('encoding', 'utf-8')

    async def execute(self) -> Any:
        try:
            if not self.data:
                return {
                    'status': 'error',
                    'message': 'Cannot write empty data array'
                }

            # Create directory if not exists
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

            # Get column names from first object
            fieldnames = list(self.data[0].keys())

            with open(self.file_path, 'w', encoding=self.encoding, newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=self.delimiter)
                writer.writeheader()
                writer.writerows(self.data)

            return {
                'status': 'success',
                'file_path': self.file_path,
                'rows_written': len(self.data)
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to write CSV: {str(e)}'
            }


