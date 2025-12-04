"""
Communication Service Integrations
Slack, Discord, Telegram, Email SMTP, Twilio
"""

from .messaging import *
from .twilio import *

__all__ = [
    # Communication modules will be auto-discovered by module registry
]
