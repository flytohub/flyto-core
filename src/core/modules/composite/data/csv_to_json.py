"""
CSV to JSON Composite Module

Reads a CSV file and converts it to JSON format.
"""
from ..base import CompositeModule, register_composite, UIVisibility


@register_composite(
    module_id='composite.data.csv_to_json',
    version='1.0.0',
    category='data',
    subcategory='transform',
    tags=['data', 'csv', 'json', 'transform', 'file'],

    # Context requirements
    requires_context=None,
    provides_context=['data', 'file'],

    # UI metadata
    ui_visibility=UIVisibility.DEFAULT,
    ui_label='CSV to JSON',
    ui_label_key='composite.csv_to_json.label',
    ui_description='Read a CSV file and convert it to JSON format',
    ui_description_key='composite.csv_to_json.desc',
    ui_group='Data / Transform',
    ui_icon='FileSpreadsheet',
    ui_color='#059669',

    # UI form generation
    ui_params_schema={
        'input_file': {
            'type': 'string',
            'label': 'Input CSV File',
            'label_key': 'composite.csv_to_json.input_file.label',
            'description': 'Path to the CSV file to read',
            'description_key': 'composite.csv_to_json.input_file.desc',
            'placeholder': './data/input.csv',
            'required': True,
            'ui_component': 'input',
        },
        'output_file': {
            'type': 'string',
            'label': 'Output JSON File',
            'label_key': 'composite.csv_to_json.output_file.label',
            'description': 'Path to save the JSON output (optional)',
            'description_key': 'composite.csv_to_json.output_file.desc',
            'placeholder': './data/output.json',
            'required': False,
            'ui_component': 'input',
        },
        'delimiter': {
            'type': 'string',
            'label': 'Delimiter',
            'label_key': 'composite.csv_to_json.delimiter.label',
            'description': 'CSV delimiter character',
            'description_key': 'composite.csv_to_json.delimiter.desc',
            'default': ',',
            'required': False,
            'ui_component': 'input',
        },
        'has_header': {
            'type': 'boolean',
            'label': 'Has Header Row',
            'label_key': 'composite.csv_to_json.has_header.label',
            'description': 'Whether the CSV has a header row',
            'description_key': 'composite.csv_to_json.has_header.desc',
            'default': True,
            'required': False,
            'ui_component': 'checkbox',
        },
        'indent': {
            'type': 'number',
            'label': 'JSON Indent',
            'label_key': 'composite.csv_to_json.indent.label',
            'description': 'Number of spaces for JSON indentation',
            'description_key': 'composite.csv_to_json.indent.desc',
            'default': 2,
            'required': False,
            'ui_component': 'number',
        }
    },

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

    # Output schema
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
