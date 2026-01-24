"""
Extract URLs Module
Extract all URLs from text
"""
from typing import Any, Dict, List
import re

from ...registry import register_module
from ...errors import ValidationError


URL_PATTERN = re.compile(
    r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\-.?=&#%]*',
    re.IGNORECASE
)


@register_module(
    module_id='text.extract_urls',
    version='1.0.0',
    category='text',
    tags=['text', 'url', 'extract', 'analysis', 'links'],
    label='Extract URLs',
    label_key='modules.text.extract_urls.label',
    description='Extract all URLs from text',
    description_key='modules.text.extract_urls.description',
    icon='Link',
    color='#F59E0B',
    input_types=['string'],
    output_types=['array'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'flow.*', 'browser.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'text': {
            'type': 'text',
            'label': 'Text',
            'label_key': 'modules.text.extract_urls.params.text.label',
            'description': 'Text to extract URLs from',
            'description_key': 'modules.text.extract_urls.params.text.description',
            'placeholder': 'Visit https://example.com for more info',
            'required': True
        },
        'unique': {
            'type': 'boolean',
            'label': 'Unique Only',
            'label_key': 'modules.text.extract_urls.params.unique.label',
            'description': 'Return only unique URLs',
            'description_key': 'modules.text.extract_urls.params.unique.description',
            'default': True,
            'required': False
        }
    },
    output_schema={
        'urls': {
            'type': 'array',
            'description': 'List of extracted URLs',
            'description_key': 'modules.text.extract_urls.output.urls.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of URLs found',
            'description_key': 'modules.text.extract_urls.output.count.description'
        }
    },
    timeout_ms=5000,
)
async def text_extract_urls(context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract all URLs from text."""
    params = context['params']
    text = params.get('text')
    unique = params.get('unique', True)

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    text = str(text)
    urls = URL_PATTERN.findall(text)

    if unique:
        seen = set()
        unique_urls = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)
        urls = unique_urls

    return {
        'ok': True,
        'data': {
            'urls': urls,
            'count': len(urls)
        }
    }
