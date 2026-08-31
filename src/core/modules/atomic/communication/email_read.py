# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Email Read Module
Read emails via IMAP

HOW FAR THIS MODULE FOLLOWS REALITY

There is no single rung here, for the same reason `database.query` has none:
three paths through one function measure three different things, and one of them
measures nothing at all.

  messages came back                          OBSERVED
      Every element of `emails` was built from bytes the server sent in reply
      to a FETCH -- `message_from_bytes(msg_data[0][1])`. Nothing is inferred.
      What it counts is messages FETCHED, never messages that MATCH: the
      `limit` truncates the id list before any fetch, and a fetch that fails is
      skipped, so `count` answers "how many did we pull" and the envelope
      carries `matched` and `requested` beside it so the difference survives.

  the search answered, and matched nothing     ACCEPTED
      `len(emails) == 0` after an OK search reads identically whether the
      mailbox is empty, the filters excluded everything, or the folder is not
      the one the caller meant. A value that would be unchanged if the effect
      had not happened is not evidence of it, so an empty read claims only that
      the server answered. Same shape, same answer as `database.query`'s empty
      result set.

  the search did NOT answer OK                 INDETERMINATE
      `if status != 'OK': return []` swallows a refused or failed SEARCH and
      hands back a payload that is indistinguishable from an empty mailbox:
      `ok: True, count: 0`. That zero is a literal written in this file, not
      anything the server said. It is not FAILED -- nothing raised and no
      postcondition was evaluated -- it is the severed observation channel that
      `engine/outcome.py` names: we cannot say what is in that folder.

READING IS NOT FREE, and the envelope says so. `mail.fetch(msg_id, '(RFC822)')`
is not a PEEK, so the server sets \\Seen on every message this module returns.
With `unread_only=True` that makes the module non-idempotent in the loudest
possible way: the second run over the same mailbox legitimately returns nothing,
because the first run consumed the very property it filtered on. That is a real
effect on somebody's mailbox and it is recorded as one.

VERIFIED is unreachable and not by oversight: no postcondition is declared and
none is evaluated, so `ceiling_for(None)` caps this at OBSERVED anyway.
"""
import asyncio
import logging
import os
from email import message_from_bytes
from email.header import decode_header
from typing import Any, Dict, List

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import enforce_outbound_host
from ...registry import register_module
from ...schema import compose, presets

logger = logging.getLogger(__name__)


def _seen_flag_effect(fetched: int) -> Dict[str, Any]:
    """The side effect of reading, which is invisible in the payload.

    Named in every envelope this module builds because a consumer cannot infer
    it from anywhere else: nothing in `emails` says the messages were marked
    read, and with `unread_only=True` that is the difference between a workflow
    that repeats and one that silently stops finding anything.
    """
    return {
        'kind': 'messages_marked_seen',
        'count': fetched,
        'measured_by': (
            "the FETCH this module issues is '(RFC822)', not '(BODY.PEEK[])' -- "
            'the server sets \\Seen on every message it returns to it'
        ),
        'detail': (
            'Reading these messages changed them. A later run with '
            'unread_only=true will not see them again, which is the module '
            'consuming the property it filtered on rather than a mailbox that '
            'went quiet.'
        ),
    }


def _read_outcome(
    *,
    folder: str,
    search_ok: bool,
    matched: int,
    requested: int,
    fetched: int,
) -> Dict[str, Any]:
    """The rung this read earned, decided per run from what actually came back.

    `matched` is the id count the SEARCH returned, `requested` the count left
    after `limit` truncates it, `fetched` the number of messages whose bytes
    arrived. They are three different numbers and the gaps between them are the
    part a `count` on its own cannot say.
    """
    if not search_ok:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'search_not_answered',
                'folder': folder,
                'measured_by': None,
                'detail': (
                    'The IMAP SEARCH did not come back OK, and this module '
                    'returns an empty list for that. The zero in `count` is a '
                    'literal written in this file, not the server saying the '
                    'folder is empty: what is in it is unknown here.'
                ),
            }],
        )

    if fetched <= 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'no_messages_returned',
                'folder': folder,
                'matched': matched,
                'measured_by': None,
                'detail': (
                    'The server answered the search and no message reached this '
                    'module. That is not an observation of the mailbox: an empty '
                    'list reads the same whether the folder is empty, the '
                    'filters excluded everything, or the folder is not the one '
                    'that was meant.'
                ),
            }],
        )

    effects: List[Dict[str, Any]] = [{
        'kind': 'messages_fetched',
        'folder': folder,
        'count': fetched,
        'matched': matched,
        'requested': requested,
        'measured_by': (
            'len() over messages parsed from bytes the server sent in reply to '
            'FETCH (RFC822)'
        ),
        'detail': (
            'Messages FETCHED, not messages that match: `limit` truncates the '
            'id list before any fetch, so `matched` is the size of the answer '
            'to the search and `count` is the size of what was pulled from it.'
        ),
    }]

    if fetched < requested:
        effects.append({
            'kind': 'messages_not_fetched',
            'folder': folder,
            'count': requested - fetched,
            'measured_by': 'ids the search returned within the limit, minus messages parsed',
            'detail': (
                'The server named these messages and then did not answer OK to '
                'the FETCH for them. They are absent from `emails` with nothing '
                'else in the payload saying so, so a consumer treating this '
                'list as the complete answer to the search would be wrong.'
            ),
        })

    effects.append(_seen_flag_effect(fetched))

    return envelope(Outcome.OBSERVED, claim_by=ClaimBy.NONE, effects=effects)


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
            'description': (
                'Number of emails fetched -- not the number that matched the '
                'search: `limit` truncates the id list first, and a message '
                'whose FETCH fails is skipped. See matched'
            )
        ,
                'description_key': 'modules.email.read.output.count.description'},
        'matched': {
            'type': 'number',
            'description': (
                'Number of message ids the IMAP SEARCH returned, before `limit` '
                'is applied. 0 when the search did not answer OK, which is not '
                'the same fact -- see outcome'
            )
        ,
                'description_key': 'modules.email.read.output.matched.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this read was followed: "observed" when messages came '
                'back, "accepted" when the search answered and nothing did, '
                '"indeterminate" when the search itself did not answer OK'
            )
        ,
                'description_key': 'modules.email.read.output.outcome.description'}
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
    imap_host = enforce_outbound_host(imap_host, purpose='IMAP')

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
        """``(emails, stats)`` -- the messages, and the three counts around them.

        `stats` is what makes the rung decidable: `search_ok` separates "the
        folder is empty" from "we never got an answer", and `matched` /
        `requested` separate the size of the search result from the size of what
        was pulled out of it. All three used to be discarded inside this
        closure, which is why a failed SEARCH and an empty mailbox left through
        the same `count: 0`.
        """
        stats = {'search_ok': False, 'matched': 0, 'requested': 0}
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
                return [], stats

            stats['search_ok'] = True
            message_ids = messages[0].split()
            stats['matched'] = len(message_ids)
            message_ids = message_ids[-limit:] if len(message_ids) > limit else message_ids
            message_ids = list(reversed(message_ids))
            stats['requested'] = len(message_ids)

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

            return emails, stats
        finally:
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass

    emails, stats = await asyncio.to_thread(_fetch_emails)

    if not stats['search_ok']:
        logger.warning(
            f"IMAP SEARCH in {folder} did not answer OK; returning an empty "
            f"list, which is not the same as an empty folder"
        )
    else:
        logger.info(
            f"Fetched {len(emails)} of {stats['matched']} matching emails from {folder}"
        )

    return {
        'ok': True,
        'emails': emails,
        'count': len(emails),
        'matched': stats['matched'],
        'outcome': _read_outcome(
            folder=folder,
            search_ok=stats['search_ok'],
            matched=stats['matched'],
            requested=stats['requested'],
            fetched=len(emails),
        ),
    }
