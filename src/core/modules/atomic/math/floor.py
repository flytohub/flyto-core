"""
Advanced Math Operations Modules

Provides extended mathematical operations.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
import math


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

    # Phase 2: Execution settings
    timeout=None,
    retryable=False,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'number': {
            'type': 'number',
            'label': 'Number',
            'label_key': 'modules.math.floor.params.number.label',
            'description': 'Number to floor',
            'description_key': 'modules.math.floor.params.number.description',
            'required': True
        }
    },
    output_schema={
        'result': {'type': 'number'},
        'original': {'type': 'number'}
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
    author='Flyto2 Team',
    license='MIT'
)
class MathFloorModule(BaseModule):
    """Math Floor Module"""

    def validate_params(self):
        self.number = self.params.get('number')

        if self.number is None:
            raise ValueError("number is required")

    async def execute(self) -> Any:
        result = math.floor(self.number)

        return {
            "result": result,
            "original": self.number
        }


