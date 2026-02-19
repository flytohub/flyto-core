# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Scheduler Delay Module
Async delay/sleep for workflow timing control.
"""
import asyncio
import logging
import time
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


@register_module(
    module_id='scheduler.delay',
    version='1.0.0',
    category='scheduler',
    tags=['scheduler', 'delay', 'sleep', 'wait', 'pause'],
    label='Delay / Sleep',
    label_key='modules.scheduler.delay.label',
    description='Pause execution for a specified duration',
    description_key='modules.scheduler.delay.description',
    icon='Clock',
    color='#7C3AED',
    input_types=['any'],
    output_types=['json'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'seconds',
            type='number',
            label='Delay Seconds',
            label_key='modules.scheduler.delay.params.seconds.label',
            description='Number of seconds to delay',
            description_key='modules.scheduler.delay.params.seconds.description',
            required=True,
            min=0,
            max=3600,
            group=FieldGroup.BASIC,
        ),
        field(
            'message',
            type='string',
            label='Message',
            label_key='modules.scheduler.delay.params.message.label',
            description='Optional message to include in the result',
            description_key='modules.scheduler.delay.params.message.description',
            placeholder='Waiting for rate limit...',
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'delayed_seconds': {
            'type': 'number',
            'description': 'Actual number of seconds delayed',
            'description_key': 'modules.scheduler.delay.output.delayed_seconds.description',
        },
        'message': {
            'type': 'string',
            'description': 'The provided message or default',
            'description_key': 'modules.scheduler.delay.output.message.description',
        },
    },
    timeout_ms=3660000,  # slightly more than max delay (1 hour + 1 minute)
)
async def scheduler_delay(context: Dict[str, Any]) -> Dict[str, Any]:
    """Pause execution for a specified duration."""
    params = context['params']
    seconds = params.get('seconds')

    if seconds is None:
        raise ValidationError("Missing required parameter: seconds", field="seconds")

    seconds = float(seconds)
    if seconds < 0:
        raise ValidationError("Delay seconds must be >= 0", field="seconds")
    if seconds > 3600:
        raise ValidationError(
            "Delay seconds must be <= 3600 (1 hour)",
            field="seconds",
            hint="For longer delays, consider using a scheduler or cron job"
        )

    message = params.get('message', 'Delay completed')

    start = time.monotonic()
    await asyncio.sleep(seconds)
    actual_delay = round(time.monotonic() - start, 3)

    return {
        'ok': True,
        'data': {
            'delayed_seconds': actual_delay,
            'message': message,
        }
    }
