"""
Discord Notification Module
Send notifications to Discord via webhook.
"""
import logging
import os
from typing import Any

import aiohttp

from ....base import BaseModule
from ....registry import register_module
from .....constants import EnvVars


logger = logging.getLogger(__name__)


@register_module(
    module_id='notification.discord.send_message',
    version='1.0.0',
    category='notification',
    tags=['notification', 'discord', 'webhook', 'messaging'],
    label='Send Discord Message',
    label_key='modules.notification.discord.send_message.label',
    description='Send message to Discord via webhook',
    description_key='modules.notification.discord.send_message.description',
    icon='MessageSquare',
    color='#5865F2',

    # Connection types
    input_types=['text', 'json', 'any'],
    output_types=['api_response'],
    can_receive_from=['data.*', 'api.*', 'string.*'],

    # Phase 2: Execution settings
    timeout=30,  # API calls should complete within 30s
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple messages can be sent in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs DISCORD_WEBHOOK_URL
    handles_sensitive_data=True,  # Messages may contain sensitive info
    required_permissions=['network.access'],

    params_schema={
        'webhook_url': {
            'type': 'string',
            'label': 'Webhook URL',
            'description': 'Discord webhook URL (from env.DISCORD_WEBHOOK_URL or direct input)',
            'placeholder': '${env.DISCORD_WEBHOOK_URL}',
            'required': False
        },
        'content': {
            'type': 'string',
            'label': 'Message Content',
            'description': 'The message to send',
            'placeholder': 'Hello from Flyto2!',
            'required': True
        },
        'username': {
            'type': 'string',
            'label': 'Username',
            'description': 'Override bot username (optional)',
            'placeholder': 'Flyto2 Bot',
            'required': False
        },
        'avatar_url': {
            'type': 'string',
            'label': 'Avatar URL',
            'description': 'Bot avatar image URL (optional)',
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'sent': {'type': 'boolean'},
        'message': {'type': 'string'}
    },
    examples=[
        {
            'name': 'Simple message',
            'params': {
                'content': 'Workflow completed successfully!'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class DiscordSendMessageModule(BaseModule):
    """Send message to Discord via webhook"""

    module_name = "Send Discord Message"
    module_description = "Send message to Discord channel via webhook URL"

    def validate_params(self):
        if 'content' not in self.params or not self.params['content']:
            raise ValueError("Missing required parameter: content")

        self.content = self.params['content']

        # Get webhook URL from params or environment
        self.webhook_url = self.params.get('webhook_url') or os.getenv(EnvVars.DISCORD_WEBHOOK_URL)

        if not self.webhook_url:
            raise ValueError(
                f"Discord webhook URL not found. "
                f"Please set {EnvVars.DISCORD_WEBHOOK_URL} environment variable or provide webhook_url parameter. "
                f"Get webhook URL from Discord Server Settings -> Integrations -> Webhooks"
            )

        self.username = self.params.get('username')
        self.avatar_url = self.params.get('avatar_url')

    async def execute(self) -> Any:
        # Build Discord message payload
        payload = {
            'content': self.content
        }

        if self.username:
            payload['username'] = self.username
        if self.avatar_url:
            payload['avatar_url'] = self.avatar_url

        # Send to Discord webhook
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'}
            ) as response:
                if response.status in [200, 204]:
                    return {
                        'status': 'success',
                        'sent': True,
                        'message': 'Message sent to Discord successfully'
                    }
                else:
                    error_text = await response.text()
                    return {
                        'status': 'error',
                        'sent': False,
                        'message': f'Failed to send message: {error_text}'
                    }
