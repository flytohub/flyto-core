"""
Array Join Module

Join array elements into string.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets
from ...errors import ValidationError, InvalidTypeError


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
        presets.SEPARATOR(default=','),
    ),
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Joined string'
        ,
                'description_key': 'modules.array.join.output.result.description'}
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
    author='Flyto Team',
    license='MIT'
)
async def array_join(context: Dict[str, Any]) -> Dict[str, Any]:
    """Join array elements into string."""
    params = context['params']
    array = params.get('array', [])
    separator = params.get('separator', ',')

    if not isinstance(array, list):
        raise InvalidTypeError("array must be a list", field="array", expected_type="list")

    result = separator.join(str(item) for item in array)

    return {
        'ok': True,
        'data': {
            'result': result
        }
    }
