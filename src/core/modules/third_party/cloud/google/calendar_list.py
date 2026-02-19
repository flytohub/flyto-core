# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Google Calendar List Events Module
List upcoming events from Google Calendar using the Calendar API with OAuth2 and aiohttp.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from ....registry import register_module
from ....schema import compose
from ....schema.builders import field
from ....schema.constants import FieldGroup
from ....errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)

CALENDAR_EVENTS_URL = 'https://www.googleapis.com/calendar/v3/calendars/primary/events'


@register_module(
    module_id='google.calendar.list_events',
    version='1.0.0',
    category='cloud',
    tags=['cloud', 'google', 'calendar', 'event', 'list', 'schedule'],
    label='Calendar List Events',
    label_key='modules.google.calendar.list_events.label',
    description='List upcoming events from Google Calendar',
    description_key='modules.google.calendar.list_events.description',
    icon='Calendar',
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
    handles_sensitive_data=False,
    required_permissions=['cloud.calendar'],
    params_schema=compose(
        field('access_token', type='string', label='Access Token', required=True,
              group=FieldGroup.CONNECTION,
              description='Google OAuth2 access token with Calendar read scope',
              format='password'),
        field('max_results', type='number', label='Max Results',
              group=FieldGroup.OPTIONS,
              description='Maximum number of events to return',
              default=10, min=1, max=250),
        field('time_min', type='string', label='Start After',
              group=FieldGroup.OPTIONS,
              description='Only return events starting after this time (ISO 8601). Defaults to now.',
              placeholder='2026-03-01T00:00:00Z'),
        field('time_max', type='string', label='Start Before',
              group=FieldGroup.OPTIONS,
              description='Only return events starting before this time (ISO 8601)',
              placeholder='2026-04-01T00:00:00Z'),
    ),
    output_schema={
        'events': {
            'type': 'array',
            'description': 'List of calendar events',
            'description_key': 'modules.google.calendar.list_events.output.events.description',
            'items': {
                'type': 'object',
                'properties': {
                    'id': {'type': 'string', 'description': 'Event ID'},
                    'summary': {'type': 'string', 'description': 'Event title'},
                    'start': {'type': 'string', 'description': 'Event start time'},
                    'end': {'type': 'string', 'description': 'Event end time'},
                    'location': {'type': 'string', 'description': 'Event location'},
                },
            },
        },
        'count': {'type': 'number', 'description': 'Number of events returned', 'description_key': 'modules.google.calendar.list_events.output.count.description'},
    },
    examples=[
        {
            'title': 'List next 5 events',
            'params': {
                'access_token': '<oauth2-token>',
                'max_results': 5,
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def google_calendar_list_events(context: Dict[str, Any]) -> Dict[str, Any]:
    """List upcoming Google Calendar events."""
    params = context.get('params', {})

    access_token = params.get('access_token')
    if not access_token:
        raise ValidationError('Access token is required', field='access_token')

    max_results = int(params.get('max_results', 10))
    time_min = params.get('time_min', '')
    time_max = params.get('time_max', '')

    # Default time_min to current UTC time if not provided
    if not time_min:
        time_min = datetime.now(timezone.utc).isoformat()

    try:
        import aiohttp
    except ImportError:
        raise ModuleError(
            'aiohttp package is required. Install with: pip install aiohttp'
        )

    headers = {
        'Authorization': f'Bearer {access_token}',
    }

    query_params: Dict[str, str] = {
        'maxResults': str(max_results),
        'timeMin': time_min,
        'singleEvents': 'true',
        'orderBy': 'startTime',
    }
    if time_max:
        query_params['timeMax'] = time_max

    events: List[Dict[str, Any]] = []

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                CALENDAR_EVENTS_URL,
                params=query_params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=25),
            ) as resp:
                resp_data = await resp.json()
                if resp.status != 200:
                    error_msg = resp_data.get('error', {}).get('message', str(resp_data))
                    raise ModuleError(
                        f'Google Calendar API error (HTTP {resp.status}): {error_msg}'
                    )
    except aiohttp.ClientError as exc:
        raise ModuleError(f'Google Calendar API request failed: {exc}')

    for item in resp_data.get('items', []):
        start_info = item.get('start', {})
        end_info = item.get('end', {})
        events.append({
            'id': item.get('id', ''),
            'summary': item.get('summary', ''),
            'start': start_info.get('dateTime', start_info.get('date', '')),
            'end': end_info.get('dateTime', end_info.get('date', '')),
            'location': item.get('location', ''),
        })

    return {
        'ok': True,
        'data': {
            'events': events,
            'count': len(events),
        },
    }
