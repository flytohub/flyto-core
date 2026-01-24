"""
URL Validation Module
Validate URL format and structure
"""
from typing import Any, Dict
from urllib.parse import urlparse

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='validate.url',
    version='1.0.0',
    category='validate',
    tags=['validate', 'url', 'format', 'verification'],
    label='Validate URL',
    label_key='modules.validate.url.label',
    description='Validate URL format and structure',
    description_key='modules.validate.url.description',
    icon='Link',
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
        'url': {
            'type': 'string',
            'label': 'URL',
            'label_key': 'modules.validate.url.params.url.label',
            'description': 'URL to validate',
            'description_key': 'modules.validate.url.params.url.description',
            'placeholder': 'https://example.com/path',
            'required': True
        },
        'require_https': {
            'type': 'boolean',
            'label': 'Require HTTPS',
            'label_key': 'modules.validate.url.params.require_https.label',
            'description': 'Only accept HTTPS URLs',
            'description_key': 'modules.validate.url.params.require_https.description',
            'default': False,
            'required': False
        }
    },
    output_schema={
        'valid': {
            'type': 'boolean',
            'description': 'Whether the URL is valid',
            'description_key': 'modules.validate.url.output.valid.description'
        },
        'url': {
            'type': 'string',
            'description': 'The validated URL',
            'description_key': 'modules.validate.url.output.url.description'
        },
        'scheme': {
            'type': 'string',
            'description': 'URL scheme (http, https, etc)',
            'description_key': 'modules.validate.url.output.scheme.description'
        },
        'host': {
            'type': 'string',
            'description': 'Host/domain name',
            'description_key': 'modules.validate.url.output.host.description'
        },
        'port': {
            'type': 'number',
            'description': 'Port number if specified',
            'description_key': 'modules.validate.url.output.port.description'
        },
        'path': {
            'type': 'string',
            'description': 'URL path',
            'description_key': 'modules.validate.url.output.path.description'
        },
        'query': {
            'type': 'string',
            'description': 'Query string',
            'description_key': 'modules.validate.url.output.query.description'
        }
    },
    timeout_ms=5000,
)
async def validate_url(context: Dict[str, Any]) -> Dict[str, Any]:
    """Validate URL format and structure."""
    params = context['params']
    url = params.get('url', '').strip()
    require_https = params.get('require_https', False)

    if not url:
        raise ValidationError("Missing required parameter: url", field="url")

    try:
        parsed = urlparse(url)
        has_scheme = parsed.scheme in ('http', 'https', 'ftp', 'ftps', 'file')
        has_netloc = bool(parsed.netloc)
        is_valid = has_scheme and has_netloc

        if require_https and parsed.scheme != 'https':
            is_valid = False

        port = parsed.port if parsed.port else None

        return {
            'ok': True,
            'data': {
                'valid': is_valid,
                'url': url,
                'scheme': parsed.scheme,
                'host': parsed.hostname or '',
                'port': port,
                'path': parsed.path,
                'query': parsed.query
            }
        }
    except Exception:
        return {
            'ok': True,
            'data': {
                'valid': False,
                'url': url,
                'scheme': '',
                'host': '',
                'port': None,
                'path': '',
                'query': ''
            }
        }
