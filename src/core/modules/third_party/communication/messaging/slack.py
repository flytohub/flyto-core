"""
Slack Notification Module
Send notifications to Slack via webhook.
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
    module_id='notification.slack.send_message',
    version='1.0.0',
    category='notification',
    tags=['notification', 'slack', 'webhook', 'messaging', 'ssrf_protected'],
    label='Send Slack Message',
    label_key='modules.notification.slack.send_message.label',
    description='Send message to Slack via webhook',
    description_key='modules.notification.slack.send_message.description',
    icon='MessageCircle',
    color='#4A154B',

    # Connection types
    input_types=['text', 'json', 'any'],
    output_types=['api_response'],
    can_receive_from=['data.*', 'api.*', 'string.*', 'utility.*', 'flow.*'],
    can_connect_to=['*'],  # Notifications can connect to any module (typically end of workflow or chain to other notifications)

    # Phase 2: Execution settings
    timeout_ms=30000,  # API calls should complete within 30s
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple messages can be sent in parallel

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['SLACK_TOKEN'],
    handles_sensitive_data=True,  # Messages may contain sensitive info
    required_permissions=['network.access'],

    params_schema={
        'webhook_url': {
            'type': 'string',
            'label': 'Webhook URL',
            'description': 'Slack webhook URL (from env.SLACK_WEBHOOK_URL or direct input)',
                'description_key': 'modules.notification.slack.send_message.params.webhook_url.description',
            'placeholder': '${env.SLACK_WEBHOOK_URL}',
            'required': False
        },
        'text': {
            'type': 'string',
            'label': 'Message Text',
            'description': 'The message to send',
                'description_key': 'modules.notification.slack.send_message.params.text.description',
            'placeholder': 'Hello from Flyto!',
            'required': True
        },
        'channel': {
            'type': 'string',
            'label': 'Channel',
            'description': 'Override default channel (optional)',
                'description_key': 'modules.notification.slack.send_message.params.channel.description',
            'placeholder': '#general',
            'required': False
        },
        'username': {
            'type': 'string',
            'label': 'Username',
            'description': 'Override bot username (optional)',
                'description_key': 'modules.notification.slack.send_message.params.username.description',
            'placeholder': 'Flyto Bot',
            'required': False
        },
        'icon_emoji': {
            'type': 'string',
            'label': 'Icon Emoji',
            'description': 'Bot icon emoji (optional)',
                'description_key': 'modules.notification.slack.send_message.params.icon_emoji.description',
            'placeholder': ':robot_face:',
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.notification.slack.send_message.output.status.description'},
        'sent': {'type': 'boolean', 'description': 'Whether notification was sent',
                'description_key': 'modules.notification.slack.send_message.output.sent.description'},
        'message': {'type': 'string', 'description': 'Result message describing the outcome',
                'description_key': 'modules.notification.slack.send_message.output.message.description'}
    },
    examples=[
        {
            'name': 'Simple message',
            'params': {
                'text': 'Workflow completed successfully!'
            }
        },
        {
            'name': 'Custom channel and icon',
            'params': {
                'text': 'Alert: New user registered!',
                'channel': '#alerts',
                'username': 'Alert Bot',
                'icon_emoji': ':warning:'
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
class SlackSendMessageModule(BaseModule):
    """Send message to Slack via webhook"""

    module_name = "Send Slack Message"
    module_description = "Send message to Slack channel via webhook URL"

    def validate_params(self) -> None:
        if 'text' not in self.params or not self.params['text']:
            raise ValueError("Missing required parameter: text")

        self.text = self.params['text']

        # Get webhook URL from params or environment
        self.webhook_url = self.params.get('webhook_url') or os.getenv(EnvVars.SLACK_WEBHOOK_URL)

        if not self.webhook_url:
            raise ValueError(
                f"Slack webhook URL not found. "
                f"Please set {EnvVars.SLACK_WEBHOOK_URL} environment variable or provide webhook_url parameter. "
                f"Get webhook URL from: https://api.slack.com/messaging/webhooks"
            )

        self.channel = self.params.get('channel')
        self.username = self.params.get('username')
        self.icon_emoji = self.params.get('icon_emoji')

    async def execute(self) -> Any:
        # Build Slack message payload
        payload = {
            'text': self.text
        }

        if self.channel:
            payload['channel'] = self.channel
        if self.username:
            payload['username'] = self.username
        if self.icon_emoji:
            payload['icon_emoji'] = self.icon_emoji

        # Send to Slack webhook
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'}
            ) as response:
                if response.status == 200:
                    return {
                        'status': 'success',
                        'sent': True,
                        'message': 'Message sent to Slack successfully'
                    }
                else:
                    error_text = await response.text()
                    return {
                        'status': 'error',
                        'sent': False,
                        'message': f'Failed to send message: {error_text}'
                    }
