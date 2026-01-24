"""
String Slugify Module
Convert text to URL-friendly slug.
"""
from typing import Any, Dict
import re
import unicodedata

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='string.slugify',
    version='1.0.0',
    category='string',
    tags=['string', 'slug', 'url', 'seo', 'format'],
    label='Slugify',
    label_key='modules.string.slugify.label',
    description='Convert text to URL-friendly slug',
    description_key='modules.string.slugify.description',
    icon='Link',
    color='#6366F1',
    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['string.*', 'data.*', 'flow.*', 'api.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'text',
            type='text',
            label='Text',
            label_key='modules.string.slugify.params.text.label',
            description='Text to slugify',
            description_key='modules.string.slugify.params.text.description',
            required=True,
            placeholder='Hello World! This is a Test',
            group=FieldGroup.BASIC,
        ),
        field(
            'separator',
            type='string',
            label='Separator',
            label_key='modules.string.slugify.params.separator.label',
            description='Word separator',
            description_key='modules.string.slugify.params.separator.description',
            default='-',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'lowercase',
            type='boolean',
            label='Lowercase',
            label_key='modules.string.slugify.params.lowercase.label',
            description='Convert to lowercase',
            description_key='modules.string.slugify.params.lowercase.description',
            default=True,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'max_length',
            type='number',
            label='Max Length',
            label_key='modules.string.slugify.params.max_length.label',
            description='Maximum slug length (0 = unlimited)',
            description_key='modules.string.slugify.params.max_length.description',
            default=0,
            min=0,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'string',
            'description': 'URL-friendly slug',
            'description_key': 'modules.string.slugify.output.result.description'
        },
        'original': {
            'type': 'string',
            'description': 'Original text',
            'description_key': 'modules.string.slugify.output.original.description'
        }
    },
    timeout_ms=5000,
)
async def string_slugify(context: Dict[str, Any]) -> Dict[str, Any]:
    """Convert text to URL-friendly slug."""
    params = context['params']
    text = params.get('text')
    separator = params.get('separator', '-')
    lowercase = params.get('lowercase', True)
    max_length = params.get('max_length', 0)

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    original = str(text)
    separator = str(separator) if separator else '-'

    # Normalize unicode characters
    result = unicodedata.normalize('NFKD', original)
    result = result.encode('ascii', 'ignore').decode('ascii')

    # Convert to lowercase if requested
    if lowercase:
        result = result.lower()

    # Replace non-alphanumeric characters with separator
    result = re.sub(r'[^a-zA-Z0-9]+', separator, result)

    # Remove leading/trailing separators
    result = result.strip(separator)

    # Remove consecutive separators
    result = re.sub(f'{re.escape(separator)}+', separator, result)

    # Apply max length
    if max_length > 0 and len(result) > max_length:
        result = result[:max_length].rstrip(separator)

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': original
        }
    }
