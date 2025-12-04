"""
Advanced String Operations Modules

Provides extended string manipulation capabilities.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='string.titlecase',
    version='1.0.0',
    category='string',
    subcategory='transform',
    tags=['string', 'titlecase', 'case'],
    label='Title Case String',
    label_key='modules.string.titlecase.label',
    description='Convert string to title case',
    description_key='modules.string.titlecase.description',
    icon='Type',
    color='#8B5CF6',

    # Connection types
    input_types=['text', 'string'],
    output_types=['text', 'string'],

    # Phase 2: Execution settings
    timeout=None,
    retryable=False,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'text': {
            'type': 'string',
            'label': 'Text',
            'label_key': 'modules.string.titlecase.params.text.label',
            'description': 'Text to convert to title case',
            'description_key': 'modules.string.titlecase.params.text.description',
            'required': True
        }
    },
    output_schema={
        'result': {'type': 'string'}
    },
    examples=[
        {
            'title': 'Convert to title case',
            'params': {
                'text': 'hello world from flyto2'
            }
        },
        {
            'title': 'Format name',
            'params': {
                'text': 'john doe'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class StringTitlecaseModule(BaseModule):
    """Title Case String Module"""

    def validate_params(self):
        self.text = self.params.get('text', '')

    async def execute(self) -> Any:
        return {
            "result": self.text.title()
        }
