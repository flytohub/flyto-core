# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Google Gmail Search Module
Search Gmail messages using the Gmail API with OAuth2 access token and aiohttp.

HOW FAR THIS MODULE FOLLOWS REALITY: two rungs, and the rung is not decided by
the number this module reports.

  the search returned message ids    OBSERVED
      Ids came back from the mailbox. Those ids are a measurement of what is
      there -- the service naming messages that match -- and they are the fact
      the rung rests on.

  the search returned none           ACCEPTED
      An empty result reads identically whether the mailbox holds nothing
      matching, the query was malformed into matching nothing, or the token
      belongs to a different account. The empty-read case, answered the way
      `database.query` answers it: the service replied, and the reply contains
      no observation of any message.

WHY NOT `len(messages)`, the number in the payload. This module makes a second
request per id, and `_fetch_message_metadata` returns None on any non-200 --
logging a warning and dropping that message from the list. So `total` can be
smaller than what matched, or even 0 while the mailbox plainly contains matches,
and a rung read off it would report ACCEPTED for a search that observed twelve
messages and merely failed to describe them. The two counts are separated in the
payload (`total` and `matched_ids`) and the shortfall is carried in its own
effect, so a consumer can see an incomplete read instead of a small one.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from .....engine.outcome import ClaimBy, Outcome, envelope
from ....errors import ModuleError, ValidationError
from ....registry import register_module
from ....schema import compose
from ....schema.builders import field
from ....schema.constants import FieldGroup

logger = logging.getLogger(__name__)

GMAIL_MESSAGES_URL = 'https://gmail.googleapis.com/gmail/v1/users/me/messages'


@register_module(
    module_id='google.gmail.search',
    version='1.0.0',
    category='cloud',
    tags=['cloud', 'google', 'gmail', 'email', 'search', 'query'],
    label='Gmail Search',
    label_key='modules.google.gmail.search.label',
    description='Search Gmail messages using Gmail search query syntax',
    description_key='modules.google.gmail.search.description',
    icon='Mail',
    color='#4285F4',
    input_types=['string'],
    output_types=['array', 'object'],
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
              description='Google OAuth2 access token with Gmail read scope',
              placeholder='ya29.a0AfH6SM...', format='password'),
        field('query', type='string', label='Search Query', required=True,
              group=FieldGroup.BASIC,
              description='Gmail search query (e.g. "from:team@flyto2.com subject:invoice")',
              placeholder='from:team@flyto2.com'),
        field('max_results', type='number', label='Max Results',
              group=FieldGroup.OPTIONS,
              description='Maximum number of messages to return',
              default=10, min=1, max=100),
    ),
    output_schema={
        'messages': {
            'type': 'array',
            'description': 'List of matching messages',
            'description_key': 'modules.google.gmail.search.output.messages.description',
            'items': {
                'type': 'object',
                'properties': {
                    'id': {'type': 'string', 'description': 'Message ID'},
                    'thread_id': {'type': 'string', 'description': 'Thread ID'},
                    'subject': {'type': 'string', 'description': 'Email subject'},
                    'from': {'type': 'string', 'description': 'Sender address'},
                    'snippet': {'type': 'string', 'description': 'Message snippet'},
                    'date': {'type': 'string', 'description': 'Date header value'},
                },
            },
        },
        'total': {
            'type': 'number',
            'description': (
                'Number of messages in the list above: those whose metadata was '
                'fetched successfully. Can be lower than matched_ids'
            ),
            'description_key': 'modules.google.gmail.search.output.total.description',
        },
        'matched_ids': {
            'type': 'number',
            'description': (
                'Number of message ids the search itself returned, before the '
                'per-message metadata fetch that can drop some of them'
            ),
            'description_key': 'modules.google.gmail.search.output.matched_ids.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far this search was followed into reality: observed when the '
                'search returned ids, accepted when it returned none. Decided '
                'from the ids, not from the messages that could be described'
            ),
            'description_key': 'modules.google.gmail.search.output.outcome.description',
        },
    },
    examples=[
        {
            'title': 'Search for emails from a specific sender',
            'params': {
                'access_token': '<oauth2-token>',
                'query': 'from:team@flyto2.com is:unread',
                'max_results': 5,
            },
        },
    ],
    author='Flyto2 Team',
    license='MIT',
)
async def google_gmail_search(context: Dict[str, Any]) -> Dict[str, Any]:
    """Search Gmail messages."""
    params = context.get('params', {})

    access_token = params.get('access_token')
    query = params.get('query')
    max_results = int(params.get('max_results', 10))

    if not access_token:
        raise ValidationError('Access token is required', field='access_token')
    if not query:
        raise ValidationError('Search query is required', field='query')

    messages, matched_ids = await _search_messages(access_token, query, max_results)

    return {
        'ok': True,
        'data': {
            'messages': messages,
            'total': len(messages),
            'matched_ids': matched_ids,
            'outcome': _search_outcome(query, matched_ids, len(messages)),
        },
    }


def _search_outcome(query: str, matched_ids: int, described: int) -> Dict[str, Any]:
    """OBSERVED when the search named messages, ACCEPTED when it named none."""
    if matched_ids <= 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'no_messages_matched',
                'query': query,
                'measured_by': None,
                'detail': (
                    'The service answered with no message ids. That is not an '
                    'observation of the mailbox: nothing matching, a query that '
                    'matched nothing, and a token for the wrong account all read '
                    'the same.'
                ),
            }],
        )

    effects: List[Dict[str, Any]] = [{
        'kind': 'messages_matched',
        'query': query,
        'count': matched_ids,
        'measured_by': 'len() over the message ids the search returned',
        'detail': (
            'Ids the service returned for messages that match. Capped by '
            'maxResults, so this is what came back under that cap, not a total.'
        ),
    }]

    if described < matched_ids:
        effects.append({
            'kind': 'message_metadata_incomplete',
            'matched_ids': matched_ids,
            'described': described,
            'measured_by': 'ids returned by the search, minus messages in the payload',
            'detail': (
                'Some per-message metadata fetches did not return 200 and those '
                'messages were dropped from the list. The search observed them; '
                'this module could not describe them.'
            ),
        })

    return envelope(Outcome.OBSERVED, claim_by=ClaimBy.NONE, effects=effects)


async def _search_messages(
    access_token: str, query: str, max_results: int
) -> Tuple[List[Dict[str, Any]], int]:
    """Search Gmail and fetch message metadata.

    Returns the described messages AND how many ids the search returned. The
    second number used to be discarded inside this function, which is what made
    a dropped metadata fetch invisible to every caller.
    """
    headers = {'Authorization': f'Bearer {access_token}'}
    messages: List[Dict[str, Any]] = []
    matched_ids = 0

    try:
        async with aiohttp.ClientSession() as session:
            # Step 1: Search for message IDs
            async with session.get(
                GMAIL_MESSAGES_URL,
                params={'q': query, 'maxResults': str(max_results)},
                headers=headers, timeout=aiohttp.ClientTimeout(total=25),
            ) as resp:
                if resp.status != 200:
                    resp_data = await resp.json()
                    error_msg = resp_data.get('error', {}).get('message', str(resp_data))
                    raise ModuleError(f'Gmail API error (HTTP {resp.status}): {error_msg}')
                search_data = await resp.json()

            # Step 2: Fetch details for each message
            message_refs = search_data.get('messages', []) or []
            matched_ids = len(message_refs)
            for msg_ref in message_refs:
                msg = await _fetch_message_metadata(session, headers, msg_ref['id'])
                if msg:
                    messages.append(msg)
    except aiohttp.ClientError as exc:
        raise ModuleError(f'Gmail API request failed: {exc}') from exc

    return messages, matched_ids


async def _fetch_message_metadata(session, headers: dict, msg_id: str) -> Optional[Dict[str, Any]]:
    """Fetch metadata for a single Gmail message."""
    msg_url = f'{GMAIL_MESSAGES_URL}/{msg_id}'
    msg_params = {'format': 'metadata', 'metadataHeaders': 'Subject,From,Date'}

    async with session.get(
        msg_url, params=msg_params, headers=headers,
        timeout=aiohttp.ClientTimeout(total=10),
    ) as msg_resp:
        if msg_resp.status != 200:
            logger.warning('Failed to fetch message %s: HTTP %s', msg_id, msg_resp.status)
            return None
        msg_data = await msg_resp.json()

    header_map: Dict[str, str] = {}
    for hdr in msg_data.get('payload', {}).get('headers', []):
        name = hdr.get('name', '').lower()
        if name in ('subject', 'from', 'date'):
            header_map[name] = hdr.get('value', '')

    return {
        'id': msg_data.get('id', ''),
        'thread_id': msg_data.get('threadId', ''),
        'subject': header_map.get('subject', ''),
        'from': header_map.get('from', ''),
        'snippet': msg_data.get('snippet', ''),
        'date': header_map.get('date', ''),
    }
