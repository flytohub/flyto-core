"""
CSV to JSON Composite Module

Reads a CSV file and converts it to JSON format.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.data.csv_to_json',
    label='CSV to JSON',
    icon='FileSpreadsheet',
    color='#059669',

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

    params_schema={
        'input_file': {
            'type': 'string',
            'label': 'Input CSV File',
            'required': True,
            'placeholder': './data/input.csv'
        },
        'output_file': {
            'type': 'string',
            'label': 'Output JSON File',
            'placeholder': './data/output.json'
        },
        'delimiter': {
            'type': 'string',
            'label': 'Delimiter',
            'default': ','
        },
        'has_header': {
            'type': 'boolean',
            'label': 'Has Header Row',
            'default': True
        },
        'indent': {
            'type': 'number',
            'label': 'Indent Size',
            'default': 2
        }
    },

    output_schema={
        'status': {'type': 'string'},
        'data': {'type': 'array'},
        'row_count': {'type': 'number'},
        'output_file': {'type': 'string'}
    },

    timeout=60,
    retryable=True,
    max_retries=2,
)
class CsvToJson(CompositeModule):
    """CSV to JSON - reads CSV and converts to JSON format"""

    def _build_output(self, metadata):
        csv_data = self.step_results.get('read_csv', {})
        data = csv_data.get('data', [])

        return {
            'status': 'success',
            'data': data,
            'row_count': len(data) if isinstance(data, list) else 0,
            'output_file': self.params.get('output_file', '')
        }
