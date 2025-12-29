"""
Messaging Modules

Send notifications to various platforms.
"""

from .slack import SlackSendMessageModule
from .discord import DiscordSendMessageModule
from .telegram import TelegramSendMessageModule
from .email import EmailSendModule

__all__ = [
    'SlackSendMessageModule',
    'DiscordSendMessageModule',
    'TelegramSendMessageModule',
    'EmailSendModule',
]
