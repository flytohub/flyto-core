# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Trigger Framework — Base models and abstract trigger manager.

Defines the core trigger types, statuses, and the abstract interface
that all trigger managers must implement.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class TriggerType(str, Enum):
    """Types of triggers that can fire a workflow."""
    WEBHOOK = "webhook"
    CRON = "cron"
    MANUAL = "manual"


class TriggerStatus(str, Enum):
    """Lifecycle status of a trigger."""
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


# =============================================================================
# Models
# =============================================================================


@dataclass
class TriggerConfig:
    """Base configuration for any trigger."""
    trigger_id: str
    trigger_type: TriggerType
    workflow_id: str
    name: str
    status: TriggerStatus = TriggerStatus.ACTIVE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TriggerEvent:
    """An event emitted when a trigger fires."""
    event_id: str
    trigger_id: str
    trigger_type: TriggerType
    workflow_id: str
    payload: Dict[str, Any]
    triggered_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Abstract Base
# =============================================================================


class BaseTriggerManager:
    """
    Abstract base for trigger managers.

    Provides in-memory trigger storage and standard CRUD operations.
    Subclasses extend with trigger-type-specific behaviour
    (e.g. signature verification for webhooks, scheduling for cron).
    """

    def __init__(self) -> None:
        self._triggers: Dict[str, TriggerConfig] = {}

    # ── CRUD ────────────────────────────────────────────────────────────

    def register(self, config: TriggerConfig) -> TriggerConfig:
        """Register a new trigger configuration."""
        now = datetime.utcnow()
        if config.created_at is None:
            config.created_at = now
        config.updated_at = now
        self._triggers[config.trigger_id] = config
        logger.info(
            "Trigger registered: %s (%s) for workflow %s",
            config.trigger_id,
            config.trigger_type.value,
            config.workflow_id,
        )
        return config

    def unregister(self, trigger_id: str) -> bool:
        """Remove a trigger. Returns True if it existed."""
        if trigger_id in self._triggers:
            del self._triggers[trigger_id]
            logger.info("Trigger unregistered: %s", trigger_id)
            return True
        return False

    def get(self, trigger_id: str) -> Optional[TriggerConfig]:
        """Look up a trigger by ID."""
        return self._triggers.get(trigger_id)

    def list_triggers(
        self, workflow_id: Optional[str] = None
    ) -> List[TriggerConfig]:
        """List triggers, optionally filtered by workflow_id."""
        triggers = list(self._triggers.values())
        if workflow_id is not None:
            triggers = [t for t in triggers if t.workflow_id == workflow_id]
        return triggers

    # ── Lifecycle ───────────────────────────────────────────────────────

    def pause(self, trigger_id: str) -> bool:
        """Pause a trigger so it stops firing."""
        config = self._triggers.get(trigger_id)
        if config is None:
            return False
        config.status = TriggerStatus.PAUSED
        config.updated_at = datetime.utcnow()
        logger.info("Trigger paused: %s", trigger_id)
        return True

    def resume(self, trigger_id: str) -> bool:
        """Resume a paused trigger."""
        config = self._triggers.get(trigger_id)
        if config is None:
            return False
        config.status = TriggerStatus.ACTIVE
        config.updated_at = datetime.utcnow()
        logger.info("Trigger resumed: %s", trigger_id)
        return True


__all__ = [
    "TriggerType",
    "TriggerStatus",
    "TriggerConfig",
    "TriggerEvent",
    "BaseTriggerManager",
]
