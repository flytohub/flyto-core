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
    module_id='data.text.template',
    version='1.0.0',
    category='data',
    tags=['data', 'text', 'template', 'string', 'format'],
    label='Text Template',
    label_key='modules.data.text.template.label',
    description='Fill text template with variables',
    description_key='modules.data.text.template.description',
    icon='FileText',
    color='#8B5CF6',

    # Phase 2: Execution settings
    # No timeout - template filling is instant
    retryable=False,  # Template errors won't fix themselves
    concurrent_safe=True,  # Stateless operation

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'template': {
            'type': 'text',
            'label': 'Template',
            'label_key': 'modules.data.text.template.params.template.label',
            'description': 'Text template with {variable} placeholders',
            'description_key': 'modules.data.text.template.params.template.description',
            'placeholder': 'Hello {name}, you have {count} messages.',
            'required': True
        },
        'variables': {
            'type': 'object',
            'label': 'Variables',
            'label_key': 'modules.data.text.template.params.variables.label',
            'description': 'Object with variable values',
            'description_key': 'modules.data.text.template.params.variables.description',
            'placeholder': {'name': 'John', 'count': 5},
            'required': True
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'result': {'type': 'string', 'description': 'Filled template'}
    },
    examples=[
        {
            'name': 'Fill template',
            'params': {
                'template': 'Hello {name}, you scored {score} points!',
                'variables': {'name': 'Alice', 'score': 95}
            },
            'expected_output': {
                'status': 'success',
                'result': 'Hello Alice, you scored 95 points!'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class TextTemplateModule(BaseModule):
    """Fill text template with variables"""

    module_name = "Text Template"
    module_description = "Replace {placeholders} in template with variable values"

    def validate_params(self):
        if 'template' not in self.params or not self.params['template']:
            raise ValueError("Missing required parameter: template")
        if 'variables' not in self.params or not isinstance(self.params['variables'], dict):
            raise ValueError("Missing or invalid parameter: variables (must be object)")

        self.template = self.params['template']
        self.variables = self.params['variables']

    async def execute(self) -> Any:
        try:
            result = self.template.format(**self.variables)
            return {
                'status': 'success',
                'result': result
            }
        except KeyError as e:
            return {
                'status': 'error',
                'message': f'Missing variable in template: {str(e)}'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Template error: {str(e)}'
            }
