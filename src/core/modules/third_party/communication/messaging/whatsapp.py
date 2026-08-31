# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
WhatsApp Business API Module
Send messages via WhatsApp Business API (Meta Cloud API).

HOW FAR THIS MODULE FOLLOWS REALITY: accepted, and it will not go higher.

A 200 from ``/{phone_number_id}/messages`` carrying ``messages: [{"id":
"wamid..."}]`` is Meta saying it has taken the message and queued it for
delivery. A server-assigned id in the reply to this very request is a real
answer from the other side -- much more than DISPATCHED, which is what the
engine stamps on a module that reports nothing -- and it is the definition of
ACCEPTED: the peer acknowledged taking it.

DELIVERY IS SOMEWHERE ELSE ENTIRELY, and on this API that is not a technicality.
The Cloud API reports delivery asynchronously, through webhook status callbacks
(``sent`` -> ``delivered`` -> ``read``) that arrive later at a different
endpoint. None of them is visible here. Worse, a message Meta accepts can be
returned with ``message_status: held_for_quality_assessment`` -- taken, given an
id, and deliberately not delivered. That field is recorded in the envelope when
Meta sends it, because a consumer reading ``status: 'sent'`` beside a held
message has been told the opposite of what happened.

WHEN NO ID COMES BACK the claim is thinner and says so: a 2xx whose body
carries no ``messages`` array leaves only the status line, and the effect names
that instead of implying an id existed.

THE ERROR PATH returns ``ok: False``, which makes `wrap_legacy_result` build an
ERROR result and drop ``data`` on the way out of the step -- so the envelope
there will not reach a consumer today. It is attached anyway, for the reason
`dns.lookup` gives for the same shape: the fact is true whether or not a
consumer exists yet. It splits on the status: a 4xx is Meta refusing by name and
sending nothing, which is FAILED; anything else broke with the request already
in Meta's hands, which is INDETERMINATE, and `retryable=True, max_retries=3`
makes that distinction the difference between one message and two.
"""
import logging
from typing import Any, Dict

import aiohttp

from ....base import BaseModule
from ....registry import register_module
from .....engine.outcome import ClaimBy, Outcome, envelope


logger = logging.getLogger(__name__)


def _accepted(status: int, message_id: str, message_status: Any, to: str) -> Dict[str, Any]:
    """ACCEPTED -- Meta took the message. Delivery happens elsewhere, later.

    Two shapes of the same rung. With an id, the evidence is the id Meta
    assigned; without one, it is only the status line, and the effect says which
    of the two this was rather than letting a reader assume the stronger one.
    """
    if message_id:
        taken = {
            'kind': 'message_accepted_by_whatsapp',
            'status': status,
            'message_id': message_id,
            'measured_by': 'the wamid Meta returned in messages[0].id, on a 2xx reply',
            'detail': (
                'Meta acknowledged the message and assigned it an id. That is '
                "the service's report of its own work; nothing is read back."
            ),
        }
    else:
        taken = {
            'kind': 'message_accepted_without_id',
            'status': status,
            'measured_by': 'response.status alone -- the reply carried no messages[] array',
            'detail': (
                'Meta answered with a success code and no message id. The claim '
                'rests on the status line only, which is weaker than the usual '
                'path and is recorded as such rather than assumed away.'
            ),
        }

    effects = [taken]

    if message_status:
        effects.append({
            'kind': 'whatsapp_message_status',
            'message_status': message_status,
            'measured_by': 'messages[0].message_status in the reply',
            'detail': (
                'Meta reported this status for the message it took. '
                "'held_for_quality_assessment' means accepted and deliberately "
                'NOT delivered -- the payload still reports status "sent".'
            ),
        })

    effects.append({
        'kind': 'delivery_not_observed',
        'to': to,
        'measured_by': None,
        'detail': (
            'The Cloud API reports delivery asynchronously through webhook '
            'status callbacks (sent -> delivered -> read) that arrive later at '
            'a different endpoint. Nothing here sees any of them.'
        ),
    })

    return envelope(Outcome.ACCEPTED, claim_by=ClaimBy.NONE, effects=effects)


def _refused(status: int, body: str) -> Dict[str, Any]:
    """The off-ladder answer for a reply that was not a 2xx.

    FAILED for a 4xx: Meta read the request, rejected it by name -- an expired
    token, a number not on WhatsApp, a template that does not exist -- and sent
    nothing. INDETERMINATE otherwise: a 5xx broke with the request already
    taken, so the message may be on its way, and calling that FAILED would tell
    a person nothing was sent when something may have been.
    """
    definite = 400 <= status < 500
    return envelope(
        Outcome.FAILED if definite else Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'message_refused_by_whatsapp' if definite else 'whatsapp_answer_inconclusive',
            'status': status,
            'response': body[:500],
            'measured_by': 'response.status, against the 200/201 this module accepts',
            'detail': (
                'Meta answered and named a reason; no message was created.'
                if definite else
                'Meta did not answer with a success code, and the request was '
                'already in its hands. Whether anything was queued for delivery '
                'is not knowable from here.'
            ),
        }],
    )


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
            'placeholder': 'Hello from Flyto2!',
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
        'data': {
            'type': 'object',
            'description': (
                'Response data with status, message_id, to, and outcome. '
                '`status` reads "sent" for every accepted message, including '
                'one Meta is holding undelivered; `outcome` carries what Meta '
                'actually said'
            )
        }
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
    author='Flyto2 Team',
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
                    message_status = None
                    messages = data.get('messages', [])
                    if messages:
                        message_id = messages[0].get('id', '')
                        # Meta sends this when it has taken a message and is NOT
                        # delivering it. Read here so the envelope can say so;
                        # `status` below stays 'sent' either way.
                        message_status = messages[0].get('message_status')

                    return {
                        'ok': True,
                        'data': {
                            'status': 'sent',
                            'message_id': message_id,
                            'to': self.to,
                            'outcome': _accepted(
                                response.status, message_id, message_status, self.to
                            ),
                        }
                    }
                else:
                    error_text = await response.text()
                    return {
                        'ok': False,
                        'data': {
                            'status': 'error',
                            'message': f'Failed to send message: HTTP {response.status} - {error_text}',
                            'outcome': _refused(response.status, error_text),
                        }
                    }
