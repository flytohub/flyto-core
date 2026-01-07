"""
Slack List Channels Module

List channels in Slack workspace.
"""

import os
from typing import Any, Dict

from ....base import BaseModule
from ....registry import register_module
from ..integration import SlackIntegration


@register_module(
    module_id="integration.slack.list_channels",
    can_connect_to=['*'],
    can_receive_from=['*'],
    version="1.0.0",
    category="integration",
    tags=["integration", "slack", "channels"],
    label="List Slack Channels",
    label_key="modules.integration.slack.list_channels.label",
    description="List channels in Slack workspace",
    description_key="modules.integration.slack.list_channels.description",
    icon="Hash",
    color="#4A154B",
    input_types=["any"],
    output_types=["any"],
    timeout=30,
    retryable=True,
    concurrent_safe=True,
    requires_credentials=True,
    params_schema={
        "types": {
            "type": "string",
            "label": "Channel Types",
            "description": "Types of channels to list",
                "description_key": "modules.integration.slack.list_channels.params.types.description",
            "default": "public_channel,private_channel",
            "required": False,
        },
        "limit": {
            "type": "number",
            "label": "Limit",
            "description": "Maximum channels to return",
                "description_key": "modules.integration.slack.list_channels.params.limit.description",
            "default": 100,
            "min": 1,
            "max": 1000,
            "required": False,
        },
        "token": {
            "type": "string",
            "label": "Bot Token",
            "placeholder": "${env.SLACK_BOT_TOKEN}",
            "required": False,
            "sensitive": True,
        },
    },
    output_schema={
        "ok": {"type": "boolean"},
        "channels": {"type": "array"},
        "count": {"type": "number"},
    },
    author="Flyto Team",
    license="MIT",
)
class SlackListChannelsModule(BaseModule):
    """List Slack channels module."""

    module_name = "List Slack Channels"
    module_description = "List channels in Slack workspace"

    def validate_params(self):
        self.types = self.params.get("types", "public_channel,private_channel")
        self.limit = self.params.get("limit", 100)
        self.token = self.params.get("token") or os.getenv("SLACK_BOT_TOKEN")

        if not self.token:
            raise ValueError("Slack bot token required")

    async def execute(self) -> Dict[str, Any]:
        async with SlackIntegration(bot_token=self.token) as slack:
            response = await slack.list_channels(
                types=self.types,
                limit=self.limit,
            )

            if response.ok:
                channels = response.data.get("channels", [])
                return {
                    "ok": True,
                    "channels": [
                        {
                            "id": ch.get("id"),
                            "name": ch.get("name"),
                            "is_private": ch.get("is_private"),
                            "num_members": ch.get("num_members"),
                        }
                        for ch in channels
                    ],
                    "count": len(channels),
                }
            else:
                return {
                    "ok": False,
                    "error": response.error,
                }
