"""
Advanced Array Operations Modules

Provides extended array manipulation capabilities.
"""
from typing import Any, Dict, List
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='array.difference',
    version='1.0.0',
    category='array',
    subcategory='set',
    tags=['array', 'difference', 'subtract'],
    label='Array Difference',
    label_key='modules.array.difference.label',
    description='Find elements in first array not in others',
    description_key='modules.array.difference.description',
    icon='Minus',
    color='#8B5CF6',

    # Connection types
    input_types=['array'],
    output_types=['array'],

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
            'label_key': 'modules.array.difference.params.array.label',
            'description': 'Base array',
            'description_key': 'modules.array.difference.params.array.description',
            'required': True
        },
        'subtract': {
            'type': 'array',
            'label': 'Subtract Arrays',
            'label_key': 'modules.array.difference.params.subtract.label',
            'description': 'Arrays to subtract from base',
            'description_key': 'modules.array.difference.params.subtract.description',
            'required': True
        }
    },
    output_schema={
        'result': {'type': 'array'},
        'length': {'type': 'number'}
    },
    examples=[
        {
            'title': 'Find unique elements',
            'params': {
                'array': [1, 2, 3, 4, 5],
                'subtract': [[2, 4], [5]]
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class ArrayDifferenceModule(BaseModule):
    """Array Difference Module"""

    def validate_params(self):
        self.array = self.params.get('array', [])
        self.subtract = self.params.get('subtract', [])

        if not isinstance(self.array, list):
            raise ValueError("array must be a list")

        if not isinstance(self.subtract, list):
            raise ValueError("subtract must be a list of arrays")

    async def execute(self) -> Any:
        result = set(self.array)

        # Subtract all arrays
        for arr in self.subtract:
            if isinstance(arr, list):
                result = result.difference(set(arr))

        result_list = list(result)

        return {
            "result": result_list,
            "length": len(result_list)
        }
