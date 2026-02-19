# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Trigger Framework — Webhook and Cron triggers for workflow execution.

Provides an extensible trigger system that can fire workflows from
external HTTP webhooks or on a cron schedule.

Both ``WebhookTriggerManager`` and ``CronTriggerManager`` are Pro
features gated behind their respective ``FeatureFlag`` values.
"""

from .base import (
    BaseTriggerManager,
    TriggerConfig,
    TriggerEvent,
    TriggerStatus,
    TriggerType,
)
from .cron import CronConfig, CronTriggerManager
from .webhook import WebhookConfig, WebhookTriggerManager

__all__ = [
    # Base
    "TriggerType",
    "TriggerStatus",
    "TriggerConfig",
    "TriggerEvent",
    "BaseTriggerManager",
    # Webhook
    "WebhookConfig",
    "WebhookTriggerManager",
    # Cron
    "CronConfig",
    "CronTriggerManager",
]
