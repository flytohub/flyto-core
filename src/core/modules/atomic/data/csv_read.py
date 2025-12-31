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
    module_id='data.csv.read',
    version='1.0.0',
    category='data',
    tags=['data', 'csv', 'file', 'read', 'parser'],
    label='Read CSV File',
    label_key='modules.data.csv.read.label',
    description='Read and parse CSV file into array of objects',
    description_key='modules.data.csv.read.description',
    icon='FileText',
    color='#10B981',

    # Connection types
    input_types=['text', 'file_path'],
    output_types=['array', 'object'],
    can_connect_to=['data.*', 'file.*'],

    # Execution settings
    timeout=30,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['file.read'],

    # Schema-driven params
    params_schema=compose(
        presets.FILE_PATH(required=True, placeholder='/path/to/data.csv'),
        presets.DELIMITER(default=','),
        presets.ENCODING(default='utf-8'),
        presets.SKIP_HEADER(default=False),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status'},
        'data': {'type': 'array', 'description': 'Array of row objects'},
        'rows': {'type': 'number', 'description': 'Number of rows'},
        'columns': {'type': 'array', 'description': 'Column names'}
    },
    examples=[
        {
            'name': 'Read CSV file',
            'params': {
                'file_path': 'data/users.csv',
                'delimiter': ',',
                'encoding': 'utf-8'
            },
            'expected_output': {
                'status': 'success',
                'data': [
                    {'name': 'John', 'age': '30', 'city': 'NYC'},
                    {'name': 'Jane', 'age': '25', 'city': 'LA'}
                ],
                'rows': 2
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class CSVReadModule(BaseModule):
    """Read CSV file and parse into array"""

    module_name = "Read CSV File"
    module_description = "Read and parse CSV file into array of objects"

    def validate_params(self):
        if 'file_path' not in self.params or not self.params['file_path']:
            raise ValueError("Missing required parameter: file_path")

        self.file_path = self.params['file_path']
        self.delimiter = self.params.get('delimiter', ',')
        self.encoding = self.params.get('encoding', 'utf-8')
        self.skip_header = self.params.get('skip_header', False)

    async def execute(self) -> Any:
        try:
            if not os.path.exists(self.file_path):
                return {
                    'status': 'error',
                    'message': f'File not found: {self.file_path}'
                }

            with open(self.file_path, 'r', encoding=self.encoding) as csvfile:
                reader = csv.DictReader(csvfile, delimiter=self.delimiter)

                if self.skip_header:
                    next(reader, None)  # Skip header row

                data = list(reader)
                columns = reader.fieldnames or []

                return {
                    'status': 'success',
                    'data': data,
                    'rows': len(data),
                    'columns': columns
                }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to read CSV: {str(e)}'
            }


