"""
Notification and Messaging Modules
Send notifications to Slack, Discord, Telegram, Email, etc.
"""
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict

import aiohttp

from ...base import BaseModule
from ...registry import register_module
from ....constants import EnvVars


logger = logging.getLogger(__name__)


@register_module(
    module_id='notification.slack.send_message',
    version='1.0.0',
    category='notification',
    tags=['notification', 'slack', 'webhook', 'messaging'],
    label='Send Slack Message',
    label_key='modules.notification.slack.send_message.label',
    description='Send message to Slack via webhook',
    description_key='modules.notification.slack.send_message.description',
    icon='MessageCircle',
    color='#4A154B',

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
    requires_credentials=True,  # Needs SLACK_WEBHOOK_URL
    handles_sensitive_data=True,  # Messages may contain sensitive info
    required_permissions=['network.access'],

    params_schema={
        'webhook_url': {
            'type': 'string',
            'label': 'Webhook URL',
            'description': 'Slack webhook URL (from env.SLACK_WEBHOOK_URL or direct input)',
            'placeholder': '${env.SLACK_WEBHOOK_URL}',
            'required': False
        },
        'text': {
            'type': 'string',
            'label': 'Message Text',
            'description': 'The message to send',
            'placeholder': 'Hello from Flyto2!',
            'required': True
        },
        'channel': {
            'type': 'string',
            'label': 'Channel',
            'description': 'Override default channel (optional)',
            'placeholder': '#general',
            'required': False
        },
        'username': {
            'type': 'string',
            'label': 'Username',
            'description': 'Override bot username (optional)',
            'placeholder': 'Flyto2 Bot',
            'required': False
        },
        'icon_emoji': {
            'type': 'string',
            'label': 'Icon Emoji',
            'description': 'Bot icon emoji (optional)',
            'placeholder': ':robot_face:',
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
    author='Flyto2 Team',
    license='MIT'
)
class SlackSendMessageModule(BaseModule):
    """Send message to Slack via webhook"""

    module_name = "Send Slack Message"
    module_description = "Send message to Slack channel via webhook URL"

    def validate_params(self):
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
                f"Get webhook URL from Discord Server Settings → Integrations → Webhooks"
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


@register_module(
    module_id='notification.telegram.send_message',
    version='1.0.0',
    category='notification',
    tags=['notification', 'telegram', 'bot', 'messaging'],
    label='Send Telegram Message',
    label_key='modules.notification.telegram.send_message.label',
    description='Send message via Telegram Bot API',
    description_key='modules.notification.telegram.send_message.description',
    icon='Send',
    color='#0088CC',

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
    requires_credentials=True,  # Needs TELEGRAM_BOT_TOKEN
    handles_sensitive_data=True,  # Messages may contain sensitive info
    required_permissions=['network.access'],

    params_schema={
        'bot_token': {
            'type': 'string',
            'label': 'Bot Token',
            'description': 'Telegram bot token (from env.TELEGRAM_BOT_TOKEN or direct input)',
            'placeholder': '${env.TELEGRAM_BOT_TOKEN}',
            'required': False
        },
        'chat_id': {
            'type': 'string',
            'label': 'Chat ID',
            'description': 'Telegram chat ID or channel username',
            'placeholder': '@channel or 123456789',
            'required': True
        },
        'text': {
            'type': 'string',
            'label': 'Message Text',
            'description': 'The message to send',
            'placeholder': 'Hello from Flyto2!',
            'required': True
        },
        'parse_mode': {
            'type': 'select',
            'label': 'Parse Mode',
            'description': 'Message formatting mode',
            'options': ['Markdown', 'HTML', 'None'],
            'default': 'Markdown',
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'sent': {'type': 'boolean'},
        'message_id': {'type': 'number'},
        'message': {'type': 'string'}
    },
    examples=[
        {
            'name': 'Simple message',
            'params': {
                'chat_id': '@mychannel',
                'text': 'Workflow completed!'
            }
        },
        {
            'name': 'Markdown formatted',
            'params': {
                'chat_id': '123456789',
                'text': '*Bold* _italic_ `code`',
                'parse_mode': 'Markdown'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class TelegramSendMessageModule(BaseModule):
    """Send message via Telegram Bot API"""

    module_name = "Send Telegram Message"
    module_description = "Send message to Telegram chat/channel via Bot API"

    def validate_params(self):
        if 'text' not in self.params or not self.params['text']:
            raise ValueError("Missing required parameter: text")
        if 'chat_id' not in self.params or not self.params['chat_id']:
            raise ValueError("Missing required parameter: chat_id")

        self.text = self.params['text']
        self.chat_id = self.params['chat_id']

        # Get bot token from params or environment
        self.bot_token = self.params.get('bot_token') or os.getenv(EnvVars.TELEGRAM_BOT_TOKEN)

        if not self.bot_token:
            raise ValueError(
                f"Telegram bot token not found. "
                f"Please set {EnvVars.TELEGRAM_BOT_TOKEN} environment variable or provide bot_token parameter. "
                f"Get token from: https://t.me/BotFather"
            )

        self.parse_mode = self.params.get('parse_mode', 'Markdown')
        if self.parse_mode == 'None':
            self.parse_mode = None

    async def execute(self) -> Any:
        # Build Telegram API URL
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

        # Build payload
        payload = {
            'chat_id': self.chat_id,
            'text': self.text
        }

        if self.parse_mode:
            payload['parse_mode'] = self.parse_mode

        # Send message
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                data = await response.json()

                if data.get('ok'):
                    return {
                        'status': 'success',
                        'sent': True,
                        'message_id': data['result']['message_id'],
                        'message': 'Message sent to Telegram successfully'
                    }
                else:
                    return {
                        'status': 'error',
                        'sent': False,
                        'message': f"Failed to send message: {data.get('description', 'Unknown error')}"
                    }


@register_module(
    module_id='notification.email.send',
    version='1.0.0',
    category='notification',
    tags=['notification', 'email', 'smtp', 'mail'],
    label='Send Email',
    label_key='modules.notification.email.send.label',
    description='Send email via SMTP',
    description_key='modules.notification.email.send.description',
    icon='Mail',
    color='#EA4335',

    # Connection types
    input_types=['text', 'json', 'any'],
    output_types=['api_response'],
    can_receive_from=['data.*', 'api.*', 'string.*'],

    # Phase 2: Execution settings
    timeout=30,  # SMTP operations should complete within 30s
    retryable=True,  # Network errors can be retried
    max_retries=2,
    concurrent_safe=True,  # Multiple emails can be sent in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs SMTP credentials
    handles_sensitive_data=True,  # Email content may be sensitive
    required_permissions=['network.access'],

    params_schema={
        'smtp_server': {
            'type': 'string',
            'label': 'SMTP Server',
            'description': 'SMTP server hostname (e.g., smtp.gmail.com)',
            'placeholder': '${env.SMTP_SERVER}',
            'required': True
        },
        'smtp_port': {
            'type': 'number',
            'label': 'SMTP Port',
            'description': 'SMTP port (587 for TLS, 465 for SSL)',
            'default': 587,
            'required': False
        },
        'username': {
            'type': 'string',
            'label': 'Username',
            'description': 'SMTP username',
            'placeholder': '${env.SMTP_USERNAME}',
            'required': True
        },
        'password': {
            'type': 'string',
            'label': 'Password',
            'description': 'SMTP password (use env variable!)',
            'placeholder': '${env.SMTP_PASSWORD}',
            'required': True,
            'sensitive': True
        },
        'from_email': {
            'type': 'string',
            'label': 'From Email',
            'description': 'Sender email address',
            'placeholder': 'bot@example.com',
            'required': True
        },
        'to_email': {
            'type': 'string',
            'label': 'To Email',
            'description': 'Recipient email address',
            'placeholder': 'user@example.com',
            'required': True
        },
        'subject': {
            'type': 'string',
            'label': 'Subject',
            'description': 'Email subject',
            'placeholder': 'Workflow Alert',
            'required': True
        },
        'body': {
            'type': 'text',
            'label': 'Body',
            'description': 'Email body (HTML supported)',
            'placeholder': 'Your workflow has completed.',
            'required': True
        },
        'html': {
            'type': 'boolean',
            'label': 'HTML Body',
            'description': 'Send body as HTML',
            'default': False,
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
            'name': 'Simple plain text email',
            'params': {
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 587,
                'from_email': 'bot@example.com',
                'to_email': 'user@example.com',
                'subject': 'Workflow Complete',
                'body': 'Your automation workflow has finished successfully.'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class EmailSendModule(BaseModule):
    """Send email via SMTP"""

    module_name = "Send Email"
    module_description = "Send email message via SMTP server"

    def validate_params(self):
        required = ['smtp_server', 'username', 'password', 'from_email', 'to_email', 'subject', 'body']
        for param in required:
            if param not in self.params or not self.params[param]:
                raise ValueError(f"Missing required parameter: {param}")

        self.smtp_server = self.params['smtp_server']
        self.smtp_port = self.params.get('smtp_port', 587)
        self.username = self.params['username']
        self.password = self.params['password']
        self.from_email = self.params['from_email']
        self.to_email = self.params['to_email']
        self.subject = self.params['subject']
        self.body = self.params['body']
        self.html = self.params.get('html', False)

    async def execute(self) -> Any:
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = self.to_email
            msg['Subject'] = self.subject

            # Attach body
            if self.html:
                msg.attach(MIMEText(self.body, 'html'))
            else:
                msg.attach(MIMEText(self.body, 'plain'))

            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            return {
                'status': 'success',
                'sent': True,
                'message': f'Email sent successfully to {self.to_email}'
            }

        except Exception as e:
            return {
                'status': 'error',
                'sent': False,
                'message': f'Failed to send email: {str(e)}'
            }
