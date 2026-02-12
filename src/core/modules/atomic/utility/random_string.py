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
    module_id='utility.random.string',
    version='1.0.0',
    category='utility',
    tags=['utility', 'random', 'string', 'generator', 'uuid'],
    label='Random String',
    label_key='modules.utility.random.string.label',
    description='Generate random string or UUID',
    description_key='modules.utility.random.string.description',
    icon='Key',
    color='#EC4899',

    # Connection types
    input_types=[],
    output_types=['string'],


    can_receive_from=['start', 'flow.*'],
    can_connect_to=['data.*', 'string.*', 'file.*', 'api.*', 'notification.*', 'flow.*', 'utility.*'],    # Phase 2: Execution settings
    retryable=False,  # Random generation is deterministic
    concurrent_safe=True,  # Multiple random operations can run in parallel

    # Phase 2: Security settings
    requires_credentials=False,  # No credentials needed
    handles_sensitive_data=False,  # No sensitive data handled
    required_permissions=[],  # No special permissions needed

    params_schema={
        'length': {
            'type': 'number',
            'label': 'Length',
            'label_key': 'modules.utility.random.string.params.length.label',
            'description': 'String length',
            'description_key': 'modules.utility.random.string.params.length.description',
            'default': 16,
            'min': 1,
            'max': 256,
            'required': False
        },
        'charset': {
            'type': 'select',
            'label': 'Character Set',
            'label_key': 'modules.utility.random.string.params.charset.label',
            'description': 'Which characters to use',
            'description_key': 'modules.utility.random.string.params.charset.description',
            'options': [
                {'value': 'alphanumeric', 'label': 'Alphanumeric (a-z, A-Z, 0-9)'},
                {'value': 'letters', 'label': 'Letters only (a-z, A-Z)'},
                {'value': 'lowercase', 'label': 'Lowercase letters (a-z)'},
                {'value': 'uppercase', 'label': 'Uppercase letters (A-Z)'},
                {'value': 'numbers', 'label': 'Numbers only (0-9)'},
                {'value': 'hex', 'label': 'Hexadecimal (0-9, a-f)'},
                {'value': 'uuid', 'label': 'UUID v4'}
            ],
            'default': 'alphanumeric',
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.utility.random.string.output.status.description'},
        'value': {'type': 'string', 'description': 'Random string',
                'description_key': 'modules.utility.random.string.output.value.description'}
    },
    examples=[
        {
            'name': 'Random alphanumeric',
            'params': {
                'length': 16,
                'charset': 'alphanumeric'
            }
        },
        {
            'name': 'Generate UUID',
            'params': {
                'charset': 'uuid'
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=5000,
)
class RandomStringModule(BaseModule):
    """Generate random string"""

    module_name = "Random String"
    module_description = "Generate random string or UUID"

    def validate_params(self) -> None:
        self.length = self.params.get('length', 16)
        self.charset = self.params.get('charset', 'alphanumeric')

    async def execute(self) -> Any:
        if self.charset == 'uuid':
            value = str(uuid.uuid4())
        else:
            # Define character sets
            charsets = {
                'alphanumeric': string.ascii_letters + string.digits,
                'letters': string.ascii_letters,
                'lowercase': string.ascii_lowercase,
                'uppercase': string.ascii_uppercase,
                'numbers': string.digits,
                'hex': string.hexdigits.lower()
            }

            chars = charsets.get(self.charset, charsets['alphanumeric'])
            value = ''.join(random.choice(chars) for _ in range(self.length))

        return {
            'status': 'success',
            'value': value
        }


