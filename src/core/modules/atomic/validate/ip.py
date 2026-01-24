"""
IP Address Validation Module
Validate IPv4 and IPv6 address formats
"""
from typing import Any, Dict
import re

from ...registry import register_module
from ...errors import ValidationError


IPV4_REGEX = re.compile(
    r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
)

IPV6_REGEX = re.compile(
    r'^(?:(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|'
    r'(?:[0-9a-fA-F]{1,4}:){1,7}:|'
    r'(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|'
    r'(?:[0-9a-fA-F]{1,4}:){1,5}(?::[0-9a-fA-F]{1,4}){1,2}|'
    r'(?:[0-9a-fA-F]{1,4}:){1,4}(?::[0-9a-fA-F]{1,4}){1,3}|'
    r'(?:[0-9a-fA-F]{1,4}:){1,3}(?::[0-9a-fA-F]{1,4}){1,4}|'
    r'(?:[0-9a-fA-F]{1,4}:){1,2}(?::[0-9a-fA-F]{1,4}){1,5}|'
    r'[0-9a-fA-F]{1,4}:(?::[0-9a-fA-F]{1,4}){1,6}|'
    r':(?::[0-9a-fA-F]{1,4}){1,7}|'
    r'::(?:[fF]{4}:)?(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))$'
)


@register_module(
    module_id='validate.ip',
    version='1.0.0',
    category='validate',
    tags=['validate', 'ip', 'ipv4', 'ipv6', 'network', 'format'],
    label='Validate IP',
    label_key='modules.validate.ip.label',
    description='Validate IPv4 or IPv6 address format',
    description_key='modules.validate.ip.description',
    icon='Network',
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
        'ip': {
            'type': 'string',
            'label': 'IP Address',
            'label_key': 'modules.validate.ip.params.ip.label',
            'description': 'IP address to validate',
            'description_key': 'modules.validate.ip.params.ip.description',
            'placeholder': '192.168.1.1',
            'required': True
        },
        'version': {
            'type': 'string',
            'label': 'IP Version',
            'label_key': 'modules.validate.ip.params.version.label',
            'description': 'Expected IP version (any, v4, v6)',
            'description_key': 'modules.validate.ip.params.version.description',
            'default': 'any',
            'required': False,
            'options': [
                {'value': 'any', 'label': 'Any'},
                {'value': 'v4', 'label': 'IPv4 Only'},
                {'value': 'v6', 'label': 'IPv6 Only'}
            ]
        }
    },
    output_schema={
        'valid': {
            'type': 'boolean',
            'description': 'Whether the IP address is valid',
            'description_key': 'modules.validate.ip.output.valid.description'
        },
        'ip': {
            'type': 'string',
            'description': 'The validated IP address',
            'description_key': 'modules.validate.ip.output.ip.description'
        },
        'version': {
            'type': 'string',
            'description': 'Detected IP version (v4 or v6)',
            'description_key': 'modules.validate.ip.output.version.description'
        },
        'is_private': {
            'type': 'boolean',
            'description': 'Whether the IP is in a private range',
            'description_key': 'modules.validate.ip.output.is_private.description'
        },
        'is_loopback': {
            'type': 'boolean',
            'description': 'Whether the IP is a loopback address',
            'description_key': 'modules.validate.ip.output.is_loopback.description'
        }
    },
    timeout_ms=5000,
)
async def validate_ip(context: Dict[str, Any]) -> Dict[str, Any]:
    """Validate IPv4 or IPv6 address format."""
    params = context['params']
    ip = params.get('ip', '').strip()
    expected_version = params.get('version', 'any')

    if not ip:
        raise ValidationError("Missing required parameter: ip", field="ip")

    is_v4 = bool(IPV4_REGEX.match(ip))
    is_v6 = bool(IPV6_REGEX.match(ip))
    is_valid = is_v4 or is_v6
    detected_version = 'v4' if is_v4 else ('v6' if is_v6 else 'unknown')

    if expected_version == 'v4' and not is_v4:
        is_valid = False
    elif expected_version == 'v6' and not is_v6:
        is_valid = False

    is_private = False
    is_loopback = False

    if is_v4:
        parts = [int(p) for p in ip.split('.')]
        is_loopback = parts[0] == 127
        is_private = (
            parts[0] == 10 or
            (parts[0] == 172 and 16 <= parts[1] <= 31) or
            (parts[0] == 192 and parts[1] == 168)
        )
    elif is_v6:
        is_loopback = ip == '::1'
        is_private = ip.lower().startswith('fe80:') or ip.lower().startswith('fc') or ip.lower().startswith('fd')

    return {
        'ok': True,
        'data': {
            'valid': is_valid,
            'ip': ip,
            'version': detected_version,
            'is_private': is_private,
            'is_loopback': is_loopback
        }
    }
