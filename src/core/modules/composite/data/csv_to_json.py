"""
CSV to JSON Composite Module

Reads a CSV file and converts it to JSON format.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.data.csv_to_json',
    version='1.0.0',
    category='composite',
    subcategory='data',
    tags=['data', 'csv', 'json', 'transform', 'file'],

    # Display
    label='CSV to JSON',
    label_key='modules.composite.data.csv_to_json.label',
    description='Read a CSV file and convert it to JSON format',
    description_key='modules.composite.data.csv_to_json.description',

    # Visual
    icon='FileSpreadsheet',
    color='#059669',

    # Connection types
    input_types=['file_path', 'csv'],
    output_types=['json'],

    # Steps definition
    steps=[
        {
            'id': 'read_csv',
            'module': 'data.csv.read',
            'params': {
                'file_path': '${params.input_file}',
                'delimiter': '${params.delimiter}',
                'has_header': '${params.has_header}'
            }
        },
        {
            'id': 'to_json',
            'module': 'data.json.stringify',
            'params': {
                'data': '${steps.read_csv.data}',
                'indent': '${params.indent}'
            }
        },
        {
            'id': 'write_json',
            'module': 'file.write',
            'params': {
                'path': '${params.output_file}',
                'content': '${steps.to_json.result}'
            },
            'on_error': 'continue'
        }
    ],

    # Schema
    params_schema={
        'input_file': {
            'type': 'string',
            'label': 'Input CSV File',
            'description': 'Path to the CSV file to read',
            'placeholder': './data/input.csv',
            'required': True
        },
        'output_file': {
            'type': 'string',
            'label': 'Output JSON File',
            'description': 'Path to save the JSON output (optional)',
            'placeholder': './data/output.json',
            'required': False
        },
        'delimiter': {
            'type': 'string',
            'label': 'Delimiter',
            'description': 'CSV delimiter character',
            'default': ',',
            'required': False
        },
        'has_header': {
            'type': 'boolean',
            'label': 'Has Header Row',
            'description': 'Whether the CSV has a header row',
            'default': True,
            'required': False
        },
        'indent': {
            'type': 'number',
            'label': 'JSON Indent',
            'description': 'Number of spaces for JSON indentation',
            'default': 2,
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'data': {'type': 'array'},
        'row_count': {'type': 'number'},
        'output_file': {'type': 'string'}
    },

    # Execution settings
    timeout=60,
    retryable=True,
    max_retries=2,

    # Documentation
    examples=[
        {
            'name': 'Convert sales data',
            'description': 'Convert sales.csv to JSON',
            'params': {
                'input_file': './data/sales.csv',
                'output_file': './data/sales.json',
                'has_header': True
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class CsvToJson(CompositeModule):
    """
    CSV to JSON Composite Module

    This composite module:
    1. Reads a CSV file
    2. Converts to JSON format
    3. Optionally saves to output file
    """

    def _build_output(self, metadata):
        """Build output with conversion results"""
        csv_data = self.step_results.get('read_csv', {})
        data = csv_data.get('data', [])

        return {
            'status': 'success',
            'data': data,
            'row_count': len(data) if isinstance(data, list) else 0,
            'output_file': self.params.get('output_file', '')
        }
