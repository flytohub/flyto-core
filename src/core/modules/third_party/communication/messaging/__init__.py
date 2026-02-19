# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Messaging Modules

Send notifications to various platforms.
"""

from .slack import SlackSendMessageModule
from .discord import DiscordSendMessageModule
from .telegram import TelegramSendMessageModule
from .email import EmailSendModule
from .teams import TeamsSendMessageModule
from .whatsapp import WhatsAppSendMessageModule

__all__ = [
    'SlackSendMessageModule',
    'DiscordSendMessageModule',
    'TelegramSendMessageModule',
    'EmailSendModule',
    'TeamsSendMessageModule',
    'WhatsAppSendMessageModule',
]
