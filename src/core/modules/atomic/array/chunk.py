"""
Advanced Array Operations Modules

Provides extended array manipulation capabilities.
"""
from typing import Any, Dict, List
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='array.chunk',
    version='1.0.0',
    category='array',
    subcategory='transform',
    tags=['array', 'chunk', 'split', 'batch'],
    label='Array Chunk',
    label_key='modules.array.chunk.label',
    description='Split array into chunks of specified size',
    description_key='modules.array.chunk.description',
    icon='Grid',
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
            'label_key': 'modules.array.chunk.params.array.label',
            'description': 'Array to chunk',
            'description_key': 'modules.array.chunk.params.array.description',
            'required': True
        },
        'size': {
            'type': 'number',
            'label': 'Chunk Size',
            'label_key': 'modules.array.chunk.params.size.label',
            'description': 'Size of each chunk',
            'description_key': 'modules.array.chunk.params.size.description',
            'required': True,
            'min': 1
        }
    },
    output_schema={
        'result': {'type': 'array'},
        'chunks': {'type': 'number'}
    },
    examples=[
        {
            'title': 'Chunk into groups of 3',
            'params': {
                'array': [1, 2, 3, 4, 5, 6, 7, 8, 9],
                'size': 3
            }
        },
        {
            'title': 'Batch process items',
            'params': {
                'array': ['a', 'b', 'c', 'd', 'e'],
                'size': 2
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class ArrayChunkModule(BaseModule):
    """Array Chunk Module"""

    def validate_params(self):
        self.array = self.params.get('array', [])
        self.size = self.params.get('size')

        if not isinstance(self.array, list):
            raise ValueError("array must be a list")

        if not self.size or self.size < 1:
            raise ValueError("size must be a positive number")

    async def execute(self) -> Any:
        result = []

        for i in range(0, len(self.array), self.size):
            result.append(self.array[i:i + self.size])

        return {
            "result": result,
            "chunks": len(result)
        }


