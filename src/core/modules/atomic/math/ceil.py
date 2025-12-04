"""
Advanced Math Operations Modules

Provides extended mathematical operations.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
import math


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
            'label_key': 'modules.math.ceil.params.number.label',
            'description': 'Number to ceil',
            'description_key': 'modules.math.ceil.params.number.description',
            'required': True
        }
    },
    output_schema={
        'result': {'type': 'number'},
        'original': {'type': 'number'}
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
class MathCeilModule(BaseModule):
    """Math Ceiling Module"""

    def validate_params(self):
        self.number = self.params.get('number')

        if self.number is None:
            raise ValueError("number is required")

    async def execute(self) -> Any:
        result = math.ceil(self.number)

        return {
            "result": result,
            "original": self.number
        }


