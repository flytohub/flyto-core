"""
Microsoft Teams Notification Module
Send notifications to Microsoft Teams via incoming webhook.
"""
import logging
from typing import Any

import aiohttp

from ....base import BaseModule
from ....registry import register_module


logger = logging.getLogger(__name__)


@register_module(
    module_id='notification.teams.send_message',
    version='1.0.0',
    category='notification',
    tags=['notification', 'teams', 'microsoft', 'messaging', 'webhook'],
    label='Send Teams Message',
    label_key='modules.notification.teams.send_message.label',
    description='Send message to Microsoft Teams via incoming webhook',
    description_key='modules.notification.teams.send_message.description',
    icon='MessageSquare',
    color='#6264A7',

    # Connection types
    input_types=['text', 'json', 'any'],
    output_types=['api_response'],
    can_receive_from=['data.*', 'http.*', 'string.*', 'flow.*', 'start'],
    can_connect_to=['data.*', 'flow.*', 'notify.*', 'end'],

    # Phase 2: Execution settings
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['TEAMS_WEBHOOK_URL'],
    handles_sensitive_data=True,
    required_permissions=['network.access'],

    params_schema={
        'webhook_url': {
            'type': 'string',
            'label': 'Webhook URL',
            'description': 'Microsoft Teams incoming webhook URL',
            'description_key': 'modules.notification.teams.send_message.params.webhook_url.description',
            'placeholder': 'https://outlook.office.com/webhook/...',
            'required': True
        },
        'message': {
            'type': 'text',
            'label': 'Message',
            'description': 'The message text to send',
            'description_key': 'modules.notification.teams.send_message.params.message.description',
            'placeholder': 'Hello from Flyto!',
            'required': True
        },
        'title': {
            'type': 'string',
            'label': 'Title',
            'description': 'Message card title (optional)',
            'description_key': 'modules.notification.teams.send_message.params.title.description',
            'placeholder': 'Notification',
            'required': False
        },
        'color': {
            'type': 'string',
            'label': 'Theme Color',
            'description': 'Theme color hex code (optional)',
            'description_key': 'modules.notification.teams.send_message.params.color.description',
            'placeholder': '#6264A7',
            'required': False
        },
        'sections': {
            'type': 'array',
            'label': 'Sections',
            'description': 'Additional MessageCard sections (optional)',
            'description_key': 'modules.notification.teams.send_message.params.sections.description',
            'required': False
        }
    },
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether the operation succeeded'},
        'data': {'type': 'object', 'description': 'Response data with status and webhook_url'}
    },
    examples=[
        {
            'name': 'Simple notification',
            'params': {
                'webhook_url': 'https://outlook.office.com/webhook/...',
                'message': 'Deployment completed successfully!',
                'title': 'Deploy Status',
                'color': '#00FF00'
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
class TeamsSendMessageModule(BaseModule):
    """Send message to Microsoft Teams via incoming webhook"""

    module_name = "Send Teams Message"
    module_description = "Send message to Microsoft Teams channel via incoming webhook URL"

    def validate_params(self) -> None:
        if 'webhook_url' not in self.params or not self.params['webhook_url']:
            raise ValueError(
                "Missing required parameter: webhook_url. "
                "Get webhook URL from Teams channel -> Connectors -> Incoming Webhook"
            )

        if 'message' not in self.params or not self.params['message']:
            raise ValueError("Missing required parameter: message")

        self.webhook_url = self.params['webhook_url']
        self.message = self.params['message']
        self.title = self.params.get('title')
        self.color = self.params.get('color')
        self.sections = self.params.get('sections')

    async def execute(self) -> Any:
        # Build Teams MessageCard payload
        payload = {
            '@type': 'MessageCard',
            '@context': 'http://schema.org/extensions',
            'summary': self.title or self.message[:50],
            'text': self.message
        }

        if self.title:
            payload['title'] = self.title

        if self.color:
            # Strip '#' if present for themeColor
            payload['themeColor'] = self.color.lstrip('#')

        if self.sections:
            payload['sections'] = self.sections

        # Send to Teams webhook
        # SECURITY: Set timeout to prevent hanging API calls
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'}
            ) as response:
                if response.status == 200:
                    return {
                        'ok': True,
                        'data': {
                            'status': 'sent',
                            'webhook_url': self.webhook_url
                        }
                    }
                else:
                    error_text = await response.text()
                    return {
                        'ok': False,
                        'data': {
                            'status': 'error',
                            'message': f'Failed to send message: HTTP {response.status} - {error_text}'
                        }
                    }
