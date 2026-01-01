"""
Data Processing Modules
Handle CSV, JSON, text processing, data transformation, etc.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
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


    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'ai.*', 'notification.*', 'flow.*'],    # Execution settings
    timeout=30,
    retryable=False,
    concurrent_safe=False,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['file.write'],

    # Schema-driven params
    params_schema=compose(
        presets.FILE_PATH(required=True, placeholder='/path/to/output.csv'),
        presets.DATA_ARRAY(required=True),
        presets.DELIMITER(default=','),
        presets.ENCODING(default='utf-8'),
    ),
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


