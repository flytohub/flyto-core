# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Scheduler Interval Module
Calculate interval timing and next occurrences.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


def _human_readable_interval(total_seconds: int) -> str:
    """Convert total seconds into a human-readable interval string."""
    if total_seconds <= 0:
        return '0 seconds'

    parts = []
    days = total_seconds // 86400
    remaining = total_seconds % 86400
    hours = remaining // 3600
    remaining = remaining % 3600
    minutes = remaining // 60
    secs = remaining % 60

    if days > 0:
        parts.append('{} day{}'.format(days, 's' if days != 1 else ''))
    if hours > 0:
        parts.append('{} hour{}'.format(hours, 's' if hours != 1 else ''))
    if minutes > 0:
        parts.append('{} minute{}'.format(minutes, 's' if minutes != 1 else ''))
    if secs > 0:
        parts.append('{} second{}'.format(secs, 's' if secs != 1 else ''))

    return 'every ' + ' '.join(parts)


@register_module(
    module_id='scheduler.interval',
    version='1.0.0',
    category='scheduler',
    tags=['scheduler', 'interval', 'timing', 'recurring', 'periodic'],
    label='Calculate Interval',
    label_key='modules.scheduler.interval.label',
    description='Calculate interval timing and next occurrences',
    description_key='modules.scheduler.interval.description',
    icon='Clock',
    color='#7C3AED',
    input_types=['number'],
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
            label='Seconds',
            label_key='modules.scheduler.interval.params.seconds.label',
            description='Interval seconds component',
            description_key='modules.scheduler.interval.params.seconds.description',
            default=0,
            min=0,
            group=FieldGroup.BASIC,
        ),
        field(
            'minutes',
            type='number',
            label='Minutes',
            label_key='modules.scheduler.interval.params.minutes.label',
            description='Interval minutes component',
            description_key='modules.scheduler.interval.params.minutes.description',
            default=0,
            min=0,
            group=FieldGroup.BASIC,
        ),
        field(
            'hours',
            type='number',
            label='Hours',
            label_key='modules.scheduler.interval.params.hours.label',
            description='Interval hours component',
            description_key='modules.scheduler.interval.params.hours.description',
            default=0,
            min=0,
            group=FieldGroup.BASIC,
        ),
        field(
            'start_time',
            type='string',
            label='Start Time',
            label_key='modules.scheduler.interval.params.start_time.label',
            description='Start time in ISO 8601 format (default: now)',
            description_key='modules.scheduler.interval.params.start_time.description',
            placeholder='2024-01-15T10:00:00Z',
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'interval_seconds': {
            'type': 'number',
            'description': 'Total interval in seconds',
            'description_key': 'modules.scheduler.interval.output.interval_seconds.description',
        },
        'next_runs': {
            'type': 'array',
            'description': 'List of next 5 run times as ISO datetime strings',
            'description_key': 'modules.scheduler.interval.output.next_runs.description',
        },
        'human_readable': {
            'type': 'string',
            'description': 'Human-readable interval description',
            'description_key': 'modules.scheduler.interval.output.human_readable.description',
        },
    },
    timeout_ms=5000,
)
async def scheduler_interval(context: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate interval timing and next occurrences."""
    params = context['params']

    seconds = int(params.get('seconds', 0) or 0)
    minutes = int(params.get('minutes', 0) or 0)
    hours = int(params.get('hours', 0) or 0)
    start_time_str = params.get('start_time')

    total_seconds = seconds + (minutes * 60) + (hours * 3600)

    if total_seconds <= 0:
        raise ValidationError(
            "At least one duration parameter (seconds, minutes, hours) must be greater than 0",
            field='seconds',
            hint='Provide at least one of: seconds, minutes, or hours with a value > 0'
        )

    # Determine start time
    if start_time_str:
        try:
            start = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            raise ValidationError(
                "Invalid start_time format: '{}'. Expected ISO 8601 format".format(start_time_str),
                field='start_time'
            )
    else:
        start = datetime.now(timezone.utc)

    # Calculate next 5 occurrences
    interval = timedelta(seconds=total_seconds)
    next_runs = []
    current = start
    for _ in range(5):
        current = current + interval
        next_runs.append(current.isoformat())

    human_readable = _human_readable_interval(total_seconds)

    return {
        'ok': True,
        'data': {
            'interval_seconds': total_seconds,
            'next_runs': next_runs,
            'human_readable': human_readable,
        }
    }
