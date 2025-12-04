"""
Array Map Module

Transform each element in an array using various operations.
"""
from typing import Any, Dict, List
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='array.map',
    version='1.0.0',
    category='array',
    subcategory='transform',
    tags=['array', 'map', 'transform'],
    label='Array Map',
    label_key='modules.array.map.label',
    description='Transform each element in an array',
    description_key='modules.array.map.description',
    icon='MapPin',
    color='#8B5CF6',

    # Connection types
    input_types=['array', 'json'],
    output_types=['array', 'json'],

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
            'label_key': 'modules.array.map.params.array.label',
            'description': 'Input array to transform',
            'description_key': 'modules.array.map.params.array.description',
            'required': True
        },
        'operation': {
            'type': 'select',
            'label': 'Operation',
            'label_key': 'modules.array.map.params.operation.label',
            'description': 'Transformation to apply',
            'description_key': 'modules.array.map.params.operation.description',
            'options': [
                {'label': 'Multiply', 'value': 'multiply'},
                {'label': 'Add', 'value': 'add'},
                {'label': 'Extract field', 'value': 'extract'},
                {'label': 'To uppercase', 'value': 'uppercase'},
                {'label': 'To lowercase', 'value': 'lowercase'}
            ],
            'required': True
        },
        'value': {
            'type': 'any',
            'label': 'Value',
            'label_key': 'modules.array.map.params.value.label',
            'description': 'Value for operation (number for math, field name for extract)',
            'description_key': 'modules.array.map.params.value.description',
            'required': False
        }
    },
    output_schema={
        'result': {'type': 'array'},
        'length': {'type': 'number'}
    },
    examples=[
        {
            'title': 'Multiply numbers',
            'params': {
                'array': [1, 2, 3, 4, 5],
                'operation': 'multiply',
                'value': 2
            }
        },
        {
            'title': 'Extract field from objects',
            'params': {
                'array': [{'name': 'Alice', 'age': 30}, {'name': 'Bob', 'age': 25}],
                'operation': 'extract',
                'value': 'name'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class ArrayMapModule(BaseModule):
    """Array Map Module"""

    def validate_params(self):
        self.array = self.params.get('array', [])
        self.operation = self.params.get('operation')
        self.value = self.params.get('value')

        if not isinstance(self.array, list):
            raise ValueError("array must be a list")

    async def execute(self) -> Any:
        result = []

        for item in self.array:
            if self.operation == 'multiply':
                result.append(item * (self.value or 1))
            elif self.operation == 'add':
                result.append(item + (self.value or 0))
            elif self.operation == 'extract':
                if isinstance(item, dict) and self.value:
                    result.append(item.get(self.value))
                else:
                    result.append(None)
            elif self.operation == 'uppercase':
                result.append(str(item).upper())
            elif self.operation == 'lowercase':
                result.append(str(item).lower())
            else:
                result.append(item)

        return {
            "result": result,
            "length": len(result)
        }
