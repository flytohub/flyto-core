"""
Format Number Module
Format numbers with thousand separators and decimal places
"""
from typing import Any, Dict

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='format.number',
    version='1.0.0',
    category='format',
    tags=['format', 'number', 'thousand', 'decimal'],
    label='Format Number',
    label_key='modules.format.number.label',
    description='Format numbers with separators and decimals',
    description_key='modules.format.number.description',
    icon='Hash',
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
        'number': {
            'type': 'number',
            'label': 'Number',
            'label_key': 'modules.format.number.params.number.label',
            'description': 'Number to format',
            'description_key': 'modules.format.number.params.number.description',
            'placeholder': '1234567.89',
            'required': True
        },
        'decimal_places': {
            'type': 'number',
            'label': 'Decimal Places',
            'label_key': 'modules.format.number.params.decimal_places.label',
            'description': 'Number of decimal places',
            'description_key': 'modules.format.number.params.decimal_places.description',
            'default': 2,
            'min': 0,
            'max': 10,
            'required': False
        },
        'thousand_separator': {
            'type': 'string',
            'label': 'Thousand Separator',
            'label_key': 'modules.format.number.params.thousand_separator.label',
            'description': 'Separator for thousands',
            'description_key': 'modules.format.number.params.thousand_separator.description',
            'default': ',',
            'required': False
        },
        'decimal_separator': {
            'type': 'string',
            'label': 'Decimal Separator',
            'label_key': 'modules.format.number.params.decimal_separator.label',
            'description': 'Separator for decimals',
            'description_key': 'modules.format.number.params.decimal_separator.description',
            'default': '.',
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Formatted number string',
            'description_key': 'modules.format.number.output.result.description'
        },
        'original': {
            'type': 'number',
            'description': 'Original number',
            'description_key': 'modules.format.number.output.original.description'
        }
    },
    timeout_ms=5000,
)
async def format_number(context: Dict[str, Any]) -> Dict[str, Any]:
    """Format numbers with separators and decimals."""
    params = context['params']
    number = params.get('number')
    decimal_places = params.get('decimal_places', 2)
    thousand_sep = params.get('thousand_separator', ',')
    decimal_sep = params.get('decimal_separator', '.')

    if number is None:
        raise ValidationError("Missing required parameter: number", field="number")

    try:
        num = float(number)
    except (ValueError, TypeError):
        raise ValidationError("Invalid number", field="number")

    formatted = f"{num:,.{decimal_places}f}"

    if thousand_sep != ',' or decimal_sep != '.':
        formatted = formatted.replace(',', '\x00').replace('.', decimal_sep).replace('\x00', thousand_sep)

    return {
        'ok': True,
        'data': {
            'result': formatted,
            'original': number
        }
    }
