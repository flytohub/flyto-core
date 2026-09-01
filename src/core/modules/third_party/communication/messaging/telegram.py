# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Telegram Notification Module
Send notifications via Telegram Bot API.

HOW FAR THIS MODULE FOLLOWS REALITY: accepted, and it will not go higher.

`sendMessage` answers ``{"ok": true, "result": {"message_id": N, ...}}`` when
Telegram has created the message in the chat. That is a real answer from the
other side, with a server-assigned id in it -- far more than DISPATCHED, which
is what the engine stamps on a module that reports nothing -- and it is exactly
ACCEPTED: the peer acknowledged taking it.

It is tempting to call a message_id an observation, and it is not one. It is
Telegram reporting on Telegram's own work, in the reply to the request this
module just sent. Nothing here calls `getUpdates`, re-reads the chat, or looks
at anything except the answer to its own POST. Above all, nobody has READ the
message: a chat_id that is a dead channel, a bot removed from a group, a user
who has muted it -- none of those is visible from a message_id, and this rung
does not pretend otherwise.

THE ERROR PATH IS THE OTHER HALF and it does not raise: an ``ok: false`` reply
returns ``{'status': 'error', 'sent': False, ...}`` with no ``ok`` key, which
``_execute_single_mode`` passes straight through, so "chat not found" is
recorded as a step that SUCCEEDED. The envelope is the only field that
disagrees, and it splits on Telegram's own ``error_code``:

    4xx    Telegram read the request and refused it by name -- 400 chat not
           found, 403 bot was blocked, 429 too many requests. Nothing was sent
           and nothing is in doubt: FAILED.
    5xx    Telegram broke with the request already in its hands. The message
           may exist in the chat. INDETERMINATE -- and `retryable=True,
           max_retries=3` means a retry after one can post it twice.

WHAT CARRIES NOTHING: a transport failure. There is no HTTP status check at
all, so a non-JSON error page makes `response.json()` raise, and the 30s client
timeout raises `asyncio.TimeoutError`; both escape uncaught and become a
StepExecutionError with the payload discarded. A timed-out send is the textbook
INDETERMINATE and it cannot be reported from here without changing this
module's error semantics, which is not a declaration's business.
"""
import logging
import os
from typing import Any, Dict

import aiohttp

from ....base import BaseModule
from ....registry import register_module
from .....constants import EnvVars
from .....engine.outcome import ClaimBy, Outcome, envelope


logger = logging.getLogger(__name__)


def _accepted(message_id: Any, chat_id: Any) -> Dict[str, Any]:
    """ACCEPTED -- Telegram acknowledged the message and assigned it an id."""
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[
            {
                'kind': 'message_accepted_by_telegram',
                'message_id': message_id,
                'chat_id': chat_id,
                'measured_by': "the ok:true reply to this sendMessage, and the message_id in it",
                'detail': (
                    'Telegram acknowledged the message and gave it an id. That '
                    "is the service's report of its own work: nothing here "
                    're-reads the chat.'
                ),
            },
            {
                'kind': 'nobody_has_read_it',
                'chat_id': chat_id,
                'measured_by': None,
                'detail': (
                    'A message id says the message exists, not that a person '
                    'saw it. A muted chat, a bot removed from a group and a '
                    'dead channel all look identical from here.'
                ),
            },
        ],
    )


def _refused(error_code: Any, description: str) -> Dict[str, Any]:
    """The off-ladder answer for ``ok: false``, split on Telegram's error_code.

    FAILED where Telegram named a reason in the 4xx range: it read the request,
    refused it, and created nothing. INDETERMINATE for a 5xx, or for a reply
    with no usable code at all -- Telegram broke with the request already in
    its hands, so the message may be in the chat, and saying FAILED there would
    tell a person nothing was sent when something may have been.
    """
    definite = isinstance(error_code, int) and 400 <= error_code < 500
    return envelope(
        Outcome.FAILED if definite else Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'message_refused_by_telegram' if definite else 'telegram_answer_inconclusive',
            'error_code': error_code,
            'description': description,
            'measured_by': "the ok:false reply to this sendMessage, and its error_code",
            'detail': (
                'Telegram answered and named a reason; no message was created.'
                if definite else
                'Telegram did not accept the message and did not name a client '
                'error for it. The request was already in its hands, so whether '
                'anything reached the chat is not knowable from here.'
            ),
        }],
    )


@register_module(
    module_id='notification.telegram.send_message',
    version='1.0.0',
    category='notification',
    tags=['notification', 'telegram', 'bot', 'messaging', 'ssrf_protected'],
    label='Send Telegram Message',
    label_key='modules.notification.telegram.send_message.label',
    description='Send message via Telegram Bot API',
    description_key='modules.notification.telegram.send_message.description',
    icon='Send',
    color='#0088CC',

    # Connection types
    input_types=['text', 'json', 'any'],
    output_types=['api_response'],
    can_receive_from=['data.*', 'http.*', 'string.*', 'flow.*', 'start'],
    can_connect_to=['data.*', 'flow.*', 'notify.*', 'end'],

    # Phase 2: Execution settings
    timeout_ms=30000,  # API calls should complete within 30s
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple messages can be sent in parallel

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['TELEGRAM_BOT_TOKEN'],
    handles_sensitive_data=True,  # Messages may contain sensitive info
    required_permissions=['network.access'],

    params_schema={
        'bot_token': {
            'type': 'string',
            'label': 'Bot Token',
            'description': 'Telegram bot token (from env.TELEGRAM_BOT_TOKEN or direct input)',
                'description_key': 'modules.notification.telegram.send_message.params.bot_token.description',
            'placeholder': '${env.TELEGRAM_BOT_TOKEN}',
            'required': False
        },
        'chat_id': {
            'type': 'string',
            'label': 'Chat ID',
            'description': 'Telegram chat ID or channel username',
                'description_key': 'modules.notification.telegram.send_message.params.chat_id.description',
            'placeholder': '@channel or 123456789',
            'required': True
        },
        'text': {
            'type': 'string',
            'label': 'Message Text',
            'description': 'The message to send',
                'description_key': 'modules.notification.telegram.send_message.params.text.description',
            'placeholder': 'Hello from Flyto2!',
            'required': True
        },
        'parse_mode': {
            'type': 'select',
            'label': 'Parse Mode',
            'description': 'Message formatting mode',
                'description_key': 'modules.notification.telegram.send_message.params.parse_mode.description',
            'options': ['Markdown', 'HTML', 'None'],
            'default': 'Markdown',
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.notification.telegram.send_message.output.status.description'},
        'sent': {'type': 'boolean', 'description': 'Whether notification was sent',
                'description_key': 'modules.notification.telegram.send_message.output.sent.description'},
        'message_id': {'type': 'number', 'description': 'Message identifier',
                'description_key': 'modules.notification.telegram.send_message.output.message_id.description'},
        'message': {'type': 'string', 'description': 'Result message describing the outcome',
                'description_key': 'modules.notification.telegram.send_message.output.message.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this send was followed: "accepted" when Telegram '
                'acknowledged the message and assigned it an id, "failed" when '
                'it refused with a 4xx error_code, "indeterminate" when it '
                'broke with the request already in its hands. Never higher than '
                'accepted -- nobody has read anything'
            ),
            'description_key': 'modules.notification.telegram.send_message.output.outcome.description'}
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

    def validate_params(self) -> None:
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
                        'message': 'Message sent to Telegram successfully',
                        'outcome': _accepted(
                            (data.get('result') or {}).get('message_id'),
                            self.chat_id,
                        ),
                    }
                else:
                    description = data.get('description', 'Unknown error')
                    return {
                        'status': 'error',
                        'sent': False,
                        'message': f"Failed to send message: {description}",
                        'outcome': _refused(data.get('error_code'), description),
                    }
