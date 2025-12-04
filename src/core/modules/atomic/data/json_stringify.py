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

    # Phase 2: Execution settings
    # No timeout - JSON stringify is instant
    retryable=False,  # Serialization errors won't fix themselves
    concurrent_safe=True,  # Stateless operation

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'data': {
            'type': 'object',
            'label': 'Data',
            'label_key': 'modules.data.json.stringify.params.data.label',
            'description': 'Object to stringify',
            'description_key': 'modules.data.json.stringify.params.data.description',
            'required': True
        },
        'pretty': {
            'type': 'boolean',
            'label': 'Pretty Print',
            'label_key': 'modules.data.json.stringify.params.pretty.label',
            'description': 'Format with indentation',
            'description_key': 'modules.data.json.stringify.params.pretty.description',
            'default': False,
            'required': False
        },
        'indent': {
            'type': 'number',
            'label': 'Indent Size',
            'label_key': 'modules.data.json.stringify.params.indent.label',
            'description': 'Indentation spaces (if pretty=true)',
            'description_key': 'modules.data.json.stringify.params.indent.description',
            'default': 2,
            'min': 1,
            'max': 8,
            'required': False
        }
    },
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


