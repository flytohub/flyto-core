# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Twilio Communication Integration Modules

Provides SMS and voice call operations with Twilio.

HOW FAR THESE TWO MODULES FOLLOW REALITY: accepted, and Twilio says so itself.

A 201 from ``/Messages`` or ``/Calls`` comes back with a resource whose
``status`` field is ``queued`` (or ``accepted``, or ``initiated`` for a call).
Twilio is not reporting a delivered SMS or an answered phone -- it is reporting
that it has taken the request and put it in its own queue. That is the clearest
statement of ACCEPTED anywhere in this product: the peer acknowledged taking it,
in the peer's own vocabulary, and the vocabulary explicitly excludes the thing a
reader would otherwise assume.

So the `status` these modules return is worth reading twice. ``queued`` is not
``delivered``; ``initiated`` is not ``answered``. Twilio reports what actually
happened later, asynchronously, to a status-callback URL, and neither module
sets one or reads one. Nobody's phone has buzzed as far as this code knows.

OBSERVED would need a second request -- ``GET /Messages/{sid}`` and a check that
``status`` had moved to ``delivered`` -- and neither module makes one. Adding it
would change what these calls cost and how long they take, which is a change to
the modules and not to what they may report. VERIFIED is unreachable: no
postcondition is declared and none is evaluated.

WHAT CARRIES NOTHING: every failure. Both modules wrap their whole body in
``except Exception`` and re-raise as ``RuntimeError``, so a non-2xx, a timeout
and a `KeyError` from a reply missing ``sid`` all become a StepExecutionError
with the payload discarded. A timed-out POST is the textbook INDETERMINATE and
matters here more than most -- ``retryable=True`` with `max_retries` of 3 and 2
means a retried SMS is a second SMS, and a retried call is a second phone
ringing. Reporting it needs these modules to return a payload instead of
raising, which is a change to their error semantics and not a declaration's
business.
"""
import logging
import os
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from ....constants import APIEndpoints, EnvVars
from ....engine.outcome import ClaimBy, Outcome, envelope


logger = logging.getLogger(__name__)


def _twilio_accepted(*, kind: str, sid: str, status: str, to: str, http_status: int) -> Dict[str, Any]:
    """ACCEPTED -- Twilio queued it, and told us that is what it did.

    `kind` is 'message' or 'call'. The measurement is the resource Twilio
    returned in the reply to this POST: a server-assigned sid, and a lifecycle
    status of its own choosing. Both are Twilio reporting on Twilio's work.

    The second effect exists because the first one is so easy to over-read. A
    sid and a 201 look like proof something reached a person; what they prove is
    that Twilio has the request. Delivery and answer are reported later to a
    status callback that neither module sets.
    """
    arrival = (
        'A queued message is not a delivered one. Twilio reports delivery '
        'later to a status-callback URL, which this module does not set and '
        'does not read; no handset has been reached as far as this code knows.'
        if kind == 'message' else
        'A queued call is not an answered one. Twilio reports the call '
        'lifecycle later to a status-callback URL, which this module does not '
        'set and does not read; nobody has picked up as far as this code knows.'
    )
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[
            {
                'kind': f'{kind}_accepted_by_twilio',
                'sid': sid,
                'twilio_status': status,
                'http_status': http_status,
                'measured_by': (
                    f'the sid and status Twilio returned for this {kind}, on a '
                    f'{http_status} reply to this POST'
                ),
                'detail': (
                    "Twilio acknowledged the request and gave it a sid. The "
                    "status is Twilio's own word for how far it has got -- "
                    "'queued', 'accepted' and 'initiated' all mean it has the "
                    "request and has not finished with it."
                ),
            },
            {
                'kind': 'delivery_not_observed',
                'to': to,
                'measured_by': None,
                'detail': arrival,
            },
        ],
    )


@register_module(
    module_id='communication.twilio.send_sms',
    can_connect_to=['*'],
    can_receive_from=['*'],
    version='1.0.0',
    category='notification',
    subcategory='sms',
    tags=['twilio', 'sms', 'message', 'phone', 'ssrf_protected'],
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
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN'],
    handles_sensitive_data=True,
    required_permissions=['voice.call'],

    params_schema={
        'account_sid': {
            'type': 'string',
            'label': 'Account SID',
            'label_key': 'modules.communication.twilio.send_sms.params.account_sid.label',
            'description': 'Twilio Account SID (or use TWILIO_ACCOUNT_SID env)',
            'description_key': 'modules.communication.twilio.send_sms.params.account_sid.description',
            'required': False,
            'sensitive': True
        ,
            'placeholder': 'ACxxxxxxxx',
},
        'auth_token': {
            'type': 'string',
            'label': 'Auth Token',
            'label_key': 'modules.communication.twilio.send_sms.params.auth_token.label',
            'description': 'Twilio Auth Token (or use TWILIO_AUTH_TOKEN env)',
            'description_key': 'modules.communication.twilio.send_sms.params.auth_token.description',
            'required': False,
            'sensitive': True
        ,
            'placeholder': 'Bearer your-token',
},
        'from_number': {
            'type': 'string',
            'label': 'From Number',
            'label_key': 'modules.communication.twilio.send_sms.params.from_number.label',
            'description': 'Twilio phone number (e.g. +1234567890)',
            'description_key': 'modules.communication.twilio.send_sms.params.from_number.description',
            'required': True
        ,
            'placeholder': '+1234567890',
},
        'to_number': {
            'type': 'string',
            'label': 'To Number',
            'label_key': 'modules.communication.twilio.send_sms.params.to_number.label',
            'description': 'Recipient phone number (e.g. +1234567890)',
            'description_key': 'modules.communication.twilio.send_sms.params.to_number.description',
            'required': True
        ,
            'placeholder': '+1234567890',
},
        'message': {
            'type': 'string',
            'label': 'Message',
            'label_key': 'modules.communication.twilio.send_sms.params.message.label',
            'description': 'SMS message text',
            'description_key': 'modules.communication.twilio.send_sms.params.message.description',
            'required': True,
            'multiline': True
        ,
            'placeholder': 'Your message here',
}
    },
    output_schema={
        'sid': {'type': 'string', 'description': 'The sid',
                'description_key': 'modules.communication.twilio.send_sms.output.sid.description'},
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.communication.twilio.send_sms.output.status.description'},
        'to': {'type': 'string', 'description': 'The to',
                'description_key': 'modules.communication.twilio.send_sms.output.to.description'},
        'from': {'type': 'string', 'description': 'The from',
                'description_key': 'modules.communication.twilio.send_sms.output.from.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this send was followed into reality. Always '
                '"accepted": Twilio queued the message and assigned it a sid. '
                'Delivery to the handset is reported later to a status callback '
                'this module does not set'
            ),
            'description_key': 'modules.communication.twilio.send_sms.output.outcome.description'}
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

    def validate_params(self) -> None:
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
                        "from": result['from'],
                        "outcome": _twilio_accepted(
                            kind='message',
                            sid=result['sid'],
                            status=result['status'],
                            to=result['to'],
                            http_status=response.status,
                        ),
                    }

        except Exception as e:
            raise RuntimeError(f"Twilio SMS error: {str(e)}")


@register_module(
    module_id='communication.twilio.make_call',
    can_connect_to=['*'],
    can_receive_from=['*'],
    version='1.0.0',
    category='notification',
    subcategory='voice',
    tags=['twilio', 'call', 'voice', 'phone', 'ssrf_protected'],
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
    timeout_ms=30000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN'],
    handles_sensitive_data=True,
    required_permissions=['voice.call'],

    params_schema={
        'account_sid': {
            'type': 'string',
            'label': 'Account SID',
            'label_key': 'modules.communication.twilio.make_call.params.account_sid.label',
            'description': 'Twilio Account SID (or use TWILIO_ACCOUNT_SID env)',
            'description_key': 'modules.communication.twilio.make_call.params.account_sid.description',
            'placeholder': 'ACxxxxxxxx',
            'required': False,
            'sensitive': True
        },
        'auth_token': {
            'type': 'string',
            'label': 'Auth Token',
            'label_key': 'modules.communication.twilio.make_call.params.auth_token.label',
            'description': 'Twilio Auth Token (or use TWILIO_AUTH_TOKEN env)',
            'description_key': 'modules.communication.twilio.make_call.params.auth_token.description',
            'placeholder': 'your-token',
            'required': False,
            'sensitive': True
        },
        'from_number': {
            'type': 'string',
            'label': 'From Number',
            'label_key': 'modules.communication.twilio.make_call.params.from_number.label',
            'description': 'Twilio phone number',
            'description_key': 'modules.communication.twilio.make_call.params.from_number.description',
            'placeholder': '+1234567890',
            'required': True
        },
        'to_number': {
            'type': 'string',
            'label': 'To Number',
            'label_key': 'modules.communication.twilio.make_call.params.to_number.label',
            'description': 'Recipient phone number',
            'description_key': 'modules.communication.twilio.make_call.params.to_number.description',
            'placeholder': '+1234567890',
            'required': True
        },
        'twiml_url': {
            'type': 'string',
            'label': 'TwiML URL',
            'label_key': 'modules.communication.twilio.make_call.params.twiml_url.label',
            'description': 'URL to TwiML instructions',
            'description_key': 'modules.communication.twilio.make_call.params.twiml_url.description',
            'required': True
        ,
            'placeholder': 'https://example.com',
}
    },
    output_schema={
        'sid': {'type': 'string', 'description': 'The sid'},
        'status': {'type': 'string', 'description': 'Operation status (success/error)'},
        'to': {'type': 'string', 'description': 'The to'},
        'from': {'type': 'string', 'description': 'The from'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this call was followed into reality. Always '
                '"accepted": Twilio queued the call and assigned it a sid. '
                'Whether anyone answers is reported later to a status callback '
                'this module does not set'
            )}
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

    def validate_params(self) -> None:
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
                        "from": result['from'],
                        "outcome": _twilio_accepted(
                            kind='call',
                            sid=result['sid'],
                            status=result['status'],
                            to=result['to'],
                            http_status=response.status,
                        ),
                    }

        except Exception as e:
            raise RuntimeError(f"Twilio call error: {str(e)}")
