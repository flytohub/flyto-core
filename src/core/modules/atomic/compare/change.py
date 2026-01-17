"""
Compare Change Module
Detect if values have changed beyond a threshold.
Perfect for price alerts, monitoring, and change detection workflows.
"""
import logging
from typing import Any, Dict, Optional, Union

from ...registry import register_module

logger = logging.getLogger(__name__)


@register_module(
    module_id='compare.change',
    stability='stable',
    version='1.0.0',
    category='compare',
    subcategory='change',
    tags=['compare', 'change', 'threshold', 'alert', 'monitor', 'price'],
    label='Detect Change',
    label_key='modules.compare.change.label',
    description='Detect if a value has changed beyond threshold (by amount or percentage)',
    description_key='modules.compare.change.description',
    icon='ArrowUpDown',
    color='#F59E0B',

    input_types=['number', 'object', 'text'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=1000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'current_value': {
            'type': 'number',
            'label': 'Current Value',
            'label_key': 'modules.compare.change.params.current.label',
            'description': 'The current/new value to compare',
            'description_key': 'modules.compare.change.params.current.description',
            'required': True,
            'placeholder': '42350.50'
        },
        'previous_value': {
            'type': 'number',
            'label': 'Previous Value',
            'label_key': 'modules.compare.change.params.previous.label',
            'description': 'The previous/old value to compare against',
            'description_key': 'modules.compare.change.params.previous.description',
            'required': True,
            'placeholder': '41000.00'
        },
        'mode': {
            'type': 'select',
            'label': 'Detection Mode',
            'label_key': 'modules.compare.change.params.mode.label',
            'description': 'How to measure change',
            'description_key': 'modules.compare.change.params.mode.description',
            'required': False,
            'default': 'percent',
            'options': [
                {'value': 'percent', 'label': 'Percentage Change'},
                {'value': 'absolute', 'label': 'Absolute Change'},
                {'value': 'any', 'label': 'Any Change'}
            ]
        },
        'threshold': {
            'type': 'number',
            'label': 'Threshold',
            'label_key': 'modules.compare.change.params.threshold.label',
            'description': 'Minimum change to trigger (5 = 5% or 5 units)',
            'description_key': 'modules.compare.change.params.threshold.description',
            'required': False,
            'default': 5,
            'min': 0,
            'placeholder': '5'
        },
        'direction': {
            'type': 'select',
            'label': 'Direction',
            'label_key': 'modules.compare.change.params.direction.label',
            'description': 'Which direction of change to detect',
            'description_key': 'modules.compare.change.params.direction.description',
            'required': False,
            'default': 'both',
            'options': [
                {'value': 'both', 'label': 'Both (Up or Down)'},
                {'value': 'up', 'label': 'Up Only (Increase)'},
                {'value': 'down', 'label': 'Down Only (Decrease)'}
            ]
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether the operation succeeded',
            'description_key': 'modules.compare.change.output.ok.description'
        },
        'changed': {
            'type': 'boolean',
            'description': 'Whether value changed beyond threshold',
            'description_key': 'modules.compare.change.output.changed.description'
        },
        'direction': {
            'type': 'string',
            'description': 'Direction of change: "up", "down", or "none"',
            'description_key': 'modules.compare.change.output.direction.description'
        },
        'change_percent': {
            'type': 'number',
            'description': 'Percentage change (positive = up, negative = down)',
            'description_key': 'modules.compare.change.output.change_percent.description'
        },
        'change_absolute': {
            'type': 'number',
            'description': 'Absolute change (positive = up, negative = down)',
            'description_key': 'modules.compare.change.output.change_absolute.description'
        },
        'current_value': {
            'type': 'number',
            'description': 'The current value',
            'description_key': 'modules.compare.change.output.current.description'
        },
        'previous_value': {
            'type': 'number',
            'description': 'The previous value',
            'description_key': 'modules.compare.change.output.previous.description'
        },
        'summary': {
            'type': 'string',
            'description': 'Human-readable summary (e.g., "+3.5%")',
            'description_key': 'modules.compare.change.output.summary.description'
        }
    },
    examples=[
        {
            'title': 'Crypto price alert (5% change)',
            'title_key': 'modules.compare.change.examples.crypto.title',
            'params': {
                'current_value': 44500,
                'previous_value': 42000,
                'mode': 'percent',
                'threshold': 5,
                'direction': 'both'
            }
        },
        {
            'title': 'Stock drop alert',
            'title_key': 'modules.compare.change.examples.stock.title',
            'params': {
                'current_value': 145.50,
                'previous_value': 152.30,
                'mode': 'percent',
                'threshold': 3,
                'direction': 'down'
            }
        },
        {
            'title': 'Temperature change (absolute)',
            'title_key': 'modules.compare.change.examples.temp.title',
            'params': {
                'current_value': 32,
                'previous_value': 25,
                'mode': 'absolute',
                'threshold': 5,
                'direction': 'up'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def compare_change(context: Dict[str, Any]) -> Dict[str, Any]:
    """Detect if value changed beyond threshold"""
    params = context['params']

    try:
        current = float(params['current_value'])
        previous = float(params['previous_value'])
    except (TypeError, ValueError) as e:
        return {
            'ok': False,
            'error': f"Invalid numeric values: {e}",
            'error_code': 'INVALID_NUMBER'
        }

    mode = params.get('mode', 'percent')
    threshold = float(params.get('threshold', 5))
    direction_filter = params.get('direction', 'both')

    # Calculate changes
    change_absolute = current - previous

    if previous == 0:
        # Avoid division by zero
        change_percent = 100.0 if current != 0 else 0.0
    else:
        change_percent = (change_absolute / abs(previous)) * 100

    # Determine direction
    if change_absolute > 0:
        direction = 'up'
    elif change_absolute < 0:
        direction = 'down'
    else:
        direction = 'none'

    # Check if change exceeds threshold
    if mode == 'percent':
        change_magnitude = abs(change_percent)
    elif mode == 'absolute':
        change_magnitude = abs(change_absolute)
    else:  # 'any'
        change_magnitude = abs(change_absolute)
        threshold = 0.0001  # Tiny threshold for "any change"

    exceeds_threshold = change_magnitude >= threshold

    # Apply direction filter
    if direction_filter == 'up':
        changed = exceeds_threshold and direction == 'up'
    elif direction_filter == 'down':
        changed = exceeds_threshold and direction == 'down'
    else:  # 'both'
        changed = exceeds_threshold and direction != 'none'

    # Generate summary
    if direction == 'none':
        summary = "No change"
    else:
        sign = '+' if direction == 'up' else ''
        if mode == 'percent':
            summary = f"{sign}{change_percent:.2f}%"
        else:
            summary = f"{sign}{change_absolute:.2f}"

    return {
        'ok': True,
        'changed': changed,
        'direction': direction,
        'change_percent': round(change_percent, 4),
        'change_absolute': round(change_absolute, 4),
        'current_value': current,
        'previous_value': previous,
        'summary': summary,
        'threshold_exceeded': exceeds_threshold,
        'mode': mode,
        'threshold': threshold
    }
