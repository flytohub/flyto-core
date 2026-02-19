# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Scheduler Cron Parse Module
Parse cron expression and calculate next N run times.

Implements a stdlib-only cron parser supporting standard 5-field expressions:
  minute hour day_of_month month day_of_week

Supports: *, specific values, ranges (1-5), steps (*/5), lists (1,3,5),
and named values (MON-SUN, JAN-DEC).
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)

# Named day-of-week mappings (0=Sunday in cron, but we normalize to 0=Monday internally
# then convert back for matching against datetime.weekday())
DAY_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3,
    'THU': 4, 'FRI': 5, 'SAT': 6,
}

MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
    'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8,
    'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

# Ranges for each cron field
FIELD_RANGES = [
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day of month
    (1, 12),   # month
    (0, 6),    # day of week (0=Sunday)
]

FIELD_NAMES = ['minute', 'hour', 'day_of_month', 'month', 'day_of_week']


def _replace_names(value: str, field_index: int) -> str:
    """Replace named values (MON, JAN, etc.) with their numeric equivalents."""
    upper = value.upper()
    if field_index == 4:  # day_of_week
        for name, num in DAY_NAMES.items():
            upper = upper.replace(name, str(num))
    elif field_index == 3:  # month
        for name, num in MONTH_NAMES.items():
            upper = upper.replace(name, str(num))
    return upper


def _parse_field(value: str, field_index: int) -> Set[int]:
    """
    Parse a single cron field into a set of valid integer values.

    Supports: *, ranges (1-5), steps (*/5, 1-10/2), lists (1,3,5)
    """
    value = _replace_names(value, field_index)
    lo, hi = FIELD_RANGES[field_index]
    result = set()

    for part in value.split(','):
        part = part.strip()
        if not part:
            continue

        # Handle step: */5 or 1-10/2
        step = 1
        if '/' in part:
            range_part, step_str = part.split('/', 1)
            try:
                step = int(step_str)
            except ValueError:
                raise ValidationError(
                    "Invalid step value '{}' in cron field '{}'".format(step_str, FIELD_NAMES[field_index]),
                    field='expression'
                )
            part = range_part

        if part == '*':
            result.update(range(lo, hi + 1, step))
        elif '-' in part:
            # Range: 1-5
            range_parts = part.split('-', 1)
            try:
                start = int(range_parts[0])
                end = int(range_parts[1])
            except ValueError:
                raise ValidationError(
                    "Invalid range '{}' in cron field '{}'".format(part, FIELD_NAMES[field_index]),
                    field='expression'
                )
            if start < lo or end > hi:
                raise ValidationError(
                    "Range {}-{} out of bounds ({}-{}) for field '{}'".format(
                        start, end, lo, hi, FIELD_NAMES[field_index]
                    ),
                    field='expression'
                )
            result.update(range(start, end + 1, step))
        else:
            # Single value
            try:
                val = int(part)
            except ValueError:
                raise ValidationError(
                    "Invalid value '{}' in cron field '{}'".format(part, FIELD_NAMES[field_index]),
                    field='expression'
                )
            if val < lo or val > hi:
                raise ValidationError(
                    "Value {} out of bounds ({}-{}) for field '{}'".format(
                        val, lo, hi, FIELD_NAMES[field_index]
                    ),
                    field='expression'
                )
            result.add(val)

    if not result:
        raise ValidationError(
            "Empty result for cron field '{}'".format(FIELD_NAMES[field_index]),
            field='expression'
        )

    return result


def _parse_expression(expression: str) -> Tuple[Set[int], Set[int], Set[int], Set[int], Set[int]]:
    """Parse a full 5-field cron expression into sets of valid values."""
    parts = expression.strip().split()
    if len(parts) != 5:
        raise ValidationError(
            "Cron expression must have exactly 5 fields (minute hour day_of_month month day_of_week), got {}".format(
                len(parts)
            ),
            field='expression'
        )

    minutes = _parse_field(parts[0], 0)
    hours = _parse_field(parts[1], 1)
    days = _parse_field(parts[2], 2)
    months = _parse_field(parts[3], 3)
    weekdays = _parse_field(parts[4], 4)

    return minutes, hours, days, months, weekdays


def _datetime_weekday_to_cron(weekday: int) -> int:
    """Convert Python datetime.weekday() (0=Monday) to cron day_of_week (0=Sunday)."""
    return (weekday + 1) % 7


def _calculate_next_runs(expression: str, count: int, tz_offset_hours: int = 0) -> List[str]:
    """Calculate the next N run times for a cron expression."""
    minutes, hours, days, months, weekdays = _parse_expression(expression)

    tz = timezone(timedelta(hours=tz_offset_hours))
    now = datetime.now(tz)
    # Start from the next minute
    current = now.replace(second=0, microsecond=0) + timedelta(minutes=1)

    results = []
    # Safety limit to prevent infinite loops
    max_iterations = 525600  # one year of minutes

    iterations = 0
    while len(results) < count and iterations < max_iterations:
        iterations += 1

        if (current.month in months and
                current.day in days and
                _datetime_weekday_to_cron(current.weekday()) in weekdays and
                current.hour in hours and
                current.minute in minutes):
            results.append(current.isoformat())
            current += timedelta(minutes=1)
            continue

        # Fast-forward: skip to next valid month if current month is invalid
        if current.month not in months:
            # Jump to next valid month
            found = False
            for m in sorted(months):
                if m > current.month:
                    current = current.replace(month=m, day=1, hour=0, minute=0)
                    found = True
                    break
            if not found:
                # Wrap to next year
                next_month = min(months)
                current = current.replace(year=current.year + 1, month=next_month, day=1, hour=0, minute=0)
            continue

        # Fast-forward: skip to next valid hour if current hour is invalid
        if current.hour not in hours:
            found = False
            for h in sorted(hours):
                if h > current.hour:
                    current = current.replace(hour=h, minute=min(minutes))
                    found = True
                    break
            if not found:
                # Next day
                current = (current + timedelta(days=1)).replace(hour=min(hours), minute=min(minutes))
            continue

        # Fast-forward: skip to next valid minute if current minute is invalid
        if current.minute not in minutes:
            found = False
            for mi in sorted(minutes):
                if mi > current.minute:
                    current = current.replace(minute=mi)
                    found = True
                    break
            if not found:
                # Next valid hour
                found_h = False
                for h in sorted(hours):
                    if h > current.hour:
                        current = current.replace(hour=h, minute=min(minutes))
                        found_h = True
                        break
                if not found_h:
                    current = (current + timedelta(days=1)).replace(hour=min(hours), minute=min(minutes))
            continue

        # Day or weekday mismatch — advance one day
        current = (current + timedelta(days=1)).replace(hour=min(hours), minute=min(minutes))

    return results


def _describe_expression(expression: str) -> str:
    """Generate a human-readable description of a cron expression."""
    parts = expression.strip().split()
    if len(parts) != 5:
        return expression

    minute, hour, dom, month, dow = parts

    # Common patterns
    if expression.strip() == '* * * * *':
        return 'Every minute'
    if minute == '0' and hour == '*' and dom == '*' and month == '*' and dow == '*':
        return 'Every hour at minute 0'
    if minute == '0' and hour == '0' and dom == '*' and month == '*' and dow == '*':
        return 'Every day at midnight'

    desc_parts = []

    # Time description
    if minute != '*' and hour != '*':
        # Specific time
        try:
            m_val = minute
            h_val = int(hour)
            period = 'AM' if h_val < 12 else 'PM'
            display_hour = h_val % 12
            if display_hour == 0:
                display_hour = 12
            desc_parts.append('At {}:{:0>2} {}'.format(display_hour, m_val, period))
        except (ValueError, TypeError):
            desc_parts.append('At {}:{}'.format(hour, minute))
    elif minute != '*' and hour == '*':
        desc_parts.append('At minute {} of every hour'.format(minute))
    elif minute == '*' and hour != '*':
        desc_parts.append('Every minute during hour {}'.format(hour))

    # Day of week
    dow_upper = dow.upper()
    day_map = {
        '1': 'Monday', '2': 'Tuesday', '3': 'Wednesday',
        '4': 'Thursday', '5': 'Friday', '6': 'Saturday', '0': 'Sunday',
        'MON': 'Monday', 'TUE': 'Tuesday', 'WED': 'Wednesday',
        'THU': 'Thursday', 'FRI': 'Friday', 'SAT': 'Saturday', 'SUN': 'Sunday',
    }
    if dow_upper == '1-5' or dow_upper == 'MON-FRI':
        desc_parts.append('on weekdays')
    elif dow_upper == '0,6' or dow_upper == 'SAT,SUN':
        desc_parts.append('on weekends')
    elif dow != '*':
        if dow in day_map:
            desc_parts.append('on {}'.format(day_map[dow]))
        elif dow_upper in day_map:
            desc_parts.append('on {}'.format(day_map[dow_upper]))
        else:
            desc_parts.append('on day_of_week {}'.format(dow))

    # Day of month
    if dom != '*':
        desc_parts.append('on day {} of the month'.format(dom))

    # Month
    month_map = {
        '1': 'January', '2': 'February', '3': 'March', '4': 'April',
        '5': 'May', '6': 'June', '7': 'July', '8': 'August',
        '9': 'September', '10': 'October', '11': 'November', '12': 'December',
    }
    if month != '*':
        if month in month_map:
            desc_parts.append('in {}'.format(month_map[month]))
        else:
            desc_parts.append('in month {}'.format(month))

    # Handle step patterns
    if '/' in minute and hour == '*':
        step = minute.split('/')[1]
        return 'Every {} minutes'.format(step)
    if '/' in hour:
        step = hour.split('/')[1]
        return 'Every {} hours'.format(step)

    if not desc_parts:
        return expression

    return ' '.join(desc_parts)


@register_module(
    module_id='scheduler.cron_parse',
    version='1.0.0',
    category='scheduler',
    tags=['scheduler', 'cron', 'parse', 'schedule', 'timing'],
    label='Parse Cron Expression',
    label_key='modules.scheduler.cron_parse.label',
    description='Parse cron expression and calculate next N run times',
    description_key='modules.scheduler.cron_parse.description',
    icon='Clock',
    color='#7C3AED',
    input_types=['string'],
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
            'expression',
            type='string',
            label='Cron Expression',
            label_key='modules.scheduler.cron_parse.params.expression.label',
            description='Standard 5-field cron expression (e.g. "0 9 * * MON-FRI")',
            description_key='modules.scheduler.cron_parse.params.expression.description',
            placeholder='0 9 * * MON-FRI',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'count',
            type='number',
            label='Number of Runs',
            label_key='modules.scheduler.cron_parse.params.count.label',
            description='Number of next run times to calculate',
            description_key='modules.scheduler.cron_parse.params.count.description',
            default=5,
            min=1,
            max=100,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'timezone',
            type='string',
            label='Timezone',
            label_key='modules.scheduler.cron_parse.params.timezone.label',
            description='Timezone for calculation (UTC offset like "+8" or "-5", default "0" for UTC)',
            description_key='modules.scheduler.cron_parse.params.timezone.description',
            default='0',
            placeholder='0',
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'expression': {
            'type': 'string',
            'description': 'The parsed cron expression',
            'description_key': 'modules.scheduler.cron_parse.output.expression.description',
        },
        'description': {
            'type': 'string',
            'description': 'Human-readable description of the schedule',
            'description_key': 'modules.scheduler.cron_parse.output.description.description',
        },
        'next_runs': {
            'type': 'array',
            'description': 'List of next run times as ISO datetime strings',
            'description_key': 'modules.scheduler.cron_parse.output.next_runs.description',
        },
        'is_valid': {
            'type': 'boolean',
            'description': 'Whether the expression is valid',
            'description_key': 'modules.scheduler.cron_parse.output.is_valid.description',
        },
    },
    timeout_ms=10000,
)
async def scheduler_cron_parse(context: Dict[str, Any]) -> Dict[str, Any]:
    """Parse cron expression and calculate next N run times."""
    params = context['params']
    expression = params.get('expression')

    if not expression:
        raise ValidationError("Missing required parameter: expression", field="expression")

    count = int(params.get('count', 5))
    tz_str = str(params.get('timezone', '0'))

    # Parse timezone offset
    try:
        tz_offset = int(tz_str.replace('+', ''))
    except ValueError:
        raise ValidationError(
            "Invalid timezone offset '{}'. Use a number like 0, +8, or -5".format(tz_str),
            field='timezone'
        )

    # Parse and validate expression
    try:
        description = _describe_expression(expression)
        next_runs = _calculate_next_runs(expression, count, tz_offset)
        is_valid = True
    except ValidationError:
        raise
    except Exception as e:
        logger.warning("Failed to parse cron expression '{}': {}".format(expression, e))
        raise ModuleError("Failed to parse cron expression: {}".format(str(e)))

    return {
        'ok': True,
        'data': {
            'expression': expression,
            'description': description,
            'next_runs': next_runs,
            'is_valid': is_valid,
        }
    }
