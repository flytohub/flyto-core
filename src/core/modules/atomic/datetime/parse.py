"""
Datetime Operations Modules

Provides date and time manipulation capabilities.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from datetime import datetime, timedelta
import time


@register_module(
    module_id='datetime.parse',
    version='1.0.0',
    category='utility',
    subcategory='datetime',
    tags=['datetime', 'parse', 'date', 'time'],
    label='Parse DateTime',
    label_key='modules.datetime.parse.label',
    description='Parse string to datetime',
    description_key='modules.datetime.parse.description',
    icon='Calendar',
    color='#8B5CF6',

    # Connection types
    input_types=['string', 'text'],
    output_types=['datetime', 'json'],

    # Phase 2: Execution settings
    timeout=None,
    retryable=False,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'datetime_string': {
            'type': 'string',
            'label': 'DateTime String',
            'label_key': 'modules.datetime.parse.params.datetime_string.label',
            'description': 'DateTime string to parse',
            'description_key': 'modules.datetime.parse.params.datetime_string.description',
            'required': True
        },
        'format': {
            'type': 'string',
            'label': 'Format',
            'label_key': 'modules.datetime.parse.params.format.label',
            'description': 'strptime format string (leave empty for ISO)',
            'description_key': 'modules.datetime.parse.params.format.description',
            'required': False
        }
    },
    output_schema={
        'result': {'type': 'string'},
        'timestamp': {'type': 'number'},
        'year': {'type': 'number'},
        'month': {'type': 'number'},
        'day': {'type': 'number'},
        'hour': {'type': 'number'},
        'minute': {'type': 'number'},
        'second': {'type': 'number'}
    },
    examples=[
        {
            'title': 'Parse ISO format',
            'params': {
                'datetime_string': '2024-01-15T10:30:00'
            }
        },
        {
            'title': 'Parse custom format',
            'params': {
                'datetime_string': 'January 15, 2024',
                'format': '%B %d, %Y'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class DateTimeParseModule(BaseModule):
    """DateTime Parse Module"""

    def validate_params(self):
        self.datetime_string = self.params.get('datetime_string')
        self.format = self.params.get('format')

        if not self.datetime_string:
            raise ValueError("datetime_string is required")

    async def execute(self) -> Any:
        # Parse datetime
        if self.format:
            dt = datetime.strptime(self.datetime_string, self.format)
        else:
            # Try ISO format
            try:
                dt = datetime.fromisoformat(self.datetime_string.replace('Z', '+00:00'))
            except:
                raise ValueError(f"Invalid datetime format: {self.datetime_string}")

        return {
            "result": dt.isoformat(),
            "timestamp": dt.timestamp(),
            "year": dt.year,
            "month": dt.month,
            "day": dt.day,
            "hour": dt.hour,
            "minute": dt.minute,
            "second": dt.second
        }


