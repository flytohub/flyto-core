"""
Math Ceiling Module
Round number up to nearest integer
"""
from typing import Any, Dict
import math

from ...registry import register_module
from ...schema import compose, presets
from ...errors import ValidationError


@register_module(
    module_id='math.ceil',
    version='1.0.0',
    category='math',
    subcategory='operations',
    tags=['math', 'ceil', 'ceiling', 'number'],
    label='Ceiling Number',
    label_key='modules.math.ceil.label',
    description='Round number up to nearest integer',
    description_key='modules.math.ceil.description',
    icon='ArrowUp',
    color='#3B82F6',

    # Connection types
    input_types=['number'],
    output_types=['number'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'math.*', 'file.*', 'api.*', 'notification.*', 'flow.*'],

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
        presets.INPUT_NUMBER(required=True),
    ),
    output_schema={
        'result': {
            'type': 'number',
            'description': 'Ceiling value'
        ,
                'description_key': 'modules.math.ceil.output.result.description'},
        'original': {
            'type': 'number',
            'description': 'Original number'
        ,
                'description_key': 'modules.math.ceil.output.original.description'}
    },
    examples=[
        {
            'title': 'Ceiling positive number',
            'params': {
                'number': 3.2
            }
        },
        {
            'title': 'Ceiling negative number',
            'params': {
                'number': -2.7
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def math_ceil(context: Dict[str, Any]) -> Dict[str, Any]:
    """Round number up to nearest integer."""
    params = context['params']
    number = params.get('number')

    if number is None:
        raise ValidationError("Missing required parameter: number", field="number")

    result = math.ceil(number)

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': number
        }
    }
