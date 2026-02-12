"""
Array Reduce Module

Reduce array to single value using various operations.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets
from ...errors import ValidationError, InvalidTypeError


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
    input_types=['array'],
    output_types=['string', 'number'],

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
        presets.REDUCE_OPERATION(required=True),
        presets.SEPARATOR(default=','),
    ),
    output_schema={
        'result': {
            'type': 'any',
            'description': 'Reduced value'
        ,
                'description_key': 'modules.array.reduce.output.result.description'},
        'operation': {
            'type': 'string',
            'description': 'Operation that was applied'
        ,
                'description_key': 'modules.array.reduce.output.operation.description'}
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
                'array': ['Hello', 'World', 'from', 'Flyto'],
                'operation': 'join',
                'separator': ' '
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
async def array_reduce(context: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce array to single value."""
    params = context['params']
    array = params.get('array', [])
    operation = params.get('operation')
    separator = params.get('separator', ',')

    if not isinstance(array, list):
        raise InvalidTypeError("array must be a list", field="array", expected_type="list")

    if not array:
        return {
            'ok': True,
            'data': {'result': None, 'operation': operation}
        }

    result = None

    if operation == 'sum':
        result = sum(array)
    elif operation == 'product':
        result = 1
        for item in array:
            result *= item
    elif operation == 'average':
        result = sum(array) / len(array)
    elif operation == 'min':
        result = min(array)
    elif operation == 'max':
        result = max(array)
    elif operation == 'join':
        result = separator.join(str(item) for item in array)

    return {
        'ok': True,
        'data': {
            'result': result,
            'operation': operation
        }
    }
