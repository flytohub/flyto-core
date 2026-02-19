# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
WhatsApp Business API Module
Send messages via WhatsApp Business API (Meta Cloud API).
"""
import logging
from typing import Any

import aiohttp

from ....base import BaseModule
from ....registry import register_module


logger = logging.getLogger(__name__)


@register_module(
    module_id='notification.whatsapp.send_message',
    version='1.0.0',
    category='notification',
    tags=['notification', 'whatsapp', 'messaging', 'meta'],
    label='Send WhatsApp Message',
    label_key='modules.notification.whatsapp.send_message.label',
    description='Send message via WhatsApp Business API (Meta Cloud API)',
    description_key='modules.notification.whatsapp.send_message.description',
    icon='MessageCircle',
    color='#25D366',

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
    credential_keys=['WHATSAPP_ACCESS_TOKEN'],
    handles_sensitive_data=True,
    required_permissions=['network.access'],

    params_schema={
        'phone_number_id': {
            'type': 'string',
            'label': 'Phone Number ID',
            'description': 'WhatsApp Business sender phone number ID',
            'description_key': 'modules.notification.whatsapp.send_message.params.phone_number_id.description',
            'placeholder': '1234567890',
            'required': True
        },
        'to': {
            'type': 'string',
            'label': 'Recipient',
            'description': 'Recipient phone number with country code',
            'description_key': 'modules.notification.whatsapp.send_message.params.to.description',
            'placeholder': '+1234567890',
            'required': True
        },
        'message': {
            'type': 'text',
            'label': 'Message',
            'description': 'The message text to send',
            'description_key': 'modules.notification.whatsapp.send_message.params.message.description',
            'placeholder': 'Hello from Flyto!',
            'required': True
        },
        'access_token': {
            'type': 'password',
            'label': 'Access Token',
            'description': 'Meta access token for WhatsApp Business API',
            'description_key': 'modules.notification.whatsapp.send_message.params.access_token.description',
            'placeholder': '${env.WHATSAPP_ACCESS_TOKEN}',
            'required': True,
            'sensitive': True
        },
        'message_type': {
            'type': 'select',
            'label': 'Message Type',
            'description': 'Type of message to send',
            'description_key': 'modules.notification.whatsapp.send_message.params.message_type.description',
            'options': [
                {'label': 'Text', 'value': 'text'},
                {'label': 'Template', 'value': 'template'}
            ],
            'required': False,
            'default': 'text'
        },
        'template_name': {
            'type': 'string',
            'label': 'Template Name',
            'description': 'WhatsApp message template name (required if message_type is "template")',
            'description_key': 'modules.notification.whatsapp.send_message.params.template_name.description',
            'placeholder': 'hello_world',
            'required': False
        },
        'template_language': {
            'type': 'string',
            'label': 'Template Language',
            'description': 'Template language code',
            'description_key': 'modules.notification.whatsapp.send_message.params.template_language.description',
            'placeholder': 'en',
            'required': False,
            'default': 'en'
        }
    },
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether the operation succeeded'},
        'data': {'type': 'object', 'description': 'Response data with status, message_id, and to'}
    },
    examples=[
        {
            'name': 'Send text message',
            'params': {
                'phone_number_id': '1234567890',
                'to': '+1987654321',
                'message': 'Your order has been shipped!',
                'access_token': 'EAAx...'
            }
        },
        {
            'name': 'Send template message',
            'params': {
                'phone_number_id': '1234567890',
                'to': '+1987654321',
                'message': '',
                'access_token': 'EAAx...',
                'message_type': 'template',
                'template_name': 'hello_world',
                'template_language': 'en'
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
class WhatsAppSendMessageModule(BaseModule):
    """Send message via WhatsApp Business API"""

    module_name = "Send WhatsApp Message"
    module_description = "Send message via WhatsApp Business API (Meta Cloud API)"

    WHATSAPP_API_BASE = "https://graph.facebook.com/v18.0"

    def validate_params(self) -> None:
        required = ['phone_number_id', 'to', 'access_token']
        for param in required:
            if param not in self.params or not self.params[param]:
                raise ValueError(f"Missing required parameter: {param}")

        self.phone_number_id = self.params['phone_number_id']
        self.to = self.params['to']
        self.message = self.params.get('message', '')
        self.access_token = self.params['access_token']
        self.message_type = self.params.get('message_type', 'text')
        self.template_name = self.params.get('template_name')
        self.template_language = self.params.get('template_language', 'en')

        if self.message_type == 'text' and not self.message:
            raise ValueError("Missing required parameter: message (required for text message type)")

        if self.message_type == 'template' and not self.template_name:
            raise ValueError("Missing required parameter: template_name (required for template message type)")

    async def execute(self) -> Any:
        url = f"{self.WHATSAPP_API_BASE}/{self.phone_number_id}/messages"

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

        # Build payload based on message type
        if self.message_type == 'template':
            payload = {
                'messaging_product': 'whatsapp',
                'to': self.to,
                'type': 'template',
                'template': {
                    'name': self.template_name,
                    'language': {
                        'code': self.template_language
                    }
                }
            }
        else:
            payload = {
                'messaging_product': 'whatsapp',
                'to': self.to,
                'type': 'text',
                'text': {
                    'body': self.message
                }
            }

        # SECURITY: Set timeout to prevent hanging API calls
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status in [200, 201]:
                    data = await response.json()

                    # Extract message ID from response
                    message_id = ''
                    messages = data.get('messages', [])
                    if messages:
                        message_id = messages[0].get('id', '')

                    return {
                        'ok': True,
                        'data': {
                            'status': 'sent',
                            'message_id': message_id,
                            'to': self.to
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
