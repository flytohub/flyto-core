"""
Array Chunk Module

Split array into chunks of specified size.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets
from ...errors import ValidationError, InvalidTypeError, InvalidValueError


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
    icon='Grid3x3',
    color='#8B5CF6',

    # Connection types
    input_types=['array'],
    output_types=['array'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'ai.*', 'notification.*', 'flow.*'],

    # Execution settings
    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.INPUT_ARRAY(required=True),
        presets.CHUNK_SIZE(required=True),
    ),
    output_schema={
        'result': {
            'type': 'array',
            'description': 'Array of chunks'
        ,
                'description_key': 'modules.array.chunk.output.result.description'},
        'chunks': {
            'type': 'number',
            'description': 'Number of chunks'
        ,
                'description_key': 'modules.array.chunk.output.chunks.description'}
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
async def array_chunk(context: Dict[str, Any]) -> Dict[str, Any]:
    """Split array into chunks of specified size."""
    params = context['params']
    array = params.get('array', [])
    size = params.get('size')

    if not isinstance(array, list):
        raise InvalidTypeError("array must be a list", field="array", expected_type="list")

    if not size or size < 1:
        raise InvalidValueError("size must be a positive number", field="size")

    result = []
    for i in range(0, len(array), size):
        result.append(array[i:i + size])

    return {
        'ok': True,
        'data': {
            'result': result,
            'chunks': len(result)
        }
    }
