"""
Twilio Communication Integration Modules

Provides SMS and voice call operations with Twilio.
"""
import logging
import os
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from ....constants import APIEndpoints, EnvVars


logger = logging.getLogger(__name__)


@register_module(
    module_id='communication.twilio.send_sms',
    version='1.0.0',
    category='notification',
    subcategory='sms',
    tags=['twilio', 'sms', 'message', 'phone'],
    label='Twilio Send SMS',
    label_key='modules.communication.twilio.send_sms.label',
    description='Send SMS message via Twilio',
    description_key='modules.communication.twilio.send_sms.description',
    icon='MessageSquare',
    color='#F22F46',

    # Connection types
    input_types=['text'],
    output_types=['json'],

    # Phase 2: Execution settings
    timeout=30,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.access', 'sms.send'],

    params_schema={
        'account_sid': {
            'type': 'string',
            'label': 'Account SID',
            'label_key': 'modules.communication.twilio.send_sms.params.account_sid.label',
            'description': 'Twilio Account SID (or use TWILIO_ACCOUNT_SID env)',
            'description_key': 'modules.communication.twilio.send_sms.params.account_sid.description',
            'required': False,
            'sensitive': True
        },
        'auth_token': {
            'type': 'string',
            'label': 'Auth Token',
            'label_key': 'modules.communication.twilio.send_sms.params.auth_token.label',
            'description': 'Twilio Auth Token (or use TWILIO_AUTH_TOKEN env)',
            'description_key': 'modules.communication.twilio.send_sms.params.auth_token.description',
            'required': False,
            'sensitive': True
        },
        'from_number': {
            'type': 'string',
            'label': 'From Number',
            'label_key': 'modules.communication.twilio.send_sms.params.from_number.label',
            'description': 'Twilio phone number (e.g. +1234567890)',
            'description_key': 'modules.communication.twilio.send_sms.params.from_number.description',
            'required': True
        },
        'to_number': {
            'type': 'string',
            'label': 'To Number',
            'label_key': 'modules.communication.twilio.send_sms.params.to_number.label',
            'description': 'Recipient phone number (e.g. +1234567890)',
            'description_key': 'modules.communication.twilio.send_sms.params.to_number.description',
            'required': True
        },
        'message': {
            'type': 'string',
            'label': 'Message',
            'label_key': 'modules.communication.twilio.send_sms.params.message.label',
            'description': 'SMS message text',
            'description_key': 'modules.communication.twilio.send_sms.params.message.description',
            'required': True,
            'multiline': True
        }
    },
    output_schema={
        'sid': {'type': 'string'},
        'status': {'type': 'string'},
        'to': {'type': 'string'},
        'from': {'type': 'string'}
    },
    examples=[
        {
            'title': 'Send notification SMS',
            'params': {
                'from_number': '+1234567890',
                'to_number': '+0987654321',
                'message': 'Your order has been shipped!'
            }
        },
        {
            'title': 'Send verification code',
            'params': {
                'from_number': '+1234567890',
                'to_number': '+0987654321',
                'message': 'Your verification code is: 123456'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class TwilioSendSMSModule(BaseModule):
    """Twilio Send SMS Module"""

    def validate_params(self):
        self.account_sid = self.params.get('account_sid')
        self.auth_token = self.params.get('auth_token')
        self.from_number = self.params.get('from_number')
        self.to_number = self.params.get('to_number')
        self.message = self.params.get('message')

        if not self.account_sid or not self.auth_token:
            self.account_sid = self.account_sid or os.environ.get(EnvVars.TWILIO_ACCOUNT_SID)
            self.auth_token = self.auth_token or os.environ.get(EnvVars.TWILIO_AUTH_TOKEN)

            if not self.account_sid or not self.auth_token:
                raise ValueError(f"account_sid/auth_token or {EnvVars.TWILIO_ACCOUNT_SID}/{EnvVars.TWILIO_AUTH_TOKEN} env required")

        if not self.from_number or not self.to_number or not self.message:
            raise ValueError("from_number, to_number, and message are required")

    async def execute(self) -> Any:
        try:
            import aiohttp
            import base64

            # Create basic auth header
            credentials = f"{self.account_sid}:{self.auth_token}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()

            # Build request
            url = APIEndpoints.twilio_messages(self.account_sid)

            data = {
                'From': self.from_number,
                'To': self.to_number,
                'Body': self.message
            }

            headers = {
                'Authorization': f'Basic {encoded_credentials}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=data) as response:
                    if response.status not in [200, 201]:
                        error_text = await response.text()
                        raise RuntimeError(f"Twilio API error ({response.status}): {error_text}")

                    result = await response.json()

                    return {
                        "sid": result['sid'],
                        "status": result['status'],
                        "to": result['to'],
                        "from": result['from']
                    }

        except Exception as e:
            raise RuntimeError(f"Twilio SMS error: {str(e)}")


@register_module(
    module_id='communication.twilio.make_call',
    version='1.0.0',
    category='notification',
    subcategory='voice',
    tags=['twilio', 'call', 'voice', 'phone'],
    label='Twilio Make Call',
    label_key='modules.communication.twilio.make_call.label',
    description='Make a voice call via Twilio',
    description_key='modules.communication.twilio.make_call.description',
    icon='Phone',
    color='#F22F46',

    # Connection types
    input_types=['text'],
    output_types=['json'],

    # Phase 2: Execution settings
    timeout=30,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.access', 'voice.call'],

    params_schema={
        'account_sid': {
            'type': 'string',
            'label': 'Account SID',
            'label_key': 'modules.communication.twilio.make_call.params.account_sid.label',
            'description': 'Twilio Account SID (or use TWILIO_ACCOUNT_SID env)',
            'description_key': 'modules.communication.twilio.make_call.params.account_sid.description',
            'required': False,
            'sensitive': True
        },
        'auth_token': {
            'type': 'string',
            'label': 'Auth Token',
            'label_key': 'modules.communication.twilio.make_call.params.auth_token.label',
            'description': 'Twilio Auth Token (or use TWILIO_AUTH_TOKEN env)',
            'description_key': 'modules.communication.twilio.make_call.params.auth_token.description',
            'required': False,
            'sensitive': True
        },
        'from_number': {
            'type': 'string',
            'label': 'From Number',
            'label_key': 'modules.communication.twilio.make_call.params.from_number.label',
            'description': 'Twilio phone number',
            'description_key': 'modules.communication.twilio.make_call.params.from_number.description',
            'required': True
        },
        'to_number': {
            'type': 'string',
            'label': 'To Number',
            'label_key': 'modules.communication.twilio.make_call.params.to_number.label',
            'description': 'Recipient phone number',
            'description_key': 'modules.communication.twilio.make_call.params.to_number.description',
            'required': True
        },
        'twiml_url': {
            'type': 'string',
            'label': 'TwiML URL',
            'label_key': 'modules.communication.twilio.make_call.params.twiml_url.label',
            'description': 'URL to TwiML instructions',
            'description_key': 'modules.communication.twilio.make_call.params.twiml_url.description',
            'required': True
        }
    },
    output_schema={
        'sid': {'type': 'string'},
        'status': {'type': 'string'},
        'to': {'type': 'string'},
        'from': {'type': 'string'}
    },
    examples=[
        {
            'title': 'Make automated call',
            'params': {
                'from_number': '+1234567890',
                'to_number': '+0987654321',
                'twiml_url': 'https://example.com/voice.xml'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class TwilioMakeCallModule(BaseModule):
    """Twilio Make Call Module"""

    def validate_params(self):
        self.account_sid = self.params.get('account_sid')
        self.auth_token = self.params.get('auth_token')
        self.from_number = self.params.get('from_number')
        self.to_number = self.params.get('to_number')
        self.twiml_url = self.params.get('twiml_url')

        if not self.account_sid or not self.auth_token:
            self.account_sid = self.account_sid or os.environ.get(EnvVars.TWILIO_ACCOUNT_SID)
            self.auth_token = self.auth_token or os.environ.get(EnvVars.TWILIO_AUTH_TOKEN)

            if not self.account_sid or not self.auth_token:
                raise ValueError(f"account_sid/auth_token or {EnvVars.TWILIO_ACCOUNT_SID}/{EnvVars.TWILIO_AUTH_TOKEN} env required")

        if not self.from_number or not self.to_number or not self.twiml_url:
            raise ValueError("from_number, to_number, and twiml_url are required")

    async def execute(self) -> Any:
        try:
            import aiohttp
            import base64

            # Create basic auth header
            credentials = f"{self.account_sid}:{self.auth_token}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()

            # Build request
            url = APIEndpoints.twilio_calls(self.account_sid)

            data = {
                'From': self.from_number,
                'To': self.to_number,
                'Url': self.twiml_url
            }

            headers = {
                'Authorization': f'Basic {encoded_credentials}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=data) as response:
                    if response.status not in [200, 201]:
                        error_text = await response.text()
                        raise RuntimeError(f"Twilio API error ({response.status}): {error_text}")

                    result = await response.json()

                    return {
                        "sid": result['sid'],
                        "status": result['status'],
                        "to": result['to'],
                        "from": result['from']
                    }

        except Exception as e:
            raise RuntimeError(f"Twilio call error: {str(e)}")
