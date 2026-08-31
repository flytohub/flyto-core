# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Slack List Channels Module

List channels in Slack workspace.

HOW FAR THE LIST IS FOLLOWED

ACCEPTED. Slack answered and handed back channel objects; nothing here reads
anything a second time, and for a listing there is nothing to read back -- the
reply is the whole of what happened.

`count` IS ONE PAGE, NOT THE WORKSPACE. `conversations.list` paginates with a
cursor in `response_metadata`, and this module neither sends one nor reads the
one it gets, so `count` is bounded by `limit` (default 100) and there is no
field anywhere in the payload that says whether more channels exist. A caller
comparing `count` against what they see in Slack will find them differ on any
workspace past the first page, and nothing in the result explains why. The
effect says so; the missing cursor is a gap in the module, reported alongside
this change.

An empty list stays ACCEPTED rather than dropping a rung. ACCEPTED claims only
that the peer answered, which is true, and it claims nothing about the data --
so there is nothing for zero channels to make untrue. `sheets_read` settles the
same question the same way.

THE ERROR PATH IS FAILED, including a body-level `{"ok": false}` at HTTP 200,
which `SlackIntegration._response_is_ok` already folds into `response.ok`. A
listing that Slack refused returned nothing and altered nothing.
"""

import os
from typing import Any, Dict

from ....base import BaseModule
from ....registry import register_module
from ...outcomes import peer_answered, read_refused
from ..integration import SlackIntegration
from .....engine.outcome import ClaimBy, Outcome, envelope


@register_module(
    module_id="integration.slack.list_channels",
    can_connect_to=['*'],
    can_receive_from=['*'],
    version="1.0.0",
    category="integration",
    tags=["integration", "slack", "channels", "ssrf_protected"],
    label="List Slack Channels",
    label_key="modules.integration.slack.list_channels.label",
    description="List channels in Slack workspace",
    description_key="modules.integration.slack.list_channels.description",
    icon="Hash",
    color="#4A154B",
    input_types=["any"],
    output_types=["any"],
    timeout_ms=30000,
    retryable=True,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=['SLACK_BOT_TOKEN'],
    params_schema={
        "types": {
            "type": "string",
            "label": "Channel Types",
            "description": "Types of channels to list",
            "description_key": "modules.integration.slack.list_channels.params.types.description",
            "placeholder": "public_channel,private_channel",
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
        "ok": {"type": "boolean", "description": "Whether the operation was successful"},
        "channels": {"type": "array", "description": "One page of channels, bounded by limit"},
        "count": {
            "type": "number",
            "description": (
                "Channels returned on this page. Not the number in the workspace -- "
                "no pagination cursor is followed"
            ),
        },
        "outcome": {
            "type": "object",
            "description": (
                'How far the listing was followed: "accepted" when Slack answered, '
                '"failed" when it did not. Never higher -- one request, its reply, '
                'and nothing read back'
            ),
        },
    },
    author="Flyto2 Team",
    license="MIT",
)
class SlackListChannelsModule(BaseModule):
    """List Slack channels module."""

    module_name = "List Slack Channels"
    module_description = "List channels in Slack workspace"

    def validate_params(self) -> None:
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
                    "outcome": envelope(
                        Outcome.ACCEPTED,
                        claim_by=ClaimBy.NONE,
                        effects=[
                            peer_answered("slack", response.status),
                            {
                                "kind": "channels_returned",
                                "count": len(channels),
                                "limit_requested": self.limit,
                                "types_requested": self.types,
                                # Slack sends a cursor when more pages exist.
                                # This module never asks for the next page, so
                                # the flag is recorded rather than acted on --
                                # a reader can at least see the list is partial.
                                "more_pages_available": bool(
                                    (response.data.get("response_metadata") or {}).get(
                                        "next_cursor"
                                    )
                                ),
                                "measured_by": (
                                    "len() over the channels array Slack returned, "
                                    "and response_metadata.next_cursor in that same "
                                    "body"
                                ),
                                "detail": (
                                    "count is ONE PAGE, bounded by limit. "
                                    "conversations.list paginates with a cursor this "
                                    "module never sends, so when more_pages_available "
                                    "is true the workspace holds channels that are "
                                    "not in this list. The channels themselves are "
                                    "Slack's report of its own workspace, read once."
                                ),
                            },
                        ],
                    ),
                }
            else:
                return {
                    "ok": False,
                    "error": response.error,
                    "outcome": read_refused(
                        service="slack",
                        status=response.status,
                        resource="channels",
                        error=response.error,
                    ),
                }
