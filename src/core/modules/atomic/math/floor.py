"""
Math Floor Module
Round number down to nearest integer
"""
from typing import Any, Dict
import math

from ...registry import register_module
from ...schema import compose, presets
from ...errors import ValidationError


@register_module(
    module_id='math.floor',
    version='1.0.0',
    category='math',
    subcategory='operations',
    tags=['math', 'floor', 'number'],
    label='Floor Number',
    label_key='modules.math.floor.label',
    description='Round number down to nearest integer',
    description_key='modules.math.floor.description',
    icon='ArrowDown',
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
            'description': 'Floored value'
        ,
                'description_key': 'modules.math.floor.output.result.description'},
        'original': {
            'type': 'number',
            'description': 'Original number'
        ,
                'description_key': 'modules.math.floor.output.original.description'}
    },
    examples=[
        {
            'title': 'Floor positive number',
            'params': {
                'number': 3.7
            }
        },
        {
            'title': 'Floor negative number',
            'params': {
                'number': -2.3
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
async def math_floor(context: Dict[str, Any]) -> Dict[str, Any]:
    """Round number down to nearest integer."""
    params = context['params']
    number = params.get('number')

    if number is None:
        raise ValidationError("Missing required parameter: number", field="number")

    result = math.floor(number)

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': number
        }
    }
