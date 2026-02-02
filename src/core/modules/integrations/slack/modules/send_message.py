"""
Slack Send Message Module

Send a message to a Slack channel.
"""

import os
from typing import Any, Dict

from ....base import BaseModule
from ....registry import register_module
from ..integration import SlackIntegration


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
            "placeholder": "Hello from Flyto!",
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
        "ts": {"type": "string", "description": "Message timestamp"},
        "message": {"type": "object", "description": "Full message object"},
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
    author="Flyto Team",
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
                }
            else:
                return {
                    "ok": False,
                    "error": response.error,
                }
