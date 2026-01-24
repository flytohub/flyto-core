"""
Credit Card Validation Module
Validate credit card number using Luhn algorithm
"""
from typing import Any, Dict
import re

from ...registry import register_module
from ...errors import ValidationError


CARD_PATTERNS = {
    'visa': re.compile(r'^4[0-9]{12}(?:[0-9]{3})?$'),
    'mastercard': re.compile(r'^5[1-5][0-9]{14}$'),
    'amex': re.compile(r'^3[47][0-9]{13}$'),
    'discover': re.compile(r'^6(?:011|5[0-9]{2})[0-9]{12}$'),
    'jcb': re.compile(r'^(?:2131|1800|35\d{3})\d{11}$'),
    'diners': re.compile(r'^3(?:0[0-5]|[68][0-9])[0-9]{11}$'),
}


def luhn_check(card_number: str) -> bool:
    """Validate card number using Luhn algorithm."""
    digits = [int(d) for d in card_number if d.isdigit()]
    if len(digits) < 13:
        return False

    checksum = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit

    return checksum % 10 == 0


@register_module(
    module_id='validate.credit_card',
    version='1.0.0',
    category='validate',
    tags=['validate', 'credit_card', 'payment', 'luhn', 'format'],
    label='Validate Credit Card',
    label_key='modules.validate.credit_card.label',
    description='Validate credit card number using Luhn algorithm',
    description_key='modules.validate.credit_card.description',
    icon='CreditCard',
    color='#10B981',
    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['flow.*', 'data.*', 'notification.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=[],

    params_schema={
        'card_number': {
            'type': 'string',
            'label': 'Card Number',
            'label_key': 'modules.validate.credit_card.params.card_number.label',
            'description': 'Credit card number to validate',
            'description_key': 'modules.validate.credit_card.params.card_number.description',
            'placeholder': '4111111111111111',
            'required': True
        }
    },
    output_schema={
        'valid': {
            'type': 'boolean',
            'description': 'Whether the card number is valid',
            'description_key': 'modules.validate.credit_card.output.valid.description'
        },
        'card_type': {
            'type': 'string',
            'description': 'Detected card type (visa, mastercard, etc)',
            'description_key': 'modules.validate.credit_card.output.card_type.description'
        },
        'masked': {
            'type': 'string',
            'description': 'Masked card number (****1234)',
            'description_key': 'modules.validate.credit_card.output.masked.description'
        },
        'luhn_valid': {
            'type': 'boolean',
            'description': 'Whether the Luhn checksum is valid',
            'description_key': 'modules.validate.credit_card.output.luhn_valid.description'
        }
    },
    timeout_ms=5000,
)
async def validate_credit_card(context: Dict[str, Any]) -> Dict[str, Any]:
    """Validate credit card number using Luhn algorithm."""
    params = context['params']
    card_number = params.get('card_number', '').strip()

    if not card_number:
        raise ValidationError("Missing required parameter: card_number", field="card_number")

    digits_only = re.sub(r'[\s\-]', '', card_number)

    if not digits_only.isdigit():
        return {
            'ok': True,
            'data': {
                'valid': False,
                'card_type': 'unknown',
                'masked': '',
                'luhn_valid': False
            }
        }

    luhn_valid = luhn_check(digits_only)

    card_type = 'unknown'
    for ctype, pattern in CARD_PATTERNS.items():
        if pattern.match(digits_only):
            card_type = ctype
            break

    masked = '*' * (len(digits_only) - 4) + digits_only[-4:]

    is_valid = luhn_valid and card_type != 'unknown'

    return {
        'ok': True,
        'data': {
            'valid': is_valid,
            'card_type': card_type,
            'masked': masked,
            'luhn_valid': luhn_valid
        }
    }
