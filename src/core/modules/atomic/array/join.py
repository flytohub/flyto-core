"""
Advanced Array Operations Modules

Provides extended array manipulation capabilities.
"""
from typing import Any, Dict, List
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='array.join',
    version='1.0.0',
    category='array',
    subcategory='transform',
    tags=['array', 'join', 'string'],
    label='Array Join',
    label_key='modules.array.join.label',
    description='Join array elements into string',
    description_key='modules.array.join.description',
    icon='Link',
    color='#10B981',

    # Connection types
    input_types=['array'],
    output_types=['text', 'string'],

    # Phase 2: Execution settings
    timeout=None,
    retryable=False,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.INPUT_ARRAY(required=True),
        presets.SEPARATOR(default=','),
    ),
    output_schema={
        'result': {'type': 'string'}
    },
    examples=[
        {
            'title': 'Join with comma',
            'params': {
                'array': ['apple', 'banana', 'cherry'],
                'separator': ', '
            }
        },
        {
            'title': 'Join with newline',
            'params': {
                'array': ['Line 1', 'Line 2', 'Line 3'],
                'separator': '\n'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class ArrayJoinModule(BaseModule):
    """Array Join Module"""

    def validate_params(self):
        self.array = self.params.get('array', [])
        self.separator = self.params.get('separator', ',')

        if not isinstance(self.array, list):
            raise ValueError("array must be a list")

    async def execute(self) -> Any:
        result = self.separator.join(str(item) for item in self.array)

        return {
            "result": result
        }


