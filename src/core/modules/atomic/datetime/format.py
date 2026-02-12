"""
Datetime Operations Modules

Provides date and time manipulation capabilities.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
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


    can_receive_from=['*'],
    can_connect_to=['data.*', 'string.*', 'file.*', 'api.*', 'notification.*', 'flow.*', 'utility.*'],    # Phase 2: Execution settings
    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.DATETIME_INPUT(default='now'),
        presets.DATETIME_FORMAT(default='%Y-%m-%d %H:%M:%S'),
    ),
    output_schema={
        'result': {'type': 'string', 'description': 'The operation result',
                'description_key': 'modules.datetime.format.output.result.description'},
        'timestamp': {'type': 'number', 'description': 'Unix timestamp',
                'description_key': 'modules.datetime.format.output.timestamp.description'}
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
    author='Flyto Team',
    license='MIT'
)
class DateTimeFormatModule(BaseModule):
    """DateTime Format Module"""

    def validate_params(self) -> None:
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
            except (ValueError, AttributeError) as e:
                raise ValueError(
                    f"Invalid datetime format: '{self.datetime_str}'. "
                    f"Expected ISO 8601 format (e.g., '2024-01-15T10:30:00Z'). "
                    f"Error: {e}"
                )

        # Format datetime
        result = dt.strftime(self.format)
        timestamp = dt.timestamp()

        return {
            "result": result,
            "timestamp": timestamp
        }


