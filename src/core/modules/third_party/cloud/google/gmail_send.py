# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Google Gmail Send Module
Send an email via the Gmail API using OAuth2 access token and aiohttp.
"""

import base64
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any, Dict

from ....registry import register_module
from ....schema import compose
from ....schema.builders import field
from ....schema.constants import FieldGroup
from ....errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)

GMAIL_SEND_URL = 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send'


@register_module(
    module_id='google.gmail.send',
    version='1.0.0',
    category='cloud',
    tags=['cloud', 'google', 'gmail', 'email', 'send', 'notification'],
    label='Gmail Send',
    label_key='modules.google.gmail.send.label',
    description='Send an email via the Gmail API',
    description_key='modules.google.gmail.send.description',
    icon='Mail',
    color='#4285F4',
    input_types=['string', 'object'],
    output_types=['object'],
    can_receive_from=['*'],
    can_connect_to=['*'],
    retryable=True,
    max_retries=2,
    concurrent_safe=True,
    timeout_ms=30000,
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['cloud.email'],
    params_schema=compose(
        field('access_token', type='string', label='Access Token', required=True,
              group=FieldGroup.CONNECTION,
              description='Google OAuth2 access token with Gmail send scope',
              placeholder='ya29.a0AfH6SM...', format='password'),
        field('to', type='string', label='To', required=True,
              group=FieldGroup.BASIC,
              description='Recipient email address',
              placeholder='recipient@example.com', format='email'),
        field('subject', type='string', label='Subject', required=True,
              group=FieldGroup.BASIC,
              description='Email subject line',
              placeholder='Hello from Flyto'),
        field('body', type='string', label='Body', required=True,
              group=FieldGroup.BASIC,
              description='Email body content',
              placeholder='Your email body here...', format='multiline'),
        field('html', type='boolean', label='HTML',
              group=FieldGroup.OPTIONS,
              description='Whether the body is HTML content',
              default=False),
        field('cc', type='string', label='CC',
              group=FieldGroup.OPTIONS,
              description='CC email address(es), comma-separated',
              placeholder='cc@example.com'),
        field('bcc', type='string', label='BCC',
              group=FieldGroup.OPTIONS,
              description='BCC email address(es), comma-separated',
              placeholder='bcc@example.com'),
    ),
    output_schema={
        'message_id': {'type': 'string', 'description': 'Gmail message ID', 'description_key': 'modules.google.gmail.send.output.message_id.description'},
        'thread_id': {'type': 'string', 'description': 'Gmail thread ID', 'description_key': 'modules.google.gmail.send.output.thread_id.description'},
        'to': {'type': 'string', 'description': 'Recipient email address', 'description_key': 'modules.google.gmail.send.output.to.description'},
    },
    examples=[
        {
            'title': 'Send a plain text email',
            'params': {
                'access_token': '<oauth2-token>',
                'to': 'user@example.com',
                'subject': 'Test Email',
                'body': 'Hello, this is a test email.',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def google_gmail_send(context: Dict[str, Any]) -> Dict[str, Any]:
    """Send an email via the Gmail API."""
    params = context.get('params', {})

    access_token = params.get('access_token')
    to = params.get('to')
    subject = params.get('subject')
    body = params.get('body')

    if not access_token:
        raise ValidationError('Access token is required', field='access_token')
    if not to:
        raise ValidationError('Recipient email is required', field='to')
    if not subject:
        raise ValidationError('Subject is required', field='subject')
    if not body:
        raise ValidationError('Body is required', field='body')

    raw_message = _build_mime_message(params)
    resp_data = await _send_message(access_token, raw_message)

    return {
        'ok': True,
        'data': {
            'message_id': resp_data.get('id', ''),
            'thread_id': resp_data.get('threadId', ''),
            'to': to,
        },
    }


def _build_mime_message(params: Dict[str, Any]) -> str:
    """Build RFC 2822 MIME message and return base64url-encoded raw."""
    body = params['body']
    is_html = params.get('html', False)

    if is_html:
        msg = MIMEMultipart('alternative')
        msg.attach(MIMEText(body, 'html'))
    else:
        msg = MIMEText(body, 'plain')

    msg['To'] = params['to']
    msg['Subject'] = params['subject']
    if params.get('cc'):
        msg['Cc'] = params['cc']
    if params.get('bcc'):
        msg['Bcc'] = params['bcc']

    return base64.urlsafe_b64encode(msg.as_bytes()).decode('ascii')


async def _send_message(access_token: str, raw_message: str) -> Dict[str, Any]:
    """POST the raw message to Gmail API."""
    try:
        import aiohttp
    except ImportError:
        raise ModuleError('aiohttp package is required. Install with: pip install aiohttp')

    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GMAIL_SEND_URL, json={'raw': raw_message},
                headers=headers, timeout=aiohttp.ClientTimeout(total=25),
            ) as resp:
                resp_data = await resp.json()
                if resp.status != 200:
                    error_msg = resp_data.get('error', {}).get('message', str(resp_data))
                    raise ModuleError(f'Gmail API error (HTTP {resp.status}): {error_msg}')
                return resp_data
    except aiohttp.ClientError as exc:
        raise ModuleError(f'Gmail API request failed: {exc}')
