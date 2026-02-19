# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

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
