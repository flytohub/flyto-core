"""
Math Round Module
Round a number to specified decimal places
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


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

    timeout=None,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'number': {
            'type': 'number',
            'label': 'Number',
            'label_key': 'modules.math.round.params.number.label',
            'description': 'Number to round',
            'description_key': 'modules.math.round.params.number.description',
            'required': True
        },
        'decimals': {
            'type': 'number',
            'label': 'Decimal Places',
            'label_key': 'modules.math.round.params.decimals.label',
            'description': 'Number of decimal places (default: 0)',
            'description_key': 'modules.math.round.params.decimals.description',
            'required': False,
            'default': 0
        }
    },
    output_schema={
        'result': {'type': 'number'},
        'original': {'type': 'number'}
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
class MathRoundModule(BaseModule):
    """Math Round Module"""

    def validate_params(self):
        self.number = self.params.get('number')
        self.decimals = self.params.get('decimals', 0)

        if self.number is None:
            raise ValueError("number is required")

    async def execute(self) -> Any:
        result = round(self.number, self.decimals)

        return {
            "result": result,
            "original": self.number,
            "decimals": self.decimals
        }
