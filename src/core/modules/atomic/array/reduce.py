"""
Advanced Array Operations Modules

Provides extended array manipulation capabilities.
"""
from typing import Any, Dict, List
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='array.reduce',
    version='1.0.0',
    category='array',
    subcategory='aggregate',
    tags=['array', 'reduce', 'aggregate'],
    label='Array Reduce',
    label_key='modules.array.reduce.label',
    description='Reduce array to single value',
    description_key='modules.array.reduce.description',
    icon='TrendingDown',
    color='#EF4444',

    # Connection types
    input_types=['array', 'json'],
    output_types=['any'],

    # Phase 2: Execution settings
    timeout=None,
    retryable=False,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'array': {
            'type': 'array',
            'label': 'Array',
            'label_key': 'modules.array.reduce.params.array.label',
            'description': 'Input array to reduce',
            'description_key': 'modules.array.reduce.params.array.description',
            'required': True
        },
        'operation': {
            'type': 'select',
            'label': 'Operation',
            'label_key': 'modules.array.reduce.params.operation.label',
            'description': 'Reduction operation',
            'description_key': 'modules.array.reduce.params.operation.description',
            'options': [
                {'label': 'Sum', 'value': 'sum'},
                {'label': 'Product', 'value': 'product'},
                {'label': 'Average', 'value': 'average'},
                {'label': 'Min', 'value': 'min'},
                {'label': 'Max', 'value': 'max'},
                {'label': 'Join', 'value': 'join'}
            ],
            'required': True
        },
        'separator': {
            'type': 'string',
            'label': 'Separator',
            'label_key': 'modules.array.reduce.params.separator.label',
            'description': 'Separator for join operation',
            'description_key': 'modules.array.reduce.params.separator.description',
            'default': ',',
            'required': False
        }
    },
    output_schema={
        'result': {'type': 'any'},
        'operation': {'type': 'string'}
    },
    examples=[
        {
            'title': 'Sum numbers',
            'params': {
                'array': [1, 2, 3, 4, 5],
                'operation': 'sum'
            }
        },
        {
            'title': 'Join strings',
            'params': {
                'array': ['Hello', 'World', 'from', 'Flyto2'],
                'operation': 'join',
                'separator': ' '
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class ArrayReduceModule(BaseModule):
    """Array Reduce Module"""

    def validate_params(self):
        self.array = self.params.get('array', [])
        self.operation = self.params.get('operation')
        self.separator = self.params.get('separator', ',')

        if not isinstance(self.array, list):
            raise ValueError("array must be a list")

    async def execute(self) -> Any:
        if not self.array:
            return {"result": None, "operation": self.operation}

        result = None

        if self.operation == 'sum':
            result = sum(self.array)
        elif self.operation == 'product':
            result = 1
            for item in self.array:
                result *= item
        elif self.operation == 'average':
            result = sum(self.array) / len(self.array)
        elif self.operation == 'min':
            result = min(self.array)
        elif self.operation == 'max':
            result = max(self.array)
        elif self.operation == 'join':
            result = self.separator.join(str(item) for item in self.array)

        return {
            "result": result,
            "operation": self.operation
        }


