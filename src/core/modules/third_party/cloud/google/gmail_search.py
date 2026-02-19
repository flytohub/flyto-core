"""
Google Gmail Search Module
Search Gmail messages using the Gmail API with OAuth2 access token and aiohttp.
"""

import logging
from typing import Any, Dict, List

from ....registry import register_module
from ....schema import compose
from ....schema.builders import field
from ....schema.constants import FieldGroup
from ....errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)

GMAIL_MESSAGES_URL = 'https://gmail.googleapis.com/gmail/v1/users/me/messages'


@register_module(
    module_id='google.gmail.search',
    version='1.0.0',
    category='cloud',
    tags=['cloud', 'google', 'gmail', 'email', 'search', 'query'],
    label='Gmail Search',
    description='Search Gmail messages using Gmail search query syntax',
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
              format='password'),
        field('query', type='string', label='Search Query', required=True,
              group=FieldGroup.BASIC,
              description='Gmail search query (e.g. "from:user@example.com subject:invoice")',
              placeholder='from:user@example.com'),
        field('max_results', type='number', label='Max Results',
              group=FieldGroup.OPTIONS,
              description='Maximum number of messages to return',
              default=10, min=1, max=100),
    ),
    output_schema={
        'messages': {
            'type': 'array',
            'description': 'List of matching messages',
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
        'total': {'type': 'number', 'description': 'Total number of messages returned'},
    },
    examples=[
        {
            'title': 'Search for emails from a specific sender',
            'params': {
                'access_token': '<oauth2-token>',
                'query': 'from:boss@company.com is:unread',
                'max_results': 5,
            },
        },
    ],
    author='Flyto Team',
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

    try:
        import aiohttp
    except ImportError:
        raise ModuleError(
            'aiohttp package is required. Install with: pip install aiohttp'
        )

    headers = {
        'Authorization': f'Bearer {access_token}',
    }

    messages: List[Dict[str, Any]] = []

    try:
        async with aiohttp.ClientSession() as session:
            # Step 1: Search for message IDs
            search_params = {
                'q': query,
                'maxResults': str(max_results),
            }
            async with session.get(
                GMAIL_MESSAGES_URL,
                params=search_params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=25),
            ) as resp:
                if resp.status != 200:
                    resp_data = await resp.json()
                    error_msg = resp_data.get('error', {}).get('message', str(resp_data))
                    raise ModuleError(
                        f'Gmail API error (HTTP {resp.status}): {error_msg}'
                    )
                search_data = await resp.json()

            message_refs = search_data.get('messages', [])

            # Step 2: Fetch details for each message
            for msg_ref in message_refs:
                msg_id = msg_ref['id']
                msg_url = f'{GMAIL_MESSAGES_URL}/{msg_id}'
                msg_params = {'format': 'metadata', 'metadataHeaders': 'Subject,From,Date'}

                async with session.get(
                    msg_url,
                    params=msg_params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as msg_resp:
                    if msg_resp.status != 200:
                        logger.warning('Failed to fetch message %s: HTTP %s', msg_id, msg_resp.status)
                        continue
                    msg_data = await msg_resp.json()

                # Extract headers
                header_map: Dict[str, str] = {}
                payload_headers = msg_data.get('payload', {}).get('headers', [])
                for hdr in payload_headers:
                    name = hdr.get('name', '').lower()
                    if name in ('subject', 'from', 'date'):
                        header_map[name] = hdr.get('value', '')

                messages.append({
                    'id': msg_data.get('id', ''),
                    'thread_id': msg_data.get('threadId', ''),
                    'subject': header_map.get('subject', ''),
                    'from': header_map.get('from', ''),
                    'snippet': msg_data.get('snippet', ''),
                    'date': header_map.get('date', ''),
                })

    except aiohttp.ClientError as exc:
        raise ModuleError(f'Gmail API request failed: {exc}')

    return {
        'ok': True,
        'data': {
            'messages': messages,
            'total': len(messages),
        },
    }
