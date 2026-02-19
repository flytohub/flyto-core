# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Google Calendar Create Event Module
Create a new event in Google Calendar using the Calendar API with OAuth2 and aiohttp.
"""

import logging
from typing import Any, Dict, List

from ....registry import register_module
from ....schema import compose
from ....schema.builders import field
from ....schema.constants import FieldGroup
from ....errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)

CALENDAR_EVENTS_URL = 'https://www.googleapis.com/calendar/v3/calendars/primary/events'


@register_module(
    module_id='google.calendar.create_event',
    version='1.0.0',
    category='cloud',
    tags=['cloud', 'google', 'calendar', 'event', 'create', 'schedule'],
    label='Calendar Create Event',
    label_key='modules.google.calendar.create_event.label',
    description='Create a new event in Google Calendar',
    description_key='modules.google.calendar.create_event.description',
    icon='Calendar',
    color='#4285F4',
    input_types=['object', 'string'],
    output_types=['object'],
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
              description='Google OAuth2 access token with Calendar write scope',
              format='password'),
        field('summary', type='string', label='Event Title', required=True,
              group=FieldGroup.BASIC,
              description='Title of the calendar event',
              placeholder='Team Meeting'),
        field('start_time', type='string', label='Start Time', required=True,
              group=FieldGroup.BASIC,
              description='Event start time in ISO 8601 format',
              placeholder='2026-03-01T10:00:00'),
        field('end_time', type='string', label='End Time', required=True,
              group=FieldGroup.BASIC,
              description='Event end time in ISO 8601 format',
              placeholder='2026-03-01T11:00:00'),
        field('description', type='string', label='Description',
              group=FieldGroup.OPTIONS,
              description='Detailed description of the event',
              placeholder='Discuss project milestones', format='multiline'),
        field('location', type='string', label='Location',
              group=FieldGroup.OPTIONS,
              description='Event location or meeting link',
              placeholder='Conference Room A'),
        field('attendees', type='string', label='Attendees',
              group=FieldGroup.OPTIONS,
              description='Comma-separated list of attendee email addresses',
              placeholder='alice@example.com, bob@example.com'),
        field('timezone', type='string', label='Timezone',
              group=FieldGroup.OPTIONS,
              description='Timezone for the event (IANA timezone)',
              default='UTC', placeholder='America/New_York'),
    ),
    output_schema={
        'event_id': {'type': 'string', 'description': 'Created event ID', 'description_key': 'modules.google.calendar.create_event.output.event_id.description'},
        'summary': {'type': 'string', 'description': 'Event title', 'description_key': 'modules.google.calendar.create_event.output.summary.description'},
        'start': {'type': 'string', 'description': 'Event start time', 'description_key': 'modules.google.calendar.create_event.output.start.description'},
        'end': {'type': 'string', 'description': 'Event end time', 'description_key': 'modules.google.calendar.create_event.output.end.description'},
        'html_link': {'type': 'string', 'description': 'Link to view the event in Google Calendar', 'description_key': 'modules.google.calendar.create_event.output.html_link.description'},
    },
    examples=[
        {
            'title': 'Create a meeting event',
            'params': {
                'access_token': '<oauth2-token>',
                'summary': 'Sprint Planning',
                'start_time': '2026-03-01T10:00:00',
                'end_time': '2026-03-01T11:00:00',
                'attendees': 'alice@example.com, bob@example.com',
                'timezone': 'America/New_York',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def google_calendar_create_event(context: Dict[str, Any]) -> Dict[str, Any]:
    """Create a Google Calendar event."""
    params = context.get('params', {})

    access_token = params.get('access_token')
    summary = params.get('summary')
    start_time = params.get('start_time')
    end_time = params.get('end_time')

    if not access_token:
        raise ValidationError('Access token is required', field='access_token')
    if not summary:
        raise ValidationError('Event title (summary) is required', field='summary')
    if not start_time:
        raise ValidationError('Start time is required', field='start_time')
    if not end_time:
        raise ValidationError('End time is required', field='end_time')

    description = params.get('description', '')
    location = params.get('location', '')
    attendees_str = params.get('attendees', '')
    timezone = params.get('timezone', 'UTC')

    # Build attendee list from comma-separated string
    attendee_list: List[Dict[str, str]] = []
    if attendees_str:
        for email in attendees_str.split(','):
            email = email.strip()
            if email:
                attendee_list.append({'email': email})

    # Build event payload
    event_body: Dict[str, Any] = {
        'summary': summary,
        'start': {
            'dateTime': start_time,
            'timeZone': timezone,
        },
        'end': {
            'dateTime': end_time,
            'timeZone': timezone,
        },
    }
    if description:
        event_body['description'] = description
    if location:
        event_body['location'] = location
    if attendee_list:
        event_body['attendees'] = attendee_list

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

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                CALENDAR_EVENTS_URL,
                json=event_body,
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

    # Extract start/end from response
    start_info = resp_data.get('start', {})
    end_info = resp_data.get('end', {})
    result_start = start_info.get('dateTime', start_info.get('date', ''))
    result_end = end_info.get('dateTime', end_info.get('date', ''))

    return {
        'ok': True,
        'data': {
            'event_id': resp_data.get('id', ''),
            'summary': resp_data.get('summary', ''),
            'start': result_start,
            'end': result_end,
            'html_link': resp_data.get('htmlLink', ''),
        },
    }
