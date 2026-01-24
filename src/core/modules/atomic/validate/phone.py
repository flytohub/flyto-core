"""
Phone Number Validation Module
Validate phone number format
"""
from typing import Any, Dict
import re

from ...registry import register_module
from ...errors import ValidationError


PHONE_PATTERNS = {
    'international': re.compile(r'^\+?[1-9]\d{6,14}$'),
    'us': re.compile(r'^(\+1)?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$'),
    'tw': re.compile(r'^(\+886|0)?[2-9]\d{7,8}$'),
    'cn': re.compile(r'^(\+86)?1[3-9]\d{9}$'),
    'jp': re.compile(r'^(\+81|0)?[789]0\d{8}$'),
}


@register_module(
    module_id='validate.phone',
    version='1.0.0',
    category='validate',
    tags=['validate', 'phone', 'format', 'verification'],
    label='Validate Phone',
    label_key='modules.validate.phone.label',
    description='Validate phone number format',
    description_key='modules.validate.phone.description',
    icon='Phone',
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
        'phone': {
            'type': 'string',
            'label': 'Phone Number',
            'label_key': 'modules.validate.phone.params.phone.label',
            'description': 'Phone number to validate',
            'description_key': 'modules.validate.phone.params.phone.description',
            'placeholder': '+1234567890',
            'required': True
        },
        'region': {
            'type': 'string',
            'label': 'Region',
            'label_key': 'modules.validate.phone.params.region.label',
            'description': 'Region code for validation (international, us, tw, cn, jp)',
            'description_key': 'modules.validate.phone.params.region.description',
            'default': 'international',
            'required': False,
            'options': [
                {'value': 'international', 'label': 'International'},
                {'value': 'us', 'label': 'United States'},
                {'value': 'tw', 'label': 'Taiwan'},
                {'value': 'cn', 'label': 'China'},
                {'value': 'jp', 'label': 'Japan'}
            ]
        }
    },
    output_schema={
        'valid': {
            'type': 'boolean',
            'description': 'Whether the phone number is valid',
            'description_key': 'modules.validate.phone.output.valid.description'
        },
        'phone': {
            'type': 'string',
            'description': 'The validated phone number',
            'description_key': 'modules.validate.phone.output.phone.description'
        },
        'normalized': {
            'type': 'string',
            'description': 'Normalized phone number (digits only)',
            'description_key': 'modules.validate.phone.output.normalized.description'
        },
        'region': {
            'type': 'string',
            'description': 'Region used for validation',
            'description_key': 'modules.validate.phone.output.region.description'
        }
    },
    timeout_ms=5000,
)
async def validate_phone(context: Dict[str, Any]) -> Dict[str, Any]:
    """Validate phone number format."""
    params = context['params']
    phone = params.get('phone', '').strip()
    region = params.get('region', 'international')

    if not phone:
        raise ValidationError("Missing required parameter: phone", field="phone")

    normalized = re.sub(r'[^\d+]', '', phone)
    pattern = PHONE_PATTERNS.get(region, PHONE_PATTERNS['international'])
    is_valid = bool(pattern.match(normalized))

    return {
        'ok': True,
        'data': {
            'valid': is_valid,
            'phone': phone,
            'normalized': normalized,
            'region': region
        }
    }
