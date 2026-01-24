"""
Format Currency Module
Format numbers as currency
"""
from typing import Any, Dict

from ...registry import register_module
from ...errors import ValidationError


CURRENCY_SYMBOLS = {
    'USD': '$',
    'EUR': '\u20ac',
    'GBP': '\u00a3',
    'JPY': '\u00a5',
    'CNY': '\u00a5',
    'TWD': 'NT$',
    'KRW': '\u20a9',
    'INR': '\u20b9',
    'BTC': '\u20bf',
}


@register_module(
    module_id='format.currency',
    version='1.0.0',
    category='format',
    tags=['format', 'currency', 'money', 'finance'],
    label='Format Currency',
    label_key='modules.format.currency.label',
    description='Format numbers as currency',
    description_key='modules.format.currency.description',
    icon='DollarSign',
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
        'amount': {
            'type': 'number',
            'label': 'Amount',
            'label_key': 'modules.format.currency.params.amount.label',
            'description': 'Amount to format',
            'description_key': 'modules.format.currency.params.amount.description',
            'placeholder': '1234.56',
            'required': True
        },
        'currency': {
            'type': 'string',
            'label': 'Currency',
            'label_key': 'modules.format.currency.params.currency.label',
            'description': 'Currency code (USD, EUR, GBP, etc)',
            'description_key': 'modules.format.currency.params.currency.description',
            'default': 'USD',
            'required': False,
            'options': [
                {'value': 'USD', 'label': 'US Dollar ($)'},
                {'value': 'EUR', 'label': 'Euro (\u20ac)'},
                {'value': 'GBP', 'label': 'British Pound (\u00a3)'},
                {'value': 'JPY', 'label': 'Japanese Yen (\u00a5)'},
                {'value': 'CNY', 'label': 'Chinese Yuan (\u00a5)'},
                {'value': 'TWD', 'label': 'Taiwan Dollar (NT$)'},
                {'value': 'KRW', 'label': 'Korean Won (\u20a9)'},
                {'value': 'INR', 'label': 'Indian Rupee (\u20b9)'}
            ]
        },
        'decimal_places': {
            'type': 'number',
            'label': 'Decimal Places',
            'label_key': 'modules.format.currency.params.decimal_places.label',
            'description': 'Number of decimal places',
            'description_key': 'modules.format.currency.params.decimal_places.description',
            'default': 2,
            'min': 0,
            'max': 4,
            'required': False
        },
        'symbol_position': {
            'type': 'string',
            'label': 'Symbol Position',
            'label_key': 'modules.format.currency.params.symbol_position.label',
            'description': 'Position of currency symbol',
            'description_key': 'modules.format.currency.params.symbol_position.description',
            'default': 'before',
            'required': False,
            'options': [
                {'value': 'before', 'label': 'Before ($100)'},
                {'value': 'after', 'label': 'After (100$)'}
            ]
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Formatted currency string',
            'description_key': 'modules.format.currency.output.result.description'
        },
        'original': {
            'type': 'number',
            'description': 'Original amount',
            'description_key': 'modules.format.currency.output.original.description'
        },
        'symbol': {
            'type': 'string',
            'description': 'Currency symbol used',
            'description_key': 'modules.format.currency.output.symbol.description'
        }
    },
    timeout_ms=5000,
)
async def format_currency(context: Dict[str, Any]) -> Dict[str, Any]:
    """Format numbers as currency."""
    params = context['params']
    amount = params.get('amount')
    currency = params.get('currency', 'USD')
    decimal_places = params.get('decimal_places', 2)
    symbol_position = params.get('symbol_position', 'before')

    if amount is None:
        raise ValidationError("Missing required parameter: amount", field="amount")

    try:
        num = float(amount)
    except (ValueError, TypeError):
        raise ValidationError("Invalid amount", field="amount")

    symbol = CURRENCY_SYMBOLS.get(currency.upper(), currency)

    formatted_num = f"{abs(num):,.{decimal_places}f}"

    if symbol_position == 'after':
        result = f"{formatted_num}{symbol}"
    else:
        result = f"{symbol}{formatted_num}"

    if num < 0:
        result = f"-{result}"

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': amount,
            'symbol': symbol
        }
    }
