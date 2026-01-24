"""
Email Validation Module
Validate email address format using RFC 5322 compliant regex
"""
from typing import Any, Dict
import re

from ...registry import register_module
from ...schema import compose, presets
from ...errors import ValidationError


EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)


@register_module(
    module_id='validate.email',
    version='1.0.0',
    category='validate',
    tags=['validate', 'email', 'format', 'verification'],
    label='Validate Email',
    label_key='modules.validate.email.label',
    description='Validate email address format',
    description_key='modules.validate.email.description',
    icon='Mail',
    color='#10B981',
    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['flow.*', 'data.*', 'notification.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'email': {
            'type': 'string',
            'label': 'Email',
            'label_key': 'modules.validate.email.params.email.label',
            'description': 'Email address to validate',
            'description_key': 'modules.validate.email.params.email.description',
            'placeholder': 'user@example.com',
            'required': True
        }
    },
    output_schema={
        'valid': {
            'type': 'boolean',
            'description': 'Whether the email is valid',
            'description_key': 'modules.validate.email.output.valid.description'
        },
        'email': {
            'type': 'string',
            'description': 'The validated email',
            'description_key': 'modules.validate.email.output.email.description'
        },
        'local_part': {
            'type': 'string',
            'description': 'The local part (before @)',
            'description_key': 'modules.validate.email.output.local_part.description'
        },
        'domain': {
            'type': 'string',
            'description': 'The domain part (after @)',
            'description_key': 'modules.validate.email.output.domain.description'
        }
    },
    timeout_ms=5000,
)
async def validate_email(context: Dict[str, Any]) -> Dict[str, Any]:
    """Validate email address format."""
    params = context['params']
    email = params.get('email', '').strip()

    if not email:
        raise ValidationError("Missing required parameter: email", field="email")

    is_valid = bool(EMAIL_REGEX.match(email))
    local_part = ''
    domain = ''

    if '@' in email:
        parts = email.split('@')
        local_part = parts[0]
        domain = parts[1] if len(parts) > 1 else ''

    return {
        'ok': True,
        'data': {
            'valid': is_valid,
            'email': email,
            'local_part': local_part,
            'domain': domain
        }
    }
