"""
Array Flatten Module

Flatten nested arrays into single array.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


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

    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'ai.*', 'notification.*', 'flow.*'],

    # Execution settings
    timeout=None,
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.INPUT_ARRAY(required=True),
        presets.FLATTEN_DEPTH(default=1),
    ),
    output_schema={
        'result': {
            'type': 'array',
            'description': 'Flattened array'
        },
        'length': {
            'type': 'number',
            'description': 'Length of flattened array'
        }
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
async def array_flatten(context: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten nested arrays into single array."""
    params = context['params']
    array = params.get('array', [])
    depth = params.get('depth', 1)

    if not isinstance(array, list):
        return {
            'ok': False,
            'error': 'array must be a list',
            'error_code': 'INVALID_TYPE'
        }

    def flatten(arr, d):
        if d == 0:
            return arr

        result = []
        for item in arr:
            if isinstance(item, list):
                if d == -1:
                    result.extend(flatten(item, -1))
                else:
                    result.extend(flatten(item, d - 1))
            else:
                result.append(item)
        return result

    result = flatten(array, depth)

    return {
        'result': result,
        'length': len(result)
    }
