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
    module_id='utility.hash.md5',
    version='1.0.0',
    category='utility',
    tags=['utility', 'hash', 'md5', 'crypto', 'checksum'],
    label='MD5 Hash',
    label_key='modules.utility.hash.md5.label',
    description='Calculate MD5 hash of text',
    description_key='modules.utility.hash.md5.description',
    icon='Hash',
    color='#8B5CF6',

    # Connection types
    input_types=['any'],
    output_types=['any'],

    # Phase 2: Execution settings
    retryable=False,  # Hash operations are deterministic
    concurrent_safe=True,  # Multiple hash operations can run in parallel

    # Phase 2: Security settings
    requires_credentials=False,  # No credentials needed
    handles_sensitive_data=False,  # Hash input might be sensitive but output is not
    required_permissions=[],  # No special permissions needed

    params_schema={
        'text': {
            'type': 'text',
            'label': 'Text',
            'label_key': 'modules.utility.hash.md5.params.text.label',
            'description': 'Text to hash',
            'description_key': 'modules.utility.hash.md5.params.text.description',
            'placeholder': 'Hello World',
            'required': True
        },
        'encoding': {
            'type': 'string',
            'label': 'Encoding',
            'label_key': 'modules.utility.hash.md5.params.encoding.label',
            'description': 'Text encoding',
            'description_key': 'modules.utility.hash.md5.params.encoding.description',
            'default': 'utf-8',
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'hash': {'type': 'string', 'description': 'MD5 hash (hexadecimal)'}
    },
    examples=[
        {
            'name': 'Hash text',
            'params': {
                'text': 'Hello World'
            },
            'expected_output': {
                'status': 'success',
                'hash': 'b10a8db164e0754105b7a99be72e3fe5'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class HashMD5Module(BaseModule):
    """Calculate MD5 hash"""

    module_name = "MD5 Hash"
    module_description = "Calculate MD5 hash of text"

    def validate_params(self):
        if 'text' not in self.params:
            raise ValueError("Missing required parameter: text")

        self.text = self.params['text']
        self.encoding = self.params.get('encoding', 'utf-8')

    async def execute(self) -> Any:
        hash_obj = hashlib.md5(self.text.encode(self.encoding))
        hash_hex = hash_obj.hexdigest()

        return {
            'status': 'success',
            'hash': hash_hex
        }
