# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

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
