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
    module_id='data.json.stringify',
    version='1.0.0',
    category='data',
    tags=['data', 'json', 'stringify', 'serialize'],
    label='JSON Stringify',
    label_key='modules.data.json.stringify.label',
    description='Convert object to JSON string',
    description_key='modules.data.json.stringify.description',
    icon='FileCode',
    color='#F59E0B',

    # Execution settings
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.DATA_OBJECT(required=True),
        presets.PRETTY_PRINT(default=False),
        presets.INDENT_SIZE(default=2),
    ),
    output_schema={
        'status': {'type': 'string'},
        'json': {'type': 'string', 'description': 'JSON string'}
    },
    examples=[
        {
            'name': 'Stringify object',
            'params': {
                'data': {'name': 'John', 'age': 30},
                'pretty': True
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class JSONStringifyModule(BaseModule):
    """Convert object to JSON string"""

    module_name = "JSON Stringify"
    module_description = "Convert object to JSON string"

    def validate_params(self):
        if 'data' not in self.params:
            raise ValueError("Missing required parameter: data")

        self.data = self.params['data']
        self.pretty = self.params.get('pretty', False)
        self.indent = self.params.get('indent', 2)

    async def execute(self) -> Any:
        try:
            if self.pretty:
                json_str = json.dumps(self.data, indent=self.indent, ensure_ascii=False)
            else:
                json_str = json.dumps(self.data, ensure_ascii=False)

            return {
                'status': 'success',
                'json': json_str
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to stringify: {str(e)}'
            }


