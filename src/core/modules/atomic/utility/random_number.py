"""
Utility Modules
Helper modules for delays, random data, date/time operations, etc.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
import asyncio
import random
import string
from datetime import datetime, timedelta
import hashlib
import uuid


@register_module(
    module_id='utility.random.number',
    version='1.0.0',
    category='utility',
    tags=['utility', 'random', 'number', 'generator'],
    label='Random Number',
    label_key='modules.utility.random.number.label',
    description='Generate random number in range',
    description_key='modules.utility.random.number.description',
    icon='Shuffle',
    color='#EC4899',

    # Connection types
    input_types=['any'],
    output_types=['any'],

    # Phase 2: Execution settings
    retryable=False,  # Random generation is deterministic
    concurrent_safe=True,  # Multiple random operations can run in parallel

    # Phase 2: Security settings
    requires_credentials=False,  # No credentials needed
    handles_sensitive_data=False,  # No sensitive data handled
    required_permissions=[],  # No special permissions needed

    params_schema={
        'min': {
            'type': 'number',
            'label': 'Minimum',
            'label_key': 'modules.utility.random.number.params.min.label',
            'description': 'Minimum value (inclusive)',
            'description_key': 'modules.utility.random.number.params.min.description',
            'default': 0,
            'required': False
        },
        'max': {
            'type': 'number',
            'label': 'Maximum',
            'label_key': 'modules.utility.random.number.params.max.label',
            'description': 'Maximum value (inclusive)',
            'description_key': 'modules.utility.random.number.params.max.description',
            'default': 100,
            'required': False
        },
        'decimals': {
            'type': 'number',
            'label': 'Decimal Places',
            'label_key': 'modules.utility.random.number.params.decimals.label',
            'description': 'Number of decimal places (0 for integers)',
            'description_key': 'modules.utility.random.number.params.decimals.description',
            'default': 0,
            'min': 0,
            'max': 10,
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'value': {'type': 'number', 'description': 'Random number'}
    },
    examples=[
        {
            'name': 'Random integer 1-100',
            'params': {
                'min': 1,
                'max': 100,
                'decimals': 0
            }
        },
        {
            'name': 'Random float 0-1',
            'params': {
                'min': 0,
                'max': 1,
                'decimals': 2
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class RandomNumberModule(BaseModule):
    """Generate random number"""

    module_name = "Random Number"
    module_description = "Generate random number in specified range"

    def validate_params(self):
        self.min = self.params.get('min', 0)
        self.max = self.params.get('max', 100)
        self.decimals = self.params.get('decimals', 0)

        if self.min > self.max:
            raise ValueError("min must be less than or equal to max")

    async def execute(self) -> Any:
        if self.decimals == 0:
            value = random.randint(int(self.min), int(self.max))
        else:
            value = random.uniform(self.min, self.max)
            value = round(value, self.decimals)

        return {
            'status': 'success',
            'value': value
        }


