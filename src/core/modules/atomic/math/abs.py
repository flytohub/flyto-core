"""
Math Absolute Value Module
Get the absolute value of a number
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='math.abs',
    version='1.0.0',
    category='math',
    subcategory='operations',
    tags=['math', 'abs', 'absolute', 'number'],
    label='Absolute Value',
    label_key='modules.math.abs.label',
    description='Get absolute value of a number',
    description_key='modules.math.abs.description',
    icon='Equal',
    color='#3B82F6',

    input_types=['number'],
    output_types=['number'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'math.*', 'file.*', 'api.*', 'notification.*', 'flow.*'],

    timeout=None,
    retryable=False,
    concurrent_safe=True,

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
            'description': 'Absolute value'
        },
        'original': {
            'type': 'number',
            'description': 'Original number'
        }
    },
    examples=[
        {
            'title': 'Absolute of negative number',
            'params': {
                'number': -5
            }
        },
        {
            'title': 'Absolute of positive number',
            'params': {
                'number': 3.14
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def math_abs(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get absolute value of a number."""
    params = context['params']
    number = params.get('number')

    if number is None:
        return {
            'ok': False,
            'error': 'Missing required parameter: number',
            'error_code': 'MISSING_PARAM'
        }

    result = abs(number)

    return {
        'result': result,
        'original': number
    }
