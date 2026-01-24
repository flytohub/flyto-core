"""
Format Duration Module
Format seconds as human-readable duration
"""
from typing import Any, Dict

from ...registry import register_module
from ...errors import ValidationError


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
    can_connect_to=['string.*', 'data.*', 'flow.*', 'notification.*'],

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
    total_seconds = abs(total_seconds)

    days = int(total_seconds // 86400)
    remaining = total_seconds % 86400
    hours = int(remaining // 3600)
    remaining = remaining % 3600
    minutes = int(remaining // 60)
    secs = int(remaining % 60)

    parts = {
        'days': days,
        'hours': hours,
        'minutes': minutes,
        'seconds': secs
    }

    if fmt == 'clock':
        if days > 0:
            result = f"{days}:{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            result = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    elif fmt == 'compact':
        if days > 0:
            result = f"{days}:{hours}:{minutes:02d}:{secs:02d}"
        elif hours > 0:
            result = f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            result = f"{minutes}:{secs:02d}"
    elif fmt == 'long':
        parts_str = []
        if days > 0 or show_zero:
            parts_str.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0 or show_zero:
            parts_str.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0 or show_zero:
            parts_str.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if secs > 0 or show_zero or not parts_str:
            parts_str.append(f"{secs} second{'s' if secs != 1 else ''}")
        result = ' '.join(parts_str)
    else:
        parts_str = []
        if days > 0:
            parts_str.append(f"{days}d")
        if hours > 0 or (days > 0 and show_zero):
            parts_str.append(f"{hours}h")
        if minutes > 0 or ((days > 0 or hours > 0) and show_zero):
            parts_str.append(f"{minutes}m")
        if secs > 0 or show_zero or not parts_str:
            parts_str.append(f"{secs}s")
        result = ' '.join(parts_str)

    if is_negative:
        result = f"-{result}"

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': seconds,
            'parts': parts
        }
    }
