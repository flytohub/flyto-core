# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Discord Notification Module
Send notifications to Discord via webhook.

HOW FAR THIS MODULE FOLLOWS REALITY: accepted on the happy path, and two
different off-ladder answers on the ones that are not.

A Discord webhook answers 204 No Content when it has taken the message and
posted it (200 with the message object instead, when the URL carries
``?wait=true``). Either way that is Discord reporting on its own work, read off
the reply to the request this module just sent, which is exactly ACCEPTED.
Attaching it is not a formality: the alternative was DISPATCHED -- what the
engine stamps on a module that reports nothing -- and "the instruction left us
and nobody confirmed anything" is untrue of a call that came back 204.

It is not OBSERVED. Nothing here re-reads the channel, and a posted message is
not a read one: no person has seen anything, and the rung must not imply one
has.

THE ERROR PATHS MATTER MORE HERE THAN THE HAPPY ONE, because this module does
not raise on them. It returns ``{'status': 'error', 'sent': False, ...}`` with
no ``ok`` key, which ``_execute_single_mode`` passes straight through, so a 404
from a deleted webhook is recorded as a step that SUCCEEDED. The envelope is the
only field on that payload that disagrees, and it splits three ways:

    4xx        Discord read the request and rejected it by name -- a deleted
               webhook, a malformed body, a rate limit. Nothing was posted, and
               nothing is left in doubt: FAILED.
    5xx        Discord broke while handling a POST it had already taken off the
               wire. The message may be in the channel. INDETERMINATE, and this
               is why it matters: `retryable=True, max_retries=3` means a retry
               after a 500 can post the same message twice.
    guard trip during the request
               `guarded_aiohttp_request` re-runs the SSRF guard on each redirect
               hop, so an SSRFError raised from inside it means the POST already
               left and a server answered it with a 30x. Whether anything was
               posted before the hop is not knowable here: INDETERMINATE.

The pre-flight guard is the one definite refusal: `enforce_outbound_url` runs
before any socket is opened, so that path is FAILED -- nothing left this
process.
"""
import logging
import os
from typing import Any, Dict

import aiohttp

from .....constants import EnvVars
from .....engine.outcome import ClaimBy, Outcome, envelope
from .....utils import (
    SSRFError,
    enforce_outbound_url,
    guarded_aiohttp_request,
    guarded_client_session,
)
from ....base import BaseModule
from ....registry import register_module

logger = logging.getLogger(__name__)


def _accepted(status: int) -> Dict[str, Any]:
    """ACCEPTED -- Discord answered with a success code for this message.

    The measurement is one status line off the reply to this request. 204 is
    the ordinary answer for a webhook post; 200 comes back when the URL carries
    ``?wait=true`` and Discord returns the message it created. Neither is a
    read of the channel, and neither is a person seeing anything.
    """
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[
            {
                'kind': 'webhook_accepted_by_discord',
                'status': status,
                'measured_by': 'response.status -- the status line of the reply to this POST',
                'detail': (
                    'Discord answered with a success code, which is Discord '
                    'saying it took the message and posted it. That is its '
                    'report of its own work: the channel is not read back.'
                ),
            },
            {
                'kind': 'nobody_has_read_it',
                'measured_by': None,
                'detail': (
                    'A posted message is not a read one. Nothing here observes '
                    'a person seeing it, and this rung does not imply one did.'
                ),
            },
        ],
    )


def _refused(status: int, body: str) -> Dict[str, Any]:
    """The off-ladder answer for a webhook post that did not come back 2xx.

    The split is the retry question, and getting it wrong is expensive in both
    directions. A 4xx is Discord naming a reason and posting nothing -- definite,
    so FAILED, and safe to retry only after the reason is fixed. A 5xx is
    Discord breaking with the request already in its hands, so the message may
    be in the channel; calling that FAILED would tell a person nothing was
    posted when something may have been, and the automatic retry would then post
    it a second time.
    """
    definite = 400 <= status < 500
    return envelope(
        Outcome.FAILED if definite else Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'webhook_refused_by_discord' if definite else 'webhook_answer_inconclusive',
            'status': status,
            'response': body[:500],
            'measured_by': 'response.status, against the 200/204 this module accepts',
            'detail': (
                'Discord answered and named a reason; nothing was posted.'
                if definite else
                'Discord did not answer with a success code, and the request was '
                'already in its hands. Whether the message reached the channel '
                'is not knowable from here.'
            ),
        }],
    )


def _blocked(reason: str, *, before_request: bool) -> Dict[str, Any]:
    """The SSRF guard tripping, which is two different facts under one exception.

    Before the request, nothing left this process and the refusal is total:
    FAILED. From inside `guarded_aiohttp_request`, the POST already went out and
    a server answered it with a redirect the guard would not follow -- so what
    that server did with the body first is unknown: INDETERMINATE.
    """
    return envelope(
        Outcome.FAILED if before_request else Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'blocked_by_ssrf_guard',
            'reason': reason,
            'measured_by': (
                'enforce_outbound_url, before any socket was opened'
                if before_request else
                'the SSRF guard re-run on a redirect hop, inside guarded_aiohttp_request'
            ),
            'detail': (
                'The request was refused before it left this process. Nothing '
                'was sent anywhere.'
                if before_request else
                'The POST left and a server answered it with a redirect into '
                'blocked space. What that server did with the body before '
                'redirecting is not knowable here.'
            ),
        }],
    )


@register_module(
    module_id='notification.discord.send_message',
    version='1.0.0',
    category='notification',
    tags=['notification', 'discord', 'webhook', 'messaging', 'ssrf_protected'],
    label='Send Discord Message',
    label_key='modules.notification.discord.send_message.label',
    description='Send message to Discord via webhook',
    description_key='modules.notification.discord.send_message.description',
    icon='MessageSquare',
    color='#5865F2',

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
    credential_keys=['DISCORD_WEBHOOK_URL'],
    handles_sensitive_data=True,  # Messages may contain sensitive info
    required_permissions=['network.access'],

    params_schema={
        'webhook_url': {
            'type': 'string',
            'label': 'Webhook URL',
            'description': 'Discord webhook URL (from env.DISCORD_WEBHOOK_URL or direct input)',
                'description_key': 'modules.notification.discord.send_message.params.webhook_url.description',
            'placeholder': '${env.DISCORD_WEBHOOK_URL}',
            'required': False
        },
        'content': {
            'type': 'string',
            'label': 'Message Content',
            'description': 'The message to send',
                'description_key': 'modules.notification.discord.send_message.params.content.description',
            'placeholder': 'Hello from Flyto2!',
            'required': True
        },
        'username': {
            'type': 'string',
            'label': 'Username',
            'description': 'Override bot username (optional)',
                'description_key': 'modules.notification.discord.send_message.params.username.description',
            'placeholder': 'Flyto2 Bot',
            'required': False
        },
        'avatar_url': {
            'type': 'string',
            'label': 'Avatar URL',
            'description': 'Bot avatar image URL (optional)',
                'description_key': 'modules.notification.discord.send_message.params.avatar_url.description',
            'required': False
        ,
            'placeholder': 'https://example.com',
}
    },
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.notification.discord.send_message.output.status.description'},
        'sent': {'type': 'boolean', 'description': 'Whether notification was sent',
                'description_key': 'modules.notification.discord.send_message.output.sent.description'},
        'message': {'type': 'string', 'description': 'Result message describing the outcome',
                'description_key': 'modules.notification.discord.send_message.output.message.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this post was followed: "accepted" when Discord '
                'answered 200/204, "failed" when it refused with a 4xx or the '
                'SSRF guard stopped the request, "indeterminate" when it broke '
                'with the request already in its hands'
            ),
            'description_key': 'modules.notification.discord.send_message.output.outcome.description'}
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

    def validate_params(self) -> None:
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
        # SECURITY: gate the client-controlled webhook URL through the SSRF guard
        # (GHSA-pgwh-4jj4-qm8v) — prevents posting to internal/metadata endpoints.
        try:
            enforce_outbound_url(self.webhook_url)
        except SSRFError as e:
            return {
                'status': 'error',
                'sent': False,
                'message': f'SSRF protection blocked request: {e}',
                'error_code': 'SSRF_BLOCKED',
                'outcome': _blocked(str(e), before_request=True),
            }

        # Build Discord message payload
        payload = {
            'content': self.content
        }

        if self.username:
            payload['username'] = self.username
        if self.avatar_url:
            payload['avatar_url'] = self.avatar_url

        # Send to Discord webhook
        # SECURITY: Set timeout to prevent hanging API calls
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        try:
            async with guarded_client_session(timeout=timeout) as session:
                response = await guarded_aiohttp_request(
                    session,
                    'POST',
                    self.webhook_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                )
                try:
                    if response.status in [200, 204]:
                        return {
                            'status': 'success',
                            'sent': True,
                            'message': 'Message sent to Discord successfully',
                            'outcome': _accepted(response.status),
                        }
                    error_text = await response.text()
                    return {
                        'status': 'error',
                        'sent': False,
                        'message': f'Failed to send message: {error_text}',
                        'outcome': _refused(response.status, error_text),
                    }
                finally:
                    response.release()
        except SSRFError as e:
            # Reachable only from inside `guarded_aiohttp_request`: the initial
            # URL already passed `enforce_outbound_url` above, so the guard that
            # trips here is the one re-run on a redirect hop -- the POST left.
            return {
                'status': 'error',
                'sent': False,
                'message': f'SSRF protection blocked request: {e}',
                'error_code': 'SSRF_BLOCKED',
                'outcome': _blocked(str(e), before_request=False),
            }
