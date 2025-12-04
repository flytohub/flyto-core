"""
Math Absolute Value Module
Get the absolute value of a number
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


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
            'label_key': 'modules.math.abs.params.number.label',
            'description': 'Number to get absolute value of',
            'description_key': 'modules.math.abs.params.number.description',
            'required': True
        }
    },
    output_schema={
        'result': {'type': 'number'},
        'original': {'type': 'number'}
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
class MathAbsModule(BaseModule):
    """Math Absolute Value Module"""

    def validate_params(self):
        self.number = self.params.get('number')

        if self.number is None:
            raise ValueError("number is required")

    async def execute(self) -> Any:
        result = abs(self.number)

        return {
            "result": result,
            "original": self.number
        }
