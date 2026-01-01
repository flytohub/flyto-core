"""
JSON to CSV Converter Module
Convert JSON data to CSV format
"""
import csv
import json
import logging
import os
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


@register_module(
    module_id='data.json_to_csv',
    version='1.0.0',
    category='data',
    subcategory='transform',
    tags=['json', 'csv', 'convert', 'data', 'transform'],
    label='JSON to CSV',
    label_key='modules.data.json_to_csv.label',
    description='Convert JSON data or files to CSV format',
    description_key='modules.data.json_to_csv.description',
    icon='FileSpreadsheet',
    color='#059669',

    # Connection types
    input_types=['object', 'array', 'file_path'],
    output_types=['file_path', 'string'],
    can_connect_to=['file.*', 'data.*'],
    can_receive_from=['*'],

    # Execution settings
    timeout=120,
    retryable=True,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['file.read', 'file.write'],

    # Schema-driven params
    params_schema=compose(
        presets.INPUT_DATA(required=True),
        presets.OUTPUT_PATH(key='output_path', default='/tmp/output.csv'),
        presets.DELIMITER(default=','),
        presets.INCLUDE_HEADER(default=True),
        presets.FLATTEN_NESTED(default=True),
        presets.COLUMNS(),
    ),
    output_schema={
        'output_path': {
            'type': 'string',
            'description': 'Path to the generated CSV file'
        },
        'row_count': {
            'type': 'number',
            'description': 'Number of rows written'
        },
        'column_count': {
            'type': 'number',
            'description': 'Number of columns'
        },
        'columns': {
            'type': 'array',
            'description': 'List of column names'
        }
    },
    examples=[
        {
            'title': 'Convert JSON array to CSV',
            'title_key': 'modules.data.json_to_csv.examples.basic.title',
            'params': {
                'input_data': [
                    {'name': 'Alice', 'age': 30},
                    {'name': 'Bob', 'age': 25}
                ],
                'output_path': '/tmp/users.csv'
            }
        },
        {
            'title': 'Convert JSON file',
            'title_key': 'modules.data.json_to_csv.examples.file.title',
            'params': {
                'input_data': '/path/to/data.json',
                'output_path': '/path/to/output.csv'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def json_to_csv(context: Dict[str, Any]) -> Dict[str, Any]:
    """Convert JSON to CSV"""
    params = context['params']
    input_data = params['input_data']
    output_path = params.get('output_path', '/tmp/output.csv')
    delimiter = params.get('delimiter', ',')
    include_header = params.get('include_header', True)
    flatten_nested = params.get('flatten_nested', True)
    columns = params.get('columns', [])

    # Handle tab delimiter
    if delimiter == '\\t':
        delimiter = '\t'

    # Load data if it's a file path
    if isinstance(input_data, str):
        if os.path.exists(input_data):
            with open(input_data, 'r', encoding='utf-8') as f:
                input_data = json.load(f)
        else:
            # Try to parse as JSON string
            try:
                input_data = json.loads(input_data)
            except json.JSONDecodeError:
                raise ValueError(f"Invalid JSON input: {input_data[:100]}...")

    # Ensure input is a list
    if isinstance(input_data, dict):
        # If it's a dict with a data key, use that
        if 'data' in input_data and isinstance(input_data['data'], list):
            input_data = input_data['data']
        else:
            # Wrap single object in list
            input_data = [input_data]

    if not isinstance(input_data, list):
        raise ValueError("Input must be a JSON array or an object with a 'data' array")

    if not input_data:
        raise ValueError("Input data is empty")

    # Flatten nested objects if requested
    if flatten_nested:
        input_data = [_flatten_dict(item) for item in input_data]

    # Determine columns
    if not columns:
        # Get all unique keys from all objects
        all_keys = set()
        for item in input_data:
            if isinstance(item, dict):
                all_keys.update(item.keys())
        columns = sorted(all_keys)

    # Create output directory if needed
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Write CSV
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=delimiter)

        if include_header:
            writer.writerow(columns)

        for item in input_data:
            if isinstance(item, dict):
                row = [_get_value(item, col) for col in columns]
            else:
                row = [str(item)]
            writer.writerow(row)

    # Get file size
    file_size = os.path.getsize(output_path)

    logger.info(f"Converted JSON to CSV: {output_path} ({len(input_data)} rows, {len(columns)} columns)")

    return {
        'ok': True,
        'output_path': output_path,
        'row_count': len(input_data),
        'column_count': len(columns),
        'columns': columns,
        'file_size': file_size,
        'message': f'Converted {len(input_data)} rows to CSV'
    }


def _flatten_dict(d: Dict, parent_key: str = '', sep: str = '.') -> Dict:
    """Flatten nested dictionary with dot notation"""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep).items())
        elif isinstance(v, list):
            # Convert list to JSON string
            items.append((new_key, json.dumps(v)))
        else:
            items.append((new_key, v))
    return dict(items)


def _get_value(item: Dict, key: str) -> str:
    """Get value from dict, handling nested keys and missing values"""
    if '.' in key:
        parts = key.split('.')
        value = item
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part, '')
            else:
                return ''
        return str(value) if value is not None else ''
    else:
        value = item.get(key, '')
        if value is None:
            return ''
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)
