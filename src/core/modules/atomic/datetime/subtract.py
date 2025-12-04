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
            'label_key': 'modules.datetime.subtract.params.datetime.label',
            'description': 'DateTime to modify (ISO format or "now")',
            'description_key': 'modules.datetime.subtract.params.datetime.description',
            'default': 'now',
            'required': False
        },
        'days': {
            'type': 'number',
            'label': 'Days',
            'label_key': 'modules.datetime.subtract.params.days.label',
            'description': 'Days to subtract',
            'description_key': 'modules.datetime.subtract.params.days.description',
            'default': 0,
            'required': False
        },
        'hours': {
            'type': 'number',
            'label': 'Hours',
            'label_key': 'modules.datetime.subtract.params.hours.label',
            'description': 'Hours to subtract',
            'description_key': 'modules.datetime.subtract.params.hours.description',
            'default': 0,
            'required': False
        },
        'minutes': {
            'type': 'number',
            'label': 'Minutes',
            'label_key': 'modules.datetime.subtract.params.minutes.label',
            'description': 'Minutes to subtract',
            'description_key': 'modules.datetime.subtract.params.minutes.description',
            'default': 0,
            'required': False
        },
        'seconds': {
            'type': 'number',
            'label': 'Seconds',
            'label_key': 'modules.datetime.subtract.params.seconds.label',
            'description': 'Seconds to subtract',
            'description_key': 'modules.datetime.subtract.params.seconds.description',
            'default': 0,
            'required': False
        }
    },
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
            except:
                raise ValueError(f"Invalid datetime format: {self.datetime_str}")

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
