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
