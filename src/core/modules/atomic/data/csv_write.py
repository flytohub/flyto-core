"""
CSV Write Module
Write array of objects to CSV file
"""
from typing import Any, Dict
import csv
import os

from ...registry import register_module
from ...schema import compose, presets
from ...errors import ValidationError, InvalidTypeError, InvalidValueError, ModuleError


@register_module(
    module_id='data.csv.write',
    version='1.0.0',
    category='data',
    tags=['data', 'csv', 'file', 'write', 'export', 'path_restricted'],
    label='Write CSV File',
    label_key='modules.data.csv.write.label',
    description='Write array of objects to CSV file',
    description_key='modules.data.csv.write.description',
    icon='Save',
    color='#10B981',

    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'ai.*', 'notification.*', 'flow.*'],

    # Execution settings
    timeout_ms=30000,
    retryable=False,
    concurrent_safe=False,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'filesystem.write'],

    # Schema-driven params
    params_schema=compose(
        presets.FILE_PATH(required=True, placeholder='/path/to/output.csv'),
        presets.DATA_ARRAY(required=True),
        presets.DELIMITER(default=','),
        presets.ENCODING(default='utf-8'),
    ),
    output_schema={
        'status': {
            'type': 'string',
            'description': 'Operation status'
        ,
                'description_key': 'modules.data.csv.write.output.status.description'},
        'file_path': {
            'type': 'string',
            'description': 'Path to written file'
        ,
                'description_key': 'modules.data.csv.write.output.file_path.description'},
        'rows_written': {
            'type': 'number',
            'description': 'Number of rows written'
        ,
                'description_key': 'modules.data.csv.write.output.rows_written.description'}
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
async def csv_write(context: Dict[str, Any]) -> Dict[str, Any]:
    """Write array of objects to CSV file."""
    params = context['params']
    file_path = params.get('file_path')
    data = params.get('data')
    delimiter = params.get('delimiter', ',')
    encoding = params.get('encoding', 'utf-8')

    if not file_path:
        raise ValidationError("Missing required parameter: file_path", field="file_path")

    if not isinstance(data, list):
        raise InvalidTypeError(
            "data must be an array",
            field="data",
            expected_type="list",
            actual_type=type(data).__name__
        )

    if not data:
        raise InvalidValueError("Cannot write empty data array", field="data")

    try:
        # Create directory if not exists
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # Get column names from first object
        fieldnames = list(data[0].keys())

        with open(file_path, 'w', encoding=encoding, newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=delimiter)
            writer.writeheader()
            writer.writerows(data)

        return {
            'ok': True,
            'data': {
                'file_path': file_path,
                'rows_written': len(data)
            }
        }

    except Exception as e:
        raise ModuleError(f"Failed to write CSV: {str(e)}")
