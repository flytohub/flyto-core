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
              placeholder='ya29.a0AfH6SM...', format='password'),
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
    if not access_token:
        raise ValidationError('Access token is required', field='access_token')
    if not params.get('summary'):
        raise ValidationError('Event title (summary) is required', field='summary')
    if not params.get('start_time'):
        raise ValidationError('Start time is required', field='start_time')
    if not params.get('end_time'):
        raise ValidationError('End time is required', field='end_time')

    event_body = _build_event_body(params)
    resp_data = await _post_calendar_event(access_token, event_body)

    start_info = resp_data.get('start', {})
    end_info = resp_data.get('end', {})
    return {
        'ok': True,
        'data': {
            'event_id': resp_data.get('id', ''),
            'summary': resp_data.get('summary', ''),
            'start': start_info.get('dateTime', start_info.get('date', '')),
            'end': end_info.get('dateTime', end_info.get('date', '')),
            'html_link': resp_data.get('htmlLink', ''),
        },
    }


def _build_event_body(params: Dict[str, Any]) -> Dict[str, Any]:
    """Build Google Calendar event JSON body."""
    timezone = params.get('timezone', 'UTC')
    body: Dict[str, Any] = {
        'summary': params['summary'],
        'start': {'dateTime': params['start_time'], 'timeZone': timezone},
        'end': {'dateTime': params['end_time'], 'timeZone': timezone},
    }
    if params.get('description'):
        body['description'] = params['description']
    if params.get('location'):
        body['location'] = params['location']
    attendees_str = params.get('attendees', '')
    if attendees_str:
        body['attendees'] = [
            {'email': e.strip()} for e in attendees_str.split(',') if e.strip()
        ]
    return body


async def _post_calendar_event(access_token: str, event_body: Dict[str, Any]) -> Dict[str, Any]:
    """POST event to Google Calendar API."""
    try:
        import aiohttp
    except ImportError:
        raise ModuleError('aiohttp package is required. Install with: pip install aiohttp')

    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                CALENDAR_EVENTS_URL, json=event_body,
                headers=headers, timeout=aiohttp.ClientTimeout(total=25),
            ) as resp:
                resp_data = await resp.json()
                if resp.status != 200:
                    error_msg = resp_data.get('error', {}).get('message', str(resp_data))
                    raise ModuleError(f'Google Calendar API error (HTTP {resp.status}): {error_msg}')
                return resp_data
    except aiohttp.ClientError as exc:
        raise ModuleError(f'Google Calendar API request failed: {exc}')
