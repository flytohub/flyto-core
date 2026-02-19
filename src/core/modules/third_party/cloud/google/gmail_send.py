# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

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
    description='Send an email via the Gmail API',
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
              format='password'),
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
        'message_id': {'type': 'string', 'description': 'Gmail message ID'},
        'thread_id': {'type': 'string', 'description': 'Gmail thread ID'},
        'to': {'type': 'string', 'description': 'Recipient email address'},
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

    is_html = params.get('html', False)
    cc = params.get('cc', '')
    bcc = params.get('bcc', '')

    # Build RFC 2822 MIME message
    if is_html:
        msg = MIMEMultipart('alternative')
        msg.attach(MIMEText(body, 'html'))
    else:
        msg = MIMEText(body, 'plain')

    msg['To'] = to
    msg['Subject'] = subject
    if cc:
        msg['Cc'] = cc
    if bcc:
        msg['Bcc'] = bcc

    # Base64url encode the message
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode('ascii')

    try:
        import aiohttp
    except ImportError:
        raise ModuleError(
            'aiohttp package is required. Install with: pip install aiohttp'
        )

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }
    payload = {'raw': raw_message}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GMAIL_SEND_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=25),
            ) as resp:
                resp_data = await resp.json()
                if resp.status != 200:
                    error_msg = resp_data.get('error', {}).get('message', str(resp_data))
                    raise ModuleError(
                        f'Gmail API error (HTTP {resp.status}): {error_msg}'
                    )
    except aiohttp.ClientError as exc:
        raise ModuleError(f'Gmail API request failed: {exc}')

    return {
        'ok': True,
        'data': {
            'message_id': resp_data.get('id', ''),
            'thread_id': resp_data.get('threadId', ''),
            'to': to,
        },
    }
