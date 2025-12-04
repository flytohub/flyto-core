"""
Advanced Array Operations Modules

Provides extended array manipulation capabilities.
"""
from typing import Any, Dict, List
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='array.flatten',
    version='1.0.0',
    category='array',
    subcategory='transform',
    tags=['array', 'flatten', 'nested'],
    label='Array Flatten',
    label_key='modules.array.flatten.label',
    description='Flatten nested arrays into single array',
    description_key='modules.array.flatten.description',
    icon='Layers',
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
            'label_key': 'modules.array.flatten.params.array.label',
            'description': 'Nested array to flatten',
            'description_key': 'modules.array.flatten.params.array.description',
            'required': True
        },
        'depth': {
            'type': 'number',
            'label': 'Depth',
            'label_key': 'modules.array.flatten.params.depth.label',
            'description': 'Depth level to flatten (default: 1, use -1 for infinite)',
            'description_key': 'modules.array.flatten.params.depth.description',
            'default': 1,
            'required': False
        }
    },
    output_schema={
        'result': {'type': 'array'},
        'length': {'type': 'number'}
    },
    examples=[
        {
            'title': 'Flatten one level',
            'params': {
                'array': [[1, 2], [3, 4], [5, 6]],
                'depth': 1
            }
        },
        {
            'title': 'Flatten all levels',
            'params': {
                'array': [[1, [2, [3, [4]]]]],
                'depth': -1
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class ArrayFlattenModule(BaseModule):
    """Array Flatten Module"""

    def validate_params(self):
        self.array = self.params.get('array', [])
        self.depth = self.params.get('depth', 1)

        if not isinstance(self.array, list):
            raise ValueError("array must be a list")

    async def execute(self) -> Any:
        def flatten(arr, depth):
            if depth == 0:
                return arr

            result = []
            for item in arr:
                if isinstance(item, list):
                    if depth == -1:
                        result.extend(flatten(item, -1))
                    else:
                        result.extend(flatten(item, depth - 1))
                else:
                    result.append(item)
            return result

        result = flatten(self.array, self.depth)

        return {
            "result": result,
            "length": len(result)
        }


