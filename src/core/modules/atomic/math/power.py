"""
Advanced Math Operations Modules

Provides extended mathematical operations.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
import math


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

    # Phase 2: Execution settings
    timeout=None,
    retryable=False,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'base': {
            'type': 'number',
            'label': 'Base',
            'label_key': 'modules.math.power.params.base.label',
            'description': 'Base number',
            'description_key': 'modules.math.power.params.base.description',
            'required': True
        },
        'exponent': {
            'type': 'number',
            'label': 'Exponent',
            'label_key': 'modules.math.power.params.exponent.label',
            'description': 'Power to raise to',
            'description_key': 'modules.math.power.params.exponent.description',
            'required': True
        }
    },
    output_schema={
        'result': {'type': 'number'},
        'base': {'type': 'number'},
        'exponent': {'type': 'number'}
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
class MathPowerModule(BaseModule):
    """Math Power Module"""

    def validate_params(self):
        self.base = self.params.get('base')
        self.exponent = self.params.get('exponent')

        if self.base is None or self.exponent is None:
            raise ValueError("base and exponent are required")

    async def execute(self) -> Any:
        result = math.pow(self.base, self.exponent)

        return {
            "result": result,
            "base": self.base,
            "exponent": self.exponent
        }
