"""
UUID Validation Module
Validate UUID format and version
"""
from typing import Any, Dict
import re

from ...registry import register_module
from ...errors import ValidationError


UUID_REGEX = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$'
)


@register_module(
    module_id='validate.uuid',
    version='1.0.0',
    category='validate',
    tags=['validate', 'uuid', 'format', 'verification'],
    label='Validate UUID',
    label_key='modules.validate.uuid.label',
    description='Validate UUID format and version',
    description_key='modules.validate.uuid.description',
    icon='Fingerprint',
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
        'uuid': {
            'type': 'string',
            'label': 'UUID',
            'label_key': 'modules.validate.uuid.params.uuid.label',
            'description': 'UUID to validate',
            'description_key': 'modules.validate.uuid.params.uuid.description',
            'placeholder': '550e8400-e29b-41d4-a716-446655440000',
            'required': True
        },
        'version': {
            'type': 'number',
            'label': 'Version',
            'label_key': 'modules.validate.uuid.params.version.label',
            'description': 'Expected UUID version (1-5, or 0 for any)',
            'description_key': 'modules.validate.uuid.params.version.description',
            'default': 0,
            'min': 0,
            'max': 5,
            'required': False
        }
    },
    output_schema={
        'valid': {
            'type': 'boolean',
            'description': 'Whether the UUID is valid',
            'description_key': 'modules.validate.uuid.output.valid.description'
        },
        'uuid': {
            'type': 'string',
            'description': 'The validated UUID',
            'description_key': 'modules.validate.uuid.output.uuid.description'
        },
        'version': {
            'type': 'number',
            'description': 'Detected UUID version',
            'description_key': 'modules.validate.uuid.output.version.description'
        },
        'variant': {
            'type': 'string',
            'description': 'UUID variant',
            'description_key': 'modules.validate.uuid.output.variant.description'
        }
    },
    timeout_ms=5000,
)
async def validate_uuid(context: Dict[str, Any]) -> Dict[str, Any]:
    """Validate UUID format and version."""
    params = context['params']
    uuid_str = params.get('uuid', '').strip()
    expected_version = params.get('version', 0)

    if not uuid_str:
        raise ValidationError("Missing required parameter: uuid", field="uuid")

    is_valid = bool(UUID_REGEX.match(uuid_str))
    detected_version = 0
    variant = 'unknown'

    if is_valid:
        detected_version = int(uuid_str[14], 16)
        variant_char = uuid_str[19].lower()
        if variant_char in '89ab':
            variant = 'RFC 4122'
        elif variant_char in '01234567':
            variant = 'NCS'
        elif variant_char in 'cd':
            variant = 'Microsoft'
        else:
            variant = 'Future'

        if expected_version > 0 and detected_version != expected_version:
            is_valid = False

    return {
        'ok': True,
        'data': {
            'valid': is_valid,
            'uuid': uuid_str,
            'version': detected_version,
            'variant': variant
        }
    }
