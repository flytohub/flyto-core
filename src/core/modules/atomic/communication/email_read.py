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


logger = logging.getLogger(__name__)


@register_module(
    module_id='email.read',
    version='1.0.0',
    category='communication',
    subcategory='email',
    tags=['email', 'imap', 'read', 'fetch', 'inbox'],
    label='Read Email',
    label_key='modules.email.read.label',
    description='Read emails from IMAP server',
    description_key='modules.email.read.description',
    icon='Mail',
    color='#4285F4',

    input_types=['object'],
    output_types=['array', 'object'],
    can_connect_to=['data.*', 'array.*'],

    timeout=60,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.imap'],

    params_schema={
        'folder': {
            'type': 'string',
            'label': 'Folder',
            'label_key': 'modules.email.read.params.folder.label',
            'description': 'Mailbox folder to read from',
            'description_key': 'modules.email.read.params.folder.description',
            'required': False,
            'default': 'INBOX'
        },
        'limit': {
            'type': 'number',
            'label': 'Limit',
            'label_key': 'modules.email.read.params.limit.label',
            'description': 'Maximum number of emails to fetch',
            'description_key': 'modules.email.read.params.limit.description',
            'required': False,
            'default': 10
        },
        'unread_only': {
            'type': 'boolean',
            'label': 'Unread Only',
            'label_key': 'modules.email.read.params.unread_only.label',
            'description': 'Only fetch unread emails',
            'description_key': 'modules.email.read.params.unread_only.description',
            'required': False,
            'default': False
        },
        'since_date': {
            'type': 'string',
            'label': 'Since Date',
            'label_key': 'modules.email.read.params.since_date.label',
            'description': 'Fetch emails since this date (YYYY-MM-DD)',
            'description_key': 'modules.email.read.params.since_date.description',
            'required': False
        },
        'from_filter': {
            'type': 'string',
            'label': 'From Filter',
            'label_key': 'modules.email.read.params.from_filter.label',
            'description': 'Filter by sender email address',
            'description_key': 'modules.email.read.params.from_filter.description',
            'required': False
        },
        'subject_filter': {
            'type': 'string',
            'label': 'Subject Filter',
            'label_key': 'modules.email.read.params.subject_filter.label',
            'description': 'Filter by subject (contains)',
            'description_key': 'modules.email.read.params.subject_filter.description',
            'required': False
        },
        'imap_host': {
            'type': 'string',
            'label': 'IMAP Host',
            'label_key': 'modules.email.read.params.imap_host.label',
            'description': 'IMAP server host',
            'description_key': 'modules.email.read.params.imap_host.description',
            'required': False
        },
        'imap_port': {
            'type': 'number',
            'label': 'IMAP Port',
            'label_key': 'modules.email.read.params.imap_port.label',
            'description': 'IMAP server port',
            'description_key': 'modules.email.read.params.imap_port.description',
            'required': False,
            'default': 993
        },
        'imap_user': {
            'type': 'string',
            'label': 'IMAP User',
            'label_key': 'modules.email.read.params.imap_user.label',
            'description': 'IMAP username',
            'description_key': 'modules.email.read.params.imap_user.description',
            'required': False
        },
        'imap_password': {
            'type': 'string',
            'label': 'IMAP Password',
            'label_key': 'modules.email.read.params.imap_password.label',
            'description': 'IMAP password',
            'description_key': 'modules.email.read.params.imap_password.description',
            'required': False,
            'secret': True
        }
    },
    output_schema={
        'emails': {
            'type': 'array',
            'description': 'List of email objects'
        },
        'count': {
            'type': 'number',
            'description': 'Number of emails fetched'
        }
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
