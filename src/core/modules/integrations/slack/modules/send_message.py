# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Slack Send Message Module

Send a message to a Slack channel.

HOW FAR THE SEND IS FOLLOWED

ACCEPTED. `chat.postMessage` answers with a `ts` -- the message timestamp Slack
assigned -- and the resolved channel id. Neither is producible from this
module's inputs: a caller who passed `#general` gets `C…` back, so the reply is
more than an echo. That is what puts this above DISPATCHED, and no further:
Slack is reporting on its own work, nothing reads the channel back, and no
human is confirmed to have seen anything. Delivery to a person is not on this
ladder at all.

SLACK'S STATUS LINE IS NOT ITS ANSWER, which is why the failure branch reads
two things. `{"ok": false, "error": "invalid_auth"}` arrives as HTTP 200;
`SlackIntegration._response_is_ok` already reads the body flag, so
`response.ok` is the honest field and `response.status` alone would call a
rejected token a successful send. The envelope carries both.

THE ERROR PATH splits on whether a message may have been posted:

    a named refusal (body ok:false, or a 4xx)   FAILED. Slack read the request,
                                                rejected it, and posted nothing.
    a 5xx, or no reply at all                   INDETERMINATE. The message may
                                                be in the channel.

That second case is the one to take seriously here, because this module sets
`retryable=True, max_retries=3` AND `BaseIntegration._request` retries on its
own. A timeout on a POST Slack had already accepted can therefore post the same
message several times, and nothing in the payload would show it. FAILED would
be the comfortable answer and the wrong one.
"""

import os
from typing import Any, Dict

from ....base import BaseModule
from ....registry import register_module
from ...outcomes import mutation_unconfirmed, peer_answered
from ..integration import SlackIntegration
from .....engine.outcome import ClaimBy, Outcome, envelope


@register_module(
    module_id="integration.slack.send_message",
    can_connect_to=['*'],
    can_receive_from=['*'],
    version="1.0.0",
    category="integration",
    tags=["integration", "slack", "messaging", "notification", "ssrf_protected"],
    label="Send Slack Message",
    label_key="modules.integration.slack.send_message.label",
    description="Send a message to a Slack channel",
    description_key="modules.integration.slack.send_message.description",
    icon="MessageSquare",
    color="#4A154B",
    input_types=["any"],
    output_types=["any"],
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=['SLACK_BOT_TOKEN'],
    required_permissions=["network.access"],
    params_schema={
        "channel": {
            "type": "string",
            "label": "Channel",
            "description": "Channel ID or name (e.g., #general or C1234567890)",
                "description_key": "modules.integration.slack.send_message.params.channel.description",
            "placeholder": "#general",
            "required": True,
        },
        "text": {
            "type": "text",
            "label": "Message",
            "description": "Message text (supports Slack markdown)",
                "description_key": "modules.integration.slack.send_message.params.text.description",
            "placeholder": "Hello from Flyto2!",
            "required": True,
        },
        "thread_ts": {
            "type": "string",
            "label": "Thread Timestamp",
            "description": "Reply to thread (optional)",
                "description_key": "modules.integration.slack.send_message.params.thread_ts.description",
            "required": False,
        },
        "token": {
            "type": "string",
            "label": "Bot Token",
            "description": "Slack Bot Token (xoxb-...)",
                "description_key": "modules.integration.slack.send_message.params.token.description",
            "placeholder": "${env.SLACK_BOT_TOKEN}",
            "required": False,
            "sensitive": True,
        },
    },
    output_schema={
        "ok": {"type": "boolean", "description": "Whether the operation was successful"},
        "channel": {"type": "string", "description": "Channel where message was sent"},
        "ts": {"type": "string", "description": "Message timestamp, assigned by Slack"},
        "message": {"type": "object", "description": "Full message object"},
        "outcome": {
            "type": "object",
            "description": (
                'How far the send was followed: "accepted" when Slack answered '
                'with a ts it assigned, "failed" when Slack named a refusal '
                '(including an HTTP 200 carrying ok:false), "indeterminate" when a '
                '5xx or no reply left a message that may have posted. Never higher '
                '-- nothing reads the channel back and no delivery to a person is '
                'confirmed'
            ),
        },
    },
    examples=[
        {
            "name": "Send simple message",
            "params": {
                "channel": "#general",
                "text": "Hello team!",
            },
        },
        {
            "name": "Reply to thread",
            "params": {
                "channel": "C1234567890",
                "text": "Thanks for the update!",
                "thread_ts": "1234567890.123456",
            },
        },
    ],
    author="Flyto2 Team",
    license="MIT",
)
class SlackSendMessageModule(BaseModule):
    """Send Slack message module."""

    module_name = "Send Slack Message"
    module_description = "Send a message to a Slack channel"

    def validate_params(self) -> None:
        if not self.params.get("channel"):
            raise ValueError("Channel is required")
        if not self.params.get("text"):
            raise ValueError("Message text is required")

        self.channel = self.params["channel"]
        self.text = self.params["text"]
        self.thread_ts = self.params.get("thread_ts")
        self.token = self.params.get("token") or os.getenv("SLACK_BOT_TOKEN")

        if not self.token:
            raise ValueError("Slack bot token required. Set SLACK_BOT_TOKEN or provide token parameter.")

    async def execute(self) -> Dict[str, Any]:
        async with SlackIntegration(bot_token=self.token) as slack:
            response = await slack.send_message(
                channel=self.channel,
                text=self.text,
                thread_ts=self.thread_ts,
            )

            if response.ok:
                data = response.data
                return {
                    "ok": True,
                    "channel": data.get("channel"),
                    "ts": data.get("ts"),
                    "message": data.get("message"),
                    "outcome": envelope(
                        Outcome.ACCEPTED,
                        claim_by=ClaimBy.NONE,
                        effects=[
                            peer_answered("slack", response.status),
                            {
                                "kind": "message_reported_posted",
                                "ts": data.get("ts"),
                                "ts_reported": "ts" in data,
                                "channel_requested": self.channel,
                                "channel_resolved": data.get("channel"),
                                "thread_ts": self.thread_ts,
                                "measured_by": (
                                    "ts and channel in the chat.postMessage reply, "
                                    "and the ok flag in that same body"
                                ),
                                "detail": (
                                    "Slack asserting that it posted a message, and "
                                    "naming it. ts is server-assigned and "
                                    "channel_resolved is the channel id Slack "
                                    "resolved channel_requested to, so neither is an "
                                    "echo -- and both are still the peer reporting on "
                                    "its own work. Nothing reads the channel back. "
                                    "Nothing here says a person saw it: delivery to a "
                                    "human is not something this module can observe."
                                ),
                            },
                        ],
                    ),
                }
            else:
                return {
                    "ok": False,
                    "error": response.error,
                    "outcome": mutation_unconfirmed(
                        service="slack",
                        status=response.status,
                        operation="message_post",
                        error=response.error,
                        retry_note=(
                            "This module sets retryable=True and "
                            "BaseIntegration._request retries as well, so the same "
                            "message may have been posted more than once."
                        ),
                    ),
                }
