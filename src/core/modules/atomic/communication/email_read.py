"""
Email Read Module
Read emails via IMAP
"""
import asyncio
import logging
import os
from email import message_from_bytes
from email.header import decode_header
from typing import Any, Dict, List, Optional

from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


@register_module(
    module_id='email.read',
    stability="beta",
    version='1.0.0',
    category='communication',
    subcategory='email',
    tags=['email', 'imap', 'read', 'fetch', 'inbox', 'ssrf_protected', 'path_restricted'],
    label='Read Email',
    label_key='modules.email.read.label',
    description='Read emails from IMAP server',
    description_key='modules.email.read.description',
    icon='Mail',
    color='#4285F4',

    input_types=['object'],
    output_types=['array', 'object'],
    can_connect_to=['data.*', 'array.*'],
    can_receive_from=['*'],

    timeout_ms=60000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    requires_credentials=True,
    credential_keys=['API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'filesystem.write'],

    params_schema=compose(
        presets.EMAIL_FOLDER(),
        presets.EMAIL_LIMIT(),
        presets.EMAIL_UNREAD_ONLY(),
        presets.EMAIL_SINCE_DATE(),
        presets.EMAIL_FROM_FILTER(),
        presets.EMAIL_SUBJECT_FILTER(),
        presets.IMAP_HOST(),
        presets.IMAP_PORT(),
        presets.IMAP_USER(),
        presets.IMAP_PASSWORD(),
    ),
    output_schema={
        'emails': {
            'type': 'array',
            'description': 'List of email objects'
        ,
                'description_key': 'modules.email.read.output.emails.description'},
        'count': {
            'type': 'number',
            'description': 'Number of emails fetched'
        ,
                'description_key': 'modules.email.read.output.count.description'}
    },
    examples=[
        {
            'title': 'Read recent unread emails',
            'title_key': 'modules.email.read.examples.unread.title',
            'params': {
                'folder': 'INBOX',
                'unread_only': True,
                'limit': 5
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def email_read(context: Dict[str, Any]) -> Dict[str, Any]:
    """Read emails from IMAP server"""
    import imaplib

    params = context['params']
    folder = params.get('folder', 'INBOX')
    limit = params.get('limit', 10)
    unread_only = params.get('unread_only', False)
    since_date = params.get('since_date')
    from_filter = params.get('from_filter')
    subject_filter = params.get('subject_filter')

    imap_host = params.get('imap_host') or os.getenv('IMAP_HOST')
    imap_port = params.get('imap_port') or int(os.getenv('IMAP_PORT', '993'))
    imap_user = params.get('imap_user') or os.getenv('IMAP_USER')
    imap_password = params.get('imap_password') or os.getenv('IMAP_PASSWORD')

    if not imap_host:
        raise ValueError("IMAP host not configured. Set IMAP_HOST env or provide imap_host param")
    if not imap_user or not imap_password:
        raise ValueError("IMAP credentials not configured")

    def _decode_header_value(value):
        if value is None:
            return ''
        decoded_parts = decode_header(value)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or 'utf-8', errors='replace'))
            else:
                result.append(part)
        return ''.join(result)

    def _get_body(msg):
        body = ''
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        body = payload.decode(charset, errors='replace')
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or 'utf-8'
                body = payload.decode(charset, errors='replace')
        return body

    def _fetch_emails():
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        try:
            mail.login(imap_user, imap_password)
            mail.select(folder)

            search_criteria = []
            if unread_only:
                search_criteria.append('UNSEEN')
            if since_date:
                search_criteria.append(f'SINCE {since_date}')
            if from_filter:
                search_criteria.append(f'FROM "{from_filter}"')
            if subject_filter:
                search_criteria.append(f'SUBJECT "{subject_filter}"')

            if not search_criteria:
                search_criteria = ['ALL']

            status, messages = mail.search(None, ' '.join(search_criteria))
            if status != 'OK':
                return []

            message_ids = messages[0].split()
            message_ids = message_ids[-limit:] if len(message_ids) > limit else message_ids
            message_ids = list(reversed(message_ids))

            emails = []
            for msg_id in message_ids:
                status, msg_data = mail.fetch(msg_id, '(RFC822)')
                if status != 'OK':
                    continue

                raw_email = msg_data[0][1]
                msg = message_from_bytes(raw_email)

                email_data = {
                    'id': msg_id.decode(),
                    'subject': _decode_header_value(msg.get('Subject')),
                    'from': _decode_header_value(msg.get('From')),
                    'to': _decode_header_value(msg.get('To')),
                    'date': msg.get('Date'),
                    'body': _get_body(msg)
                }
                emails.append(email_data)

            return emails
        finally:
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass

    emails = await asyncio.to_thread(_fetch_emails)

    logger.info(f"Fetched {len(emails)} emails from {folder}")

    return {
        'ok': True,
        'emails': emails,
        'count': len(emails)
    }
