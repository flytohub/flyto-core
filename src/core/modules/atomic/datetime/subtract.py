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
    module_id='datetime.subtract',
    version='1.0.0',
    category='utility',
    subcategory='datetime',
    tags=['datetime', 'subtract', 'date', 'time'],
    label='Subtract Time',
    label_key='modules.datetime.subtract.label',
    description='Subtract time from datetime',
    description_key='modules.datetime.subtract.description',
    icon='Minus',
    color='#8B5CF6',

    # Connection types
    input_types=['datetime', 'string'],
    output_types=['datetime', 'string'],


    can_receive_from=['*'],
    can_connect_to=['data.*', 'string.*', 'file.*', 'api.*', 'notification.*', 'flow.*', 'utility.*'],    # Phase 2: Execution settings
    timeout=None,
    retryable=False,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.DATETIME_INPUT(default='now'),
        presets.TIME_DAYS(default=0),
        presets.TIME_HOURS(default=0),
        presets.TIME_MINUTES(default=0),
        presets.TIME_SECONDS(default=0),
    ),
    output_schema={
        'result': {'type': 'string'},
        'timestamp': {'type': 'number'}
    },
    examples=[
        {
            'title': 'Subtract 7 days',
            'params': {
                'datetime': 'now',
                'days': 7
            }
        },
        {
            'title': 'Subtract 1 hour',
            'params': {
                'datetime': '2024-01-15T10:00:00',
                'hours': 1
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class DateTimeSubtractModule(BaseModule):
    """DateTime Subtract Module"""

    def validate_params(self):
        self.datetime_str = self.params.get('datetime', 'now')
        self.days = self.params.get('days', 0)
        self.hours = self.params.get('hours', 0)
        self.minutes = self.params.get('minutes', 0)
        self.seconds = self.params.get('seconds', 0)

    async def execute(self) -> Any:
        # Parse datetime
        if self.datetime_str == 'now':
            dt = datetime.now()
        else:
            try:
                dt = datetime.fromisoformat(self.datetime_str.replace('Z', '+00:00'))
            except (ValueError, AttributeError) as e:
                raise ValueError(
                    f"Invalid datetime format: '{self.datetime_str}'. "
                    f"Expected ISO 8601 format (e.g., '2024-01-15T10:30:00Z'). "
                    f"Error: {e}"
                )

        # Subtract time
        delta = timedelta(
            days=self.days,
            hours=self.hours,
            minutes=self.minutes,
            seconds=self.seconds
        )
        result_dt = dt - delta

        return {
            "result": result_dt.isoformat(),
            "timestamp": result_dt.timestamp()
        }
