"""
Extract Emails Module
Extract all email addresses from text
"""
from typing import Any, Dict, List
import re

from ...registry import register_module
from ...errors import ValidationError


EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    re.IGNORECASE
)


@register_module(
    module_id='text.extract_emails',
    version='1.0.0',
    category='text',
    tags=['text', 'email', 'extract', 'analysis'],
    label='Extract Emails',
    label_key='modules.text.extract_emails.label',
    description='Extract all email addresses from text',
    description_key='modules.text.extract_emails.description',
    icon='Mail',
    color='#F59E0B',
    input_types=['string'],
    output_types=['array'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'flow.*', 'communication.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=[],

    params_schema={
        'text': {
            'type': 'text',
            'label': 'Text',
            'label_key': 'modules.text.extract_emails.params.text.label',
            'description': 'Text to extract emails from',
            'description_key': 'modules.text.extract_emails.params.text.description',
            'placeholder': 'Contact us at info@example.com',
            'required': True
        },
        'unique': {
            'type': 'boolean',
            'label': 'Unique Only',
            'label_key': 'modules.text.extract_emails.params.unique.label',
            'description': 'Return only unique emails',
            'description_key': 'modules.text.extract_emails.params.unique.description',
            'default': True,
            'required': False
        },
        'lowercase': {
            'type': 'boolean',
            'label': 'Lowercase',
            'label_key': 'modules.text.extract_emails.params.lowercase.label',
            'description': 'Convert emails to lowercase',
            'description_key': 'modules.text.extract_emails.params.lowercase.description',
            'default': True,
            'required': False
        }
    },
    output_schema={
        'emails': {
            'type': 'array',
            'description': 'List of extracted emails',
            'description_key': 'modules.text.extract_emails.output.emails.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of emails found',
            'description_key': 'modules.text.extract_emails.output.count.description'
        },
        'domains': {
            'type': 'array',
            'description': 'Unique domains found',
            'description_key': 'modules.text.extract_emails.output.domains.description'
        }
    },
    timeout_ms=5000,
)
async def text_extract_emails(context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract all email addresses from text."""
    params = context['params']
    text = params.get('text')
    unique = params.get('unique', True)
    lowercase = params.get('lowercase', True)

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    text = str(text)
    emails = EMAIL_PATTERN.findall(text)

    if lowercase:
        emails = [e.lower() for e in emails]

    if unique:
        seen = set()
        unique_emails = []
        for email in emails:
            if email not in seen:
                seen.add(email)
                unique_emails.append(email)
        emails = unique_emails

    domains = list(set(e.split('@')[1] for e in emails if '@' in e))

    return {
        'ok': True,
        'data': {
            'emails': emails,
            'count': len(emails),
            'domains': domains
        }
    }
