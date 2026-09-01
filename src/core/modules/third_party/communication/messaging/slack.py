# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Slack Notification Module
Send notifications to Slack via webhook.

HOW FAR THIS MODULE FOLLOWS REALITY: accepted on the happy path, and two
different off-ladder answers on the ones that are not.

An incoming webhook answers 200 (body ``ok``) when Slack has taken the message
and posted it to the channel behind the URL. That is Slack reporting on its own
work, read off the reply to the request this module just sent, which is the
definition of ACCEPTED. It is worth attaching because the alternative was
DISPATCHED -- what the engine stamps on a module that reports nothing -- and
"nobody confirmed anything" is untrue of a call that came back 200.

It is not OBSERVED. Nothing here re-reads the channel with
`conversations.history`, and a posted message is not a read one: no person has
seen anything and the rung must not imply one has.

THE ERROR PATHS MATTER MORE HERE THAN THE HAPPY ONE, because this module does
not raise on them. It returns ``{'status': 'error', 'sent': False, ...}`` with
no ``ok`` key, which ``_execute_single_mode`` passes straight through, so a 404
from a revoked webhook is recorded as a step that SUCCEEDED. The envelope is the
only field on that payload that disagrees, and it splits three ways:

    4xx        Slack read the request and rejected it by name -- ``no_service``
               for a revoked webhook, ``channel_is_archived``,
               ``invalid_payload``. Nothing was posted and nothing is in doubt:
               FAILED.
    5xx        Slack broke with a POST it had already taken off the wire. The
               message may be in the channel. INDETERMINATE -- and this is the
               one that matters, because `retryable=True, max_retries=3` means a
               retry after a 500 can post the same message twice.
    guard trip during the request
               `guarded_aiohttp_request` re-runs the SSRF guard on every
               redirect hop, so an SSRFError from inside it means the POST left
               and a server answered with a 30x. INDETERMINATE.

The pre-flight guard is the one definite refusal: `enforce_outbound_url` runs
before a socket is opened, so nothing left this process -- FAILED.
"""
import logging
import os
from typing import Any, Dict

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


def _accepted(status: int, channel: Any) -> Dict[str, Any]:
    """ACCEPTED -- Slack answered 200 for this message and nothing more is known."""
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[
            {
                'kind': 'webhook_accepted_by_slack',
                'status': status,
                'channel': channel,
                'measured_by': 'response.status -- the status line of the reply to this POST',
                'detail': (
                    'Slack answered 200, which is Slack saying it took the '
                    'message and posted it. That is its report of its own work: '
                    'the channel is not read back anywhere in this module.'
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
    """The off-ladder answer for a post that did not come back 200.

    FAILED for a 4xx -- Slack named a reason and posted nothing, which is
    definite. INDETERMINATE for anything else, above all a 5xx: Slack broke with
    the request already in its hands, so the message may be in the channel, and
    saying FAILED there would tell a person nothing was posted when something
    may have been -- after which the automatic retry posts it again.
    """
    definite = 400 <= status < 500
    return envelope(
        Outcome.FAILED if definite else Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'webhook_refused_by_slack' if definite else 'webhook_answer_inconclusive',
            'status': status,
            'response': body[:500],
            'measured_by': 'response.status, against the 200 this module accepts',
            'detail': (
                'Slack answered and named a reason; nothing was posted.'
                if definite else
                'Slack did not answer 200, and the request was already in its '
                'hands. Whether the message reached the channel is not knowable '
                'from here.'
            ),
        }],
    )


def _blocked(reason: str, *, before_request: bool) -> Dict[str, Any]:
    """The SSRF guard tripping -- two different facts under one exception type.

    Before the request nothing left this process, so the refusal is total:
    FAILED. From inside `guarded_aiohttp_request` the POST already went out and
    a server answered with a redirect the guard would not follow, so what that
    server did with the body first is unknown: INDETERMINATE.
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
    can_receive_from=['data.*', 'http.*', 'string.*', 'utility.*', 'flow.*'],
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
            'placeholder': 'Hello from Flyto2!',
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
            'placeholder': 'Flyto2 Bot',
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
                'description_key': 'modules.notification.slack.send_message.output.message.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this post was followed: "accepted" when Slack answered '
                '200, "failed" when it refused with a 4xx or the SSRF guard '
                'stopped the request, "indeterminate" when it broke with the '
                'request already in its hands'
            ),
            'description_key': 'modules.notification.slack.send_message.output.outcome.description'}
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
        try:
            async with guarded_client_session() as session:
                response = await guarded_aiohttp_request(
                    session,
                    'POST',
                    self.webhook_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                )
                try:
                    if response.status == 200:
                        return {
                            'status': 'success',
                            'sent': True,
                            'message': 'Message sent to Slack successfully',
                            'outcome': _accepted(response.status, self.channel),
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
