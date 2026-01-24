"""
Format Percentage Module
Format numbers as percentages
"""
from typing import Any, Dict

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='format.percentage',
    version='1.0.0',
    category='format',
    tags=['format', 'percentage', 'percent', 'ratio'],
    label='Format Percentage',
    label_key='modules.format.percentage.label',
    description='Format numbers as percentages',
    description_key='modules.format.percentage.description',
    icon='Percent',
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
        'value': {
            'type': 'number',
            'label': 'Value',
            'label_key': 'modules.format.percentage.params.value.label',
            'description': 'Value to format as percentage',
            'description_key': 'modules.format.percentage.params.value.description',
            'placeholder': '0.75',
            'required': True
        },
        'is_ratio': {
            'type': 'boolean',
            'label': 'Is Ratio',
            'label_key': 'modules.format.percentage.params.is_ratio.label',
            'description': 'Input is a ratio (0-1) that needs to be multiplied by 100',
            'description_key': 'modules.format.percentage.params.is_ratio.description',
            'default': True,
            'required': False
        },
        'decimal_places': {
            'type': 'number',
            'label': 'Decimal Places',
            'label_key': 'modules.format.percentage.params.decimal_places.label',
            'description': 'Number of decimal places',
            'description_key': 'modules.format.percentage.params.decimal_places.description',
            'default': 1,
            'min': 0,
            'max': 6,
            'required': False
        },
        'include_sign': {
            'type': 'boolean',
            'label': 'Include Sign',
            'label_key': 'modules.format.percentage.params.include_sign.label',
            'description': 'Include + sign for positive values',
            'description_key': 'modules.format.percentage.params.include_sign.description',
            'default': False,
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Formatted percentage string',
            'description_key': 'modules.format.percentage.output.result.description'
        },
        'original': {
            'type': 'number',
            'description': 'Original value',
            'description_key': 'modules.format.percentage.output.original.description'
        },
        'numeric': {
            'type': 'number',
            'description': 'Numeric percentage value',
            'description_key': 'modules.format.percentage.output.numeric.description'
        }
    },
    timeout_ms=5000,
)
async def format_percentage(context: Dict[str, Any]) -> Dict[str, Any]:
    """Format numbers as percentages."""
    params = context['params']
    value = params.get('value')
    is_ratio = params.get('is_ratio', True)
    decimal_places = params.get('decimal_places', 1)
    include_sign = params.get('include_sign', False)

    if value is None:
        raise ValidationError("Missing required parameter: value", field="value")

    try:
        num = float(value)
    except (ValueError, TypeError):
        raise ValidationError("Invalid value", field="value")

    if is_ratio:
        percentage = num * 100
    else:
        percentage = num

    formatted = f"{percentage:.{decimal_places}f}"

    if include_sign and percentage > 0:
        result = f"+{formatted}%"
    else:
        result = f"{formatted}%"

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': value,
            'numeric': round(percentage, decimal_places)
        }
    }
