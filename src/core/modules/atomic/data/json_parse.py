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
    module_id='data.json.parse',
    version='1.0.0',
    category='data',
    tags=['data', 'json', 'parse', 'transform'],
    label='Parse JSON',
    label_key='modules.data.json.parse.label',
    description='Parse JSON string into object',
    description_key='modules.data.json.parse.description',
    icon='Code',
    color='#F59E0B',

    # Phase 2: Execution settings
    # No timeout - JSON parsing is instant
    retryable=False,  # Parse errors won't fix themselves
    concurrent_safe=True,  # Stateless operation

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'json_string': {
            'type': 'text',
            'label': 'JSON String',
            'label_key': 'modules.data.json.parse.params.json_string.label',
            'description': 'JSON string to parse',
            'description_key': 'modules.data.json.parse.params.json_string.description',
            'placeholder': '{"name": "John", "age": 30}',
            'required': True
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'data': {'type': 'object', 'description': 'Parsed object'}
    },
    examples=[
        {
            'name': 'Parse JSON string',
            'params': {
                'json_string': '{"name": "John", "age": 30}'
            },
            'expected_output': {
                'status': 'success',
                'data': {'name': 'John', 'age': 30}
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class JSONParseModule(BaseModule):
    """Parse JSON string"""

    module_name = "Parse JSON"
    module_description = "Parse JSON string into object"

    def validate_params(self):
        if 'json_string' not in self.params:
            raise ValueError("Missing required parameter: json_string")
        self.json_string = self.params['json_string']

    async def execute(self) -> Any:
        try:
            data = json.loads(self.json_string)
            return {
                'status': 'success',
                'data': data
            }
        except json.JSONDecodeError as e:
            return {
                'status': 'error',
                'message': f'Invalid JSON: {str(e)}'
            }


