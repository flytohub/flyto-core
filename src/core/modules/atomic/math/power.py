"""
Math Power Module
Raise number to a power
"""
from typing import Any, Dict
import math

from ...registry import register_module
from ...schema import compose, presets
from ...errors import ValidationError


@register_module(
    module_id='math.power',
    version='1.0.0',
    category='math',
    subcategory='operations',
    tags=['math', 'power', 'exponent', 'number'],
    label='Power/Exponent',
    label_key='modules.math.power.label',
    description='Raise number to a power',
    description_key='modules.math.power.description',
    icon='Zap',
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
        presets.MATH_BASE(required=True),
        presets.MATH_EXPONENT(required=True),
    ),
    output_schema={
        'result': {
            'type': 'number',
            'description': 'Result of base raised to exponent'
        ,
                'description_key': 'modules.math.power.output.result.description'},
        'base': {
            'type': 'number',
            'description': 'Base number'
        ,
                'description_key': 'modules.math.power.output.base.description'},
        'exponent': {
            'type': 'number',
            'description': 'Exponent used'
        ,
                'description_key': 'modules.math.power.output.exponent.description'}
    },
    examples=[
        {
            'title': 'Square a number',
            'params': {
                'base': 5,
                'exponent': 2
            }
        },
        {
            'title': 'Cube root',
            'params': {
                'base': 27,
                'exponent': 0.333333
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def math_power(context: Dict[str, Any]) -> Dict[str, Any]:
    """Raise number to a power."""
    params = context['params']
    base = params.get('base')
    exponent = params.get('exponent')

    if base is None:
        raise ValidationError("Missing required parameter: base", field="base")

    if exponent is None:
        raise ValidationError("Missing required parameter: exponent", field="exponent")

    result = math.pow(base, exponent)

    return {
        'ok': True,
        'data': {
            'result': result,
            'base': base,
            'exponent': exponent
        }
    }
