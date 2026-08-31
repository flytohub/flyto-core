# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Slack Send Module
Send messages to Slack channels via webhook

HOW FAR THIS MODULE FOLLOWS REALITY: accepted, and it cannot go higher.

An incoming webhook answers 200 when Slack has taken the message and posted it
to the channel behind the URL. That is Slack reporting on Slack's own work --
one status line, read off the reply to the request this module just sent -- and
taking a peer's word for its own work is the definition of ACCEPTED. It is
worth attaching all the same, because the alternative was never OBSERVED: it was
DISPATCHED, which is what the engine stamps on a module that reports nothing,
and "the instruction left us and nobody confirmed anything" is untrue of a call
that came back 200.

OBSERVED would need a second call -- `conversations.history` on the channel,
finding the message -- and nothing here makes one. Nor is a posted message a
read one: nobody in that channel has seen anything, and the rung is not allowed
to imply they have.

VERIFIED is unreachable: no postcondition is declared and none is evaluated, so
`ceiling_for(None)` caps this at OBSERVED regardless.

THE ERROR PATHS CARRY NOTHING, and that is a real gap rather than a decision.
A non-200 raises RuntimeError and an SSRF-blocked URL raises ValueError; both
become a StepExecutionError with the payload discarded, so a 404 from a revoked
webhook and a timeout mid-POST -- the textbook INDETERMINATE, and one that
matters because `retryable=True, max_retries=3` can post the same message twice
-- reach a consumer as the same bare exception. Attaching an envelope there
means returning a payload instead of raising, which is a change to this
module's error semantics and not a declaration's business.
"""
import logging
import os
from typing import Any, Dict, List, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose, presets
from ....utils import guarded_client_session, enforce_outbound_url, SSRFError


logger = logging.getLogger(__name__)


@register_module(
    module_id='slack.send',
    stability="beta",
    version='1.0.0',
    category='communication',
    subcategory='slack',
    tags=['slack', 'message', 'send', 'notification', 'webhook', 'ssrf_protected'],
    label='Send Slack Message',
    label_key='modules.slack.send.label',
    description='Send messages to Slack channels via incoming webhook',
    description_key='modules.slack.send.description',
    icon='MessageSquare',
    color='#4A154B',

    input_types=['text', 'object'],
    output_types=['object'],
    can_connect_to=['notify.*', 'flow.*', 'data.*', 'string.*', 'object.*'],
    can_receive_from=['*'],

    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    requires_credentials=True,
    credential_keys=['API_KEY'],
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        presets.SLACK_MESSAGE(),
        presets.SLACK_WEBHOOK_URL(),
        presets.SLACK_CHANNEL(),
        presets.SLACK_USERNAME(),
        presets.SLACK_ICON_EMOJI(),
        presets.SLACK_BLOCKS(),
        presets.SLACK_ATTACHMENTS(),
    ),
    output_schema={
        'sent': {
            'type': 'boolean',
            'description': 'Whether message was sent successfully'
        ,
                'description_key': 'modules.slack.send.output.sent.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this post was followed into reality. Always "accepted": '
                'Slack answered 200 for the message it took. Nobody has read it, '
                'and the channel is not read back'
            )
        ,
                'description_key': 'modules.slack.send.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Send simple message',
            'title_key': 'modules.slack.send.examples.simple.title',
            'params': {
                'message': 'Hello from Flyto2!'
            }
        },
        {
            'title': 'Send with formatting',
            'title_key': 'modules.slack.send.examples.formatted.title',
            'params': {
                'message': 'Task completed successfully',
                'username': 'Flyto2 Bot',
                'icon_emoji': ':white_check_mark:'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def slack_send(context: Dict[str, Any]) -> Dict[str, Any]:
    """Send message to Slack via webhook"""
    try:
        import aiohttp
    except ImportError:
        raise ImportError("aiohttp is required for slack.send. Install with: pip install aiohttp")

    params = context['params']
    message = params['message']
    webhook_url = params.get('webhook_url') or os.getenv('SLACK_WEBHOOK_URL')
    channel = params.get('channel')
    username = params.get('username')
    icon_emoji = params.get('icon_emoji')
    blocks = params.get('blocks')
    attachments = params.get('attachments')

    if not webhook_url:
        raise ValueError("Slack webhook URL not configured. Set SLACK_WEBHOOK_URL env or provide webhook_url param")

    # SECURITY: gate the client-controlled webhook URL through the SSRF guard
    # (GHSA-pgwh-4jj4-qm8v) — prevents posting to internal/metadata endpoints.
    try:
        enforce_outbound_url(webhook_url)
    except SSRFError as e:
        raise ValueError(f"SSRF protection blocked request: {e}")

    payload = {'text': message}

    if channel:
        payload['channel'] = channel
    if username:
        payload['username'] = username
    if icon_emoji:
        payload['icon_emoji'] = icon_emoji
    if blocks:
        payload['blocks'] = blocks
    if attachments:
        payload['attachments'] = attachments

    async with guarded_client_session() as session:
        async with session.post(webhook_url, json=payload) as response:
            if response.status == 200:
                logger.info("Slack message sent successfully")
                return {
                    'ok': True,
                    'sent': True,
                    'outcome': envelope(
                        Outcome.ACCEPTED,
                        claim_by=ClaimBy.NONE,
                        effects=[
                            {
                                'kind': 'webhook_accepted_by_slack',
                                'status': response.status,
                                'channel': channel,
                                'measured_by': (
                                    'response.status -- the status line of the '
                                    'reply to this POST'
                                ),
                                'detail': (
                                    'Slack answered 200, which is Slack saying it '
                                    'took the message and posted it. That is its '
                                    'report of its own work: no channel is read '
                                    'back anywhere in this module.'
                                ),
                            },
                            {
                                'kind': 'nobody_has_read_it',
                                'measured_by': None,
                                'detail': (
                                    'A posted message is not a read one. Nothing '
                                    'here observes a person seeing it, and this '
                                    'rung does not imply one did.'
                                ),
                            },
                        ],
                    ),
                }
            else:
                text = await response.text()
                logger.error(f"Failed to send Slack message: {response.status} - {text}")
                raise RuntimeError(f"Slack API error: {response.status} - {text}")
