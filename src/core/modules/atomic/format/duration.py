# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Format Duration Module
Format seconds as human-readable duration
"""
from typing import Any, Dict

from ...registry import register_module
from ...errors import ValidationError


def _decompose_seconds(total_seconds: float) -> Dict[str, int]:
    """Break total seconds into days, hours, minutes, seconds."""
    days = int(total_seconds // 86400)
    remaining = total_seconds % 86400
    hours = int(remaining // 3600)
    remaining = remaining % 3600
    minutes = int(remaining // 60)
    secs = int(remaining % 60)
    return {'days': days, 'hours': hours, 'minutes': minutes, 'seconds': secs}


def _format_clock(p: Dict[str, int]) -> str:
    """Format parts as clock style (01:02:03)."""
    if p['days'] > 0:
        return f"{p['days']}:{p['hours']:02d}:{p['minutes']:02d}:{p['seconds']:02d}"
    return f"{p['hours']:02d}:{p['minutes']:02d}:{p['seconds']:02d}"


def _format_compact(p: Dict[str, int]) -> str:
    """Format parts as compact style (1:02:03)."""
    if p['days'] > 0:
        return f"{p['days']}:{p['hours']}:{p['minutes']:02d}:{p['seconds']:02d}"
    if p['hours'] > 0:
        return f"{p['hours']}:{p['minutes']:02d}:{p['seconds']:02d}"
    return f"{p['minutes']}:{p['seconds']:02d}"


def _format_long(p: Dict[str, int], show_zero: bool) -> str:
    """Format parts as long style (1 hour 2 minutes 3 seconds)."""
    parts_str = []
    if p['days'] > 0 or show_zero:
        parts_str.append(f"{p['days']} day{'s' if p['days'] != 1 else ''}")
    if p['hours'] > 0 or show_zero:
        parts_str.append(f"{p['hours']} hour{'s' if p['hours'] != 1 else ''}")
    if p['minutes'] > 0 or show_zero:
        parts_str.append(f"{p['minutes']} minute{'s' if p['minutes'] != 1 else ''}")
    if p['seconds'] > 0 or show_zero or not parts_str:
        parts_str.append(f"{p['seconds']} second{'s' if p['seconds'] != 1 else ''}")
    return ' '.join(parts_str)


def _format_short(p: Dict[str, int], show_zero: bool) -> str:
    """Format parts as short style (1h 2m 3s)."""
    parts_str = []
    if p['days'] > 0:
        parts_str.append(f"{p['days']}d")
    if p['hours'] > 0 or (p['days'] > 0 and show_zero):
        parts_str.append(f"{p['hours']}h")
    if p['minutes'] > 0 or ((p['days'] > 0 or p['hours'] > 0) and show_zero):
        parts_str.append(f"{p['minutes']}m")
    if p['seconds'] > 0 or show_zero or not parts_str:
        parts_str.append(f"{p['seconds']}s")
    return ' '.join(parts_str)


@register_module(
    module_id='format.duration',
    version='1.0.0',
    category='format',
    tags=['format', 'duration', 'time', 'seconds'],
    label='Format Duration',
    label_key='modules.format.duration.label',
    description='Format seconds as human-readable duration',
    description_key='modules.format.duration.description',
    icon='Clock',
    color='#EC4899',
    input_types=['number'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['string.*', 'data.*', 'flow.*', 'notify.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'seconds': {
            'type': 'number',
            'label': 'Seconds',
            'label_key': 'modules.format.duration.params.seconds.label',
            'description': 'Duration in seconds',
            'description_key': 'modules.format.duration.params.seconds.description',
            'placeholder': '3661',
            'required': True
        },
        'format': {
            'type': 'string',
            'label': 'Format',
            'label_key': 'modules.format.duration.params.format.label',
            'description': 'Output format style',
            'description_key': 'modules.format.duration.params.format.description',
            'default': 'short',
            'required': False,
            'options': [
                {'value': 'short', 'label': 'Short (1h 2m 3s)'},
                {'value': 'long', 'label': 'Long (1 hour 2 minutes 3 seconds)'},
                {'value': 'clock', 'label': 'Clock (01:02:03)'},
                {'value': 'compact', 'label': 'Compact (1:02:03)'}
            ]
        },
        'show_zero': {
            'type': 'boolean',
            'label': 'Show Zero Units',
            'label_key': 'modules.format.duration.params.show_zero.label',
            'description': 'Show units that are zero',
            'description_key': 'modules.format.duration.params.show_zero.description',
            'default': False,
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Formatted duration string',
            'description_key': 'modules.format.duration.output.result.description'
        },
        'original': {
            'type': 'number',
            'description': 'Original seconds',
            'description_key': 'modules.format.duration.output.original.description'
        },
        'parts': {
            'type': 'object',
            'description': 'Duration parts (days, hours, minutes, seconds)',
            'description_key': 'modules.format.duration.output.parts.description'
        }
    },
    timeout_ms=5000,
)
async def format_duration(context: Dict[str, Any]) -> Dict[str, Any]:
    """Format seconds as human-readable duration."""
    params = context['params']
    seconds = params.get('seconds')
    fmt = params.get('format', 'short')
    show_zero = params.get('show_zero', False)

    if seconds is None:
        raise ValidationError("Missing required parameter: seconds", field="seconds")
    try:
        total_seconds = float(seconds)
    except (ValueError, TypeError):
        raise ValidationError("Invalid seconds value", field="seconds")

    is_negative = total_seconds < 0
    parts = _decompose_seconds(abs(total_seconds))

    formatters = {
        'clock': lambda: _format_clock(parts),
        'compact': lambda: _format_compact(parts),
        'long': lambda: _format_long(parts, show_zero),
    }
    result = formatters.get(fmt, lambda: _format_short(parts, show_zero))()

    if is_negative:
        result = f"-{result}"

    return {
        'ok': True,
        'data': {'result': result, 'original': seconds, 'parts': parts}
    }
