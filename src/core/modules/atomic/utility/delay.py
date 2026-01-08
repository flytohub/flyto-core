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
    module_id='utility.delay',
    version='1.0.0',
    category='utility',
    tags=['utility', 'delay', 'sleep', 'wait', 'timing'],
    label='Delay/Sleep',
    label_key='modules.utility.delay.label',
    description='Pause workflow execution for specified duration',
    description_key='modules.utility.delay.description',
    icon='Clock',
    color='#6B7280',

    # Connection types - pure utility, no data transformation
    input_types=[],
    output_types=[],


    can_receive_from=['start', 'flow.*'],
    can_connect_to=['data.*', 'string.*', 'file.*', 'api.*', 'notification.*', 'flow.*', 'utility.*'],    # Phase 2: Execution settings
    retryable=False,  # Delay operations are deterministic
    concurrent_safe=True,  # Multiple delays can run in parallel

    # Phase 2: Security settings
    requires_credentials=False,  # No credentials needed
    handles_sensitive_data=False,  # No sensitive data handled
    required_permissions=[],  # No special permissions needed

    params_schema={
        'duration_ms': {
            'type': 'number',
            'label': 'Duration (milliseconds)',
            'label_key': 'modules.utility.delay.params.duration_ms.label',
            'description': 'How long to wait in milliseconds',
            'description_key': 'modules.utility.delay.params.duration_ms.description',
            'placeholder': 1000,
            'default': 1000,
            'min': 0,
            'max': 3600000,  # Max 1 hour
            'required': False
        },
        'duration_seconds': {
            'type': 'number',
            'label': 'Duration (seconds)',
            'label_key': 'modules.utility.delay.params.duration_seconds.label',
            'description': 'Alternative: duration in seconds',
            'description_key': 'modules.utility.delay.params.duration_seconds.description',
            'placeholder': 1,
            'min': 0,
            'max': 3600,
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.utility.delay.output.status.description'},
        'waited_ms': {'type': 'number', 'description': 'Actual wait time in ms',
                'description_key': 'modules.utility.delay.output.waited_ms.description'}
    },
    examples=[
        {
            'name': 'Wait 2 seconds',
            'params': {
                'duration_seconds': 2
            }
        },
        {
            'name': 'Wait 500ms',
            'params': {
                'duration_ms': 500
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=5000,
)
class DelayModule(BaseModule):
    """Pause workflow execution"""

    module_name = "Delay/Sleep"
    module_description = "Pause workflow execution for specified duration"

    def validate_params(self) -> None:
        # Support both milliseconds and seconds
        self.duration_ms = self.params.get('duration_ms')
        self.duration_seconds = self.params.get('duration_seconds')

        if self.duration_ms is None and self.duration_seconds is None:
            self.duration_ms = 1000  # Default 1 second

        if self.duration_seconds is not None:
            self.duration_ms = self.duration_seconds * 1000

    async def execute(self) -> Any:
        await asyncio.sleep(self.duration_ms / 1000)

        return {
            'status': 'success',
            'waited_ms': self.duration_ms
        }


