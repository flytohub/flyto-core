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
    module_id='utility.datetime.now',
    version='1.0.0',
    category='utility',
    tags=['utility', 'datetime', 'time', 'date', 'timestamp'],
    label='Current Date/Time',
    label_key='modules.utility.datetime.now.label',
    description='Get current date and time',
    description_key='modules.utility.datetime.now.description',
    icon='Calendar',
    color='#3B82F6',

    # Connection types
    input_types=['any'],
    output_types=['any'],

    # Phase 2: Execution settings
    retryable=False,  # Time operations are instant and deterministic
    concurrent_safe=True,  # Multiple time operations can run in parallel

    # Phase 2: Security settings
    requires_credentials=False,  # No credentials needed
    handles_sensitive_data=False,  # No sensitive data handled
    required_permissions=[],  # No special permissions needed

    params_schema={
        'format': {
            'type': 'select',
            'label': 'Format',
            'label_key': 'modules.utility.datetime.now.params.format.label',
            'description': 'Output format',
            'description_key': 'modules.utility.datetime.now.params.format.description',
            'options': [
                {'value': 'iso', 'label': 'ISO 8601 (2024-01-15T10:30:00)'},
                {'value': 'unix', 'label': 'Unix timestamp (seconds)'},
                {'value': 'unix_ms', 'label': 'Unix timestamp (milliseconds)'},
                {'value': 'date', 'label': 'Date only (2024-01-15)'},
                {'value': 'time', 'label': 'Time only (10:30:00)'},
                {'value': 'custom', 'label': 'Custom format'}
            ],
            'default': 'iso',
            'required': False
        },
        'custom_format': {
            'type': 'string',
            'label': 'Custom Format',
            'label_key': 'modules.utility.datetime.now.params.custom_format.label',
            'description': 'Python strftime format (if format=custom)',
            'description_key': 'modules.utility.datetime.now.params.custom_format.description',
            'placeholder': '%Y-%m-%d %H:%M:%S',
            'required': False
        },
        'timezone': {
            'type': 'string',
            'label': 'Timezone',
            'label_key': 'modules.utility.datetime.now.params.timezone.label',
            'description': 'Timezone (default: UTC)',
            'description_key': 'modules.utility.datetime.now.params.timezone.description',
            'placeholder': 'UTC',
            'default': 'UTC',
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'datetime': {'type': 'string', 'description': 'Formatted date/time'},
        'timestamp': {'type': 'number', 'description': 'Unix timestamp'},
        'iso': {'type': 'string', 'description': 'ISO format'}
    },
    examples=[
        {
            'name': 'Get current ISO datetime',
            'params': {
                'format': 'iso'
            }
        },
        {
            'name': 'Get Unix timestamp',
            'params': {
                'format': 'unix'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class DateTimeNowModule(BaseModule):
    """Get current date/time"""

    module_name = "Current Date/Time"
    module_description = "Get current date and time in various formats"

    def validate_params(self):
        self.format = self.params.get('format', 'iso')
        self.custom_format = self.params.get('custom_format', '%Y-%m-%d %H:%M:%S')
        self.timezone = self.params.get('timezone', 'UTC')

    async def execute(self) -> Any:
        now = datetime.utcnow()  # Always use UTC for consistency

        # Format output
        if self.format == 'iso':
            formatted = now.isoformat()
        elif self.format == 'unix':
            formatted = int(now.timestamp())
        elif self.format == 'unix_ms':
            formatted = int(now.timestamp() * 1000)
        elif self.format == 'date':
            formatted = now.strftime('%Y-%m-%d')
        elif self.format == 'time':
            formatted = now.strftime('%H:%M:%S')
        elif self.format == 'custom':
            formatted = now.strftime(self.custom_format)
        else:
            formatted = now.isoformat()

        return {
            'status': 'success',
            'datetime': formatted,
            'timestamp': int(now.timestamp()),
            'iso': now.isoformat()
        }


