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
    module_id='datetime.format',
    version='1.0.0',
    category='utility',
    subcategory='datetime',
    tags=['datetime', 'format', 'date', 'time'],
    label='Format DateTime',
    label_key='modules.datetime.format.label',
    description='Format datetime to string',
    description_key='modules.datetime.format.description',
    icon='Calendar',
    color='#8B5CF6',

    # Connection types
    input_types=['datetime', 'string'],
    output_types=['string', 'text'],

    # Phase 2: Execution settings
    timeout=None,
    retryable=False,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'datetime': {
            'type': 'string',
            'label': 'DateTime',
            'label_key': 'modules.datetime.format.params.datetime.label',
            'description': 'DateTime to format (ISO format or "now")',
            'description_key': 'modules.datetime.format.params.datetime.description',
            'default': 'now',
            'required': False
        },
        'format': {
            'type': 'string',
            'label': 'Format',
            'label_key': 'modules.datetime.format.params.format.label',
            'description': 'strftime format string',
            'description_key': 'modules.datetime.format.params.format.description',
            'default': '%Y-%m-%d %H:%M:%S',
            'required': False
        }
    },
    output_schema={
        'result': {'type': 'string'},
        'timestamp': {'type': 'number'}
    },
    examples=[
        {
            'title': 'Format current time',
            'params': {
                'datetime': 'now',
                'format': '%Y-%m-%d %H:%M:%S'
            }
        },
        {
            'title': 'Custom date format',
            'params': {
                'datetime': '2024-01-15T10:30:00',
                'format': '%B %d, %Y'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class DateTimeFormatModule(BaseModule):
    """DateTime Format Module"""

    def validate_params(self):
        self.datetime_str = self.params.get('datetime', 'now')
        self.format = self.params.get('format', '%Y-%m-%d %H:%M:%S')

    async def execute(self) -> Any:
        # Parse datetime
        if self.datetime_str == 'now':
            dt = datetime.now()
        else:
            # Try parsing ISO format
            try:
                dt = datetime.fromisoformat(self.datetime_str.replace('Z', '+00:00'))
            except:
                raise ValueError(f"Invalid datetime format: {self.datetime_str}")

        # Format datetime
        result = dt.strftime(self.format)
        timestamp = dt.timestamp()

        return {
            "result": result,
            "timestamp": timestamp
        }


