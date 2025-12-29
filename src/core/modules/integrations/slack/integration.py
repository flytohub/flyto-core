"""
Slack Integration

Core Slack API integration class.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from ..base import BaseIntegration, IntegrationConfig, APIResponse

logger = logging.getLogger(__name__)


class SlackIntegration(BaseIntegration):
    """
    Slack API integration.

    Usage:
        async with SlackIntegration(access_token="xoxb-...") as slack:
            await slack.send_message("#general", "Hello!")
    """

    service_name = "slack"
    base_url = "https://slack.com/api"
    api_version = ""  # Slack doesn't use versioned URLs

    def __init__(
        self,
        access_token: Optional[str] = None,
        bot_token: Optional[str] = None,
    ):
        """
        Initialize Slack integration.

        Args:
            access_token: OAuth access token (xoxp-...)
            bot_token: Bot token (xoxb-...)
        """
        token = access_token or bot_token or os.getenv("SLACK_BOT_TOKEN")
        super().__init__(access_token=token)

    def _get_auth_header(self) -> Dict[str, str]:
        """Get Slack authorization header."""
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        return {}

    async def send_message(
        self,
        channel: str,
        text: str,
        blocks: Optional[List[Dict]] = None,
        attachments: Optional[List[Dict]] = None,
        thread_ts: Optional[str] = None,
        reply_broadcast: bool = False,
        unfurl_links: bool = True,
        unfurl_media: bool = True,
    ) -> APIResponse:
        """
        Send message to a Slack channel.

        Args:
            channel: Channel ID or name (e.g., "#general" or "C1234567890")
            text: Message text
            blocks: Block Kit blocks for rich formatting
            attachments: Legacy attachments
            thread_ts: Thread timestamp for replies
            reply_broadcast: Also post to channel when replying to thread
            unfurl_links: Unfurl links in message
            unfurl_media: Unfurl media in message

        Returns:
            APIResponse with message details
        """
        payload = {
            "channel": channel,
            "text": text,
            "unfurl_links": unfurl_links,
            "unfurl_media": unfurl_media,
        }

        if blocks:
            payload["blocks"] = blocks
        if attachments:
            payload["attachments"] = attachments
        if thread_ts:
            payload["thread_ts"] = thread_ts
            payload["reply_broadcast"] = reply_broadcast

        return await self.post("chat.postMessage", json=payload)

    async def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        blocks: Optional[List[Dict]] = None,
    ) -> APIResponse:
        """Update an existing message."""
        payload = {
            "channel": channel,
            "ts": ts,
            "text": text,
        }
        if blocks:
            payload["blocks"] = blocks

        return await self.post("chat.update", json=payload)

    async def delete_message(self, channel: str, ts: str) -> APIResponse:
        """Delete a message."""
        return await self.post("chat.delete", json={
            "channel": channel,
            "ts": ts,
        })

    async def add_reaction(
        self,
        channel: str,
        timestamp: str,
        name: str,
    ) -> APIResponse:
        """Add emoji reaction to a message."""
        return await self.post("reactions.add", json={
            "channel": channel,
            "timestamp": timestamp,
            "name": name,
        })

    async def upload_file(
        self,
        channels: List[str],
        content: Optional[str] = None,
        file_path: Optional[str] = None,
        filename: str = "file.txt",
        title: Optional[str] = None,
        initial_comment: Optional[str] = None,
    ) -> APIResponse:
        """
        Upload a file to Slack.

        Args:
            channels: Channel IDs to share file in
            content: File content as string
            file_path: Path to local file (alternative to content)
            filename: Filename to display
            title: Title of file
            initial_comment: Comment to add with file

        Returns:
            APIResponse with file details
        """
        import aiohttp
        import aiofiles

        data = aiohttp.FormData()
        data.add_field("channels", ",".join(channels))
        data.add_field("filename", filename)

        if title:
            data.add_field("title", title)
        if initial_comment:
            data.add_field("initial_comment", initial_comment)

        if content:
            data.add_field("content", content)
        elif file_path:
            async with aiofiles.open(file_path, "rb") as f:
                file_content = await f.read()
                data.add_field("file", file_content, filename=filename)

        session = await self._ensure_session()
        async with session.post(
            f"{self.base_url}/files.upload",
            data=data,
            headers=self._get_auth_header(),
        ) as response:
            result = await response.json()
            return APIResponse(
                ok=result.get("ok", False),
                status=response.status,
                data=result,
                error=result.get("error"),
            )

    async def list_channels(
        self,
        types: str = "public_channel,private_channel",
        limit: int = 100,
    ) -> APIResponse:
        """List channels in workspace."""
        return await self.get("conversations.list", params={
            "types": types,
            "limit": limit,
        })

    async def get_channel_info(self, channel: str) -> APIResponse:
        """Get channel information."""
        return await self.get("conversations.info", params={
            "channel": channel,
        })

    async def list_users(self, limit: int = 100) -> APIResponse:
        """List users in workspace."""
        return await self.get("users.list", params={"limit": limit})

    async def get_user_info(self, user: str) -> APIResponse:
        """Get user information."""
        return await self.get("users.info", params={"user": user})

    async def open_dm(self, users: List[str]) -> APIResponse:
        """Open direct message channel with users."""
        return await self.post("conversations.open", json={
            "users": ",".join(users),
        })

    async def post_ephemeral(
        self,
        channel: str,
        user: str,
        text: str,
        blocks: Optional[List[Dict]] = None,
    ) -> APIResponse:
        """Post ephemeral message visible only to specific user."""
        payload = {
            "channel": channel,
            "user": user,
            "text": text,
        }
        if blocks:
            payload["blocks"] = blocks

        return await self.post("chat.postEphemeral", json=payload)
