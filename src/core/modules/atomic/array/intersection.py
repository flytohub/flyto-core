"""
Advanced Array Operations Modules

Provides extended array manipulation capabilities.
"""
from typing import Any, Dict, List
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='array.intersection',
    version='1.0.0',
    category='array',
    subcategory='set',
    tags=['array', 'intersection', 'common'],
    label='Array Intersection',
    label_key='modules.array.intersection.label',
    description='Find common elements between arrays',
    description_key='modules.array.intersection.description',
    icon='Intersect',
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
        'arrays': {
            'type': 'array',
            'label': 'Arrays',
            'label_key': 'modules.array.intersection.params.arrays.label',
            'description': 'Arrays to find intersection',
            'description_key': 'modules.array.intersection.params.arrays.description',
            'required': True
        }
    },
    output_schema={
        'result': {'type': 'array'},
        'length': {'type': 'number'}
    },
    examples=[
        {
            'title': 'Find common elements',
            'params': {
                'arrays': [[1, 2, 3, 4], [2, 3, 5], [2, 3, 6]]
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class ArrayIntersectionModule(BaseModule):
    """Array Intersection Module"""

    def validate_params(self):
        self.arrays = self.params.get('arrays', [])

        if not isinstance(self.arrays, list) or len(self.arrays) < 2:
            raise ValueError("arrays must be a list with at least 2 arrays")

    async def execute(self) -> Any:
        # Convert first array to set
        result = set(self.arrays[0])

        # Intersect with remaining arrays
        for arr in self.arrays[1:]:
            result = result.intersection(set(arr))

        result_list = list(result)

        return {
            "result": result_list,
            "length": len(result_list)
        }


