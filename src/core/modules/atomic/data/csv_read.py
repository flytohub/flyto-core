"""
CSV Read Module
Read and parse CSV file into array of objects
"""
from typing import Any, Dict
import csv
import os

from ...registry import register_module
from ...schema import compose, presets


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
    can_connect_to=['data.*', 'file.*', 'flow.*', 'array.*'],
    can_receive_from=['*'],

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
        'status': {
            'type': 'string',
            'description': 'Operation status'
        ,
                'description_key': 'modules.data.csv.read.output.status.description'},
        'data': {
            'type': 'array',
            'description': 'Array of row objects'
        ,
                'description_key': 'modules.data.csv.read.output.data.description'},
        'rows': {
            'type': 'number',
            'description': 'Number of rows'
        ,
                'description_key': 'modules.data.csv.read.output.rows.description'},
        'columns': {
            'type': 'array',
            'description': 'Column names'
        ,
                'description_key': 'modules.data.csv.read.output.columns.description'}
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
async def csv_read(context: Dict[str, Any]) -> Dict[str, Any]:
    """Read and parse CSV file into array of objects."""
    params = context['params']
    file_path = params.get('file_path')
    delimiter = params.get('delimiter', ',')
    encoding = params.get('encoding', 'utf-8')
    skip_header = params.get('skip_header', False)

    if not file_path:
        return {
            'ok': False,
            'error': 'Missing required parameter: file_path',
            'error_code': 'MISSING_PARAM'
        }

    try:
        if not os.path.exists(file_path):
            return {
                'status': 'error',
                'message': f'File not found: {file_path}'
            }

        with open(file_path, 'r', encoding=encoding) as csvfile:
            reader = csv.DictReader(csvfile, delimiter=delimiter)

            if skip_header:
                next(reader, None)

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
