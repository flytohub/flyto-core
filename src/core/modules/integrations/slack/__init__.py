# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Slack Integration

Provides Slack workspace integration:
- Send messages to channels
- Post to threads
- Upload files
- Manage channels
- User management
"""

from .integration import SlackIntegration
from .modules import (
    SlackSendMessageModule,
    SlackListChannelsModule,
)

__all__ = [
    'SlackIntegration',
    'SlackSendMessageModule',
    'SlackListChannelsModule',
]
