"""
Telegram Notification Module
Send notifications via Telegram Bot API.
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
    can_receive_from=['data.*', 'api.*', 'string.*', 'flow.*', 'start'],
    can_connect_to=['data.*', 'flow.*', 'notification.*', 'end'],

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

        # Send message with timeout
        # SECURITY: Set timeout to prevent hanging API calls
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
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
