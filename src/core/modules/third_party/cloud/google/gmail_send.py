# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Google Gmail Send Module
Send an email via the Gmail API using OAuth2 access token and aiohttp.

HOW FAR THIS MODULE FOLLOWS REALITY: accepted, and it will not go higher.

A 200 from `messages/send` carrying an `id` and a `threadId` is Gmail saying it
took the message and filed it. That is a real answer from the other side -- more
than `dispatched`, which is a message that left with nobody confirming anything
-- and it is the definition of ACCEPTED: the peer acknowledged taking it.

It is not OBSERVED, and the gap is not a technicality. Nothing here looks at the
world after the fact: no read-back of the message, no fetch of the thread, and
above all nothing about delivery. A message id is assigned at the moment of
acceptance; the recipient's server may still bounce it, the address may not
exist, a filter may drop it. Reading the peer's report of its own work is taking
its word for it, which is exactly what separates the two rungs.

VERIFIED is unreachable and not by oversight: no postcondition is declared and
none is evaluated, so `ceiling_for(None)` caps this at OBSERVED anyway.

ONE THING THIS MODULE CANNOT SAY, and a reader should know it: a timeout. The
`total=25` client timeout raises `asyncio.TimeoutError`, which is not an
`aiohttp.ClientError` and so escapes the handler below uncaught. That is the
textbook INDETERMINATE -- the message may well have been sent -- and it matters
here more than on a read, because `retryable=True, max_retries=2` means a
timed-out send is retried and a mail that did go out can go out again. An
envelope cannot be attached to it today: every error path raises, and a raised
exception becomes a StepExecutionError with the payload discarded (the same
constraint `http.request` records for its own error branch). Fixing that is a
change to error and retry semantics, which is not a declaration's business.
"""

import base64
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any, Dict

from .....engine.outcome import ClaimBy, Outcome, envelope
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
              placeholder='support@flyto2.com', format='email'),
        field('subject', type='string', label='Subject', required=True,
              group=FieldGroup.BASIC,
              description='Email subject line',
              placeholder='Hello from Flyto2'),
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
              placeholder='team@flyto2.com'),
        field('bcc', type='string', label='BCC',
              group=FieldGroup.OPTIONS,
              description='BCC email address(es), comma-separated',
              placeholder='team@flyto2.com'),
    ),
    output_schema={
        'message_id': {'type': 'string', 'description': 'Gmail message ID', 'description_key': 'modules.google.gmail.send.output.message_id.description'},
        'thread_id': {'type': 'string', 'description': 'Gmail thread ID', 'description_key': 'modules.google.gmail.send.output.thread_id.description'},
        'to': {'type': 'string', 'description': 'Recipient email address', 'description_key': 'modules.google.gmail.send.output.to.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this send was followed into reality. Always '
                '"accepted": Gmail acknowledged the message and assigned it an '
                'id. Delivery to the recipient is not observed'
            ),
            'description_key': 'modules.google.gmail.send.output.outcome.description',
        },
    },
    examples=[
        {
            'title': 'Send a plain text email',
            'params': {
                'access_token': '<oauth2-token>',
                'to': 'team@flyto2.com',
                'subject': 'Test Email',
                'body': 'Hello, this is a test email.',
            },
        },
    ],
    author='Flyto2 Team',
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

    message_id = resp_data.get('id', '')
    thread_id = resp_data.get('threadId', '')

    return {
        'ok': True,
        'data': {
            'message_id': message_id,
            'thread_id': thread_id,
            'to': to,
            'outcome': envelope(
                Outcome.ACCEPTED,
                claim_by=ClaimBy.NONE,
                effects=[
                    {
                        'kind': 'message_accepted_by_gmail',
                        'message_id': message_id,
                        'thread_id': thread_id,
                        'measured_by': 'HTTP 200 from messages/send, with the id it returned',
                        'detail': (
                            'Gmail acknowledged the message and assigned it an id. '
                            "That is the service's report of its own work: the "
                            'message is not read back.'
                        ),
                    },
                    {
                        'kind': 'delivery_not_observed',
                        'to': to,
                        'measured_by': None,
                        'detail': (
                            'Nothing here observes delivery. An id is assigned at '
                            'acceptance; the recipient may still bounce it, the '
                            'address may not exist, a filter may drop it.'
                        ),
                    },
                ],
            ),
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
