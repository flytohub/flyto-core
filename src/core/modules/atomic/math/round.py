"""
Math Round Module
Round a number to specified decimal places
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='math.round',
    version='1.0.0',
    category='math',
    subcategory='operations',
    tags=['math', 'round', 'number'],
    label='Round Number',
    label_key='modules.math.round.label',
    description='Round number to specified decimal places',
    description_key='modules.math.round.description',
    icon='Circle',
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
        presets.DECIMAL_PLACES(default=0),
    ),
    output_schema={
        'result': {
            'type': 'number',
            'description': 'Rounded value'
        ,
                'description_key': 'modules.math.round.output.result.description'},
        'original': {
            'type': 'number',
            'description': 'Original number'
        ,
                'description_key': 'modules.math.round.output.original.description'},
        'decimals': {
            'type': 'number',
            'description': 'Decimal places used'
        ,
                'description_key': 'modules.math.round.output.decimals.description'}
    },
    examples=[
        {
            'title': 'Round to integer',
            'params': {
                'number': 3.7
            }
        },
        {
            'title': 'Round to 2 decimal places',
            'params': {
                'number': 3.14159,
                'decimals': 2
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def math_round(context: Dict[str, Any]) -> Dict[str, Any]:
    """Round number to specified decimal places."""
    params = context['params']
    number = params.get('number')
    decimals = params.get('decimals', 0)

    if number is None:
        return {
            'ok': False,
            'error': 'Missing required parameter: number',
            'error_code': 'MISSING_PARAM'
        }

    result = round(number, decimals)

    return {
        'result': result,
        'original': number,
        'decimals': decimals
    }
