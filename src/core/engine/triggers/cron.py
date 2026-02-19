# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Cron Trigger Manager — schedule-driven workflow triggers.

Pro feature gated behind FeatureFlag.SCHEDULED_JOBS.
Implements a 5-field cron expression parser (minute hour day_of_month
month day_of_week) using only the standard library and an async
scheduler loop that fires due triggers every 60 seconds.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

from core.licensing import FeatureFlag, LicenseError, LicenseManager

from .base import (
    BaseTriggerManager,
    TriggerConfig,
    TriggerEvent,
    TriggerStatus,
    TriggerType,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Models
# =============================================================================


@dataclass
class CronConfig(TriggerConfig):
    """Cron-specific trigger configuration."""

    # Standard 5-field cron expression, e.g. "0 9 * * 1-5"
    expression: str = ""

    # IANA timezone name (only UTC implemented in the stdlib-only parser)
    timezone: str = "UTC"

    # Static params forwarded to the workflow on each run
    params: Dict[str, Any] = field(default_factory=dict)

    # Execution bookkeeping
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0

    # None = unlimited
    max_runs: Optional[int] = None


# =============================================================================
# Cron Expression Parser (stdlib only)
# =============================================================================


def _parse_cron_field(token: str, min_val: int, max_val: int) -> Set[int]:
    """
    Parse a single cron field token into a set of matching integer values.

    Supported syntax:
    - ``*``            every value
    - ``5``            specific value
    - ``1-5``          inclusive range
    - ``1,3,5``        list
    - ``*/5``          every 5th value starting from *min_val*
    - ``1-10/2``       every 2nd value in range 1..10
    """
    values: Set[int] = set()

    for part in token.split(","):
        part = part.strip()

        # Handle step (e.g. */5 or 1-10/2)
        step = 1
        if "/" in part:
            range_part, step_str = part.split("/", 1)
            step = int(step_str)
            if step < 1:
                raise ValueError(
                    "Step must be >= 1, got: {}".format(step)
                )
            part = range_part

        if part == "*":
            values.update(range(min_val, max_val + 1, step))
        elif "-" in part:
            lo_str, hi_str = part.split("-", 1)
            lo, hi = int(lo_str), int(hi_str)
            if lo < min_val or hi > max_val or lo > hi:
                raise ValueError(
                    "Range {}-{} out of bounds [{}, {}]".format(
                        lo, hi, min_val, max_val
                    )
                )
            values.update(range(lo, hi + 1, step))
        else:
            val = int(part)
            if val < min_val or val > max_val:
                raise ValueError(
                    "Value {} out of bounds [{}, {}]".format(
                        val, min_val, max_val
                    )
                )
            values.add(val)

    return values


# =============================================================================
# Cron Trigger Manager
# =============================================================================


class CronTriggerManager(BaseTriggerManager):
    """
    Manages cron (schedule) based workflow triggers.

    Parses standard 5-field cron expressions, calculates next-run
    times, and provides an async scheduler loop that fires due
    triggers at ~60-second intervals.
    """

    def __init__(self) -> None:
        self._require_feature()
        super().__init__()
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    # ── Feature gate ────────────────────────────────────────────────────

    @staticmethod
    def _require_feature() -> None:
        """Verify that the SCHEDULED_JOBS feature is licensed."""
        manager = LicenseManager.get_instance()
        if not manager.has_feature(FeatureFlag.SCHEDULED_JOBS):
            raise LicenseError(
                "Scheduled Jobs requires a Pro license",
                feature=FeatureFlag.SCHEDULED_JOBS,
            )

    # ── Registration ────────────────────────────────────────────────────

    def register_schedule(
        self,
        workflow_id: str,
        name: str,
        expression: str,
        timezone: str = "UTC",
        params: Optional[Dict[str, Any]] = None,
        max_runs: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CronConfig:
        """
        Register a new cron trigger for a workflow.

        The expression is validated immediately; an invalid expression
        raises ``ValueError``.

        Args:
            workflow_id: Workflow to execute on each tick.
            name: Human-readable name.
            expression: 5-field cron expression.
            timezone: IANA timezone (currently only UTC is supported).
            params: Static params passed to the workflow each run.
            max_runs: Maximum number of executions (``None`` = unlimited).
            metadata: Arbitrary extra metadata.

        Returns:
            The registered ``CronConfig`` with ``next_run`` pre-computed.
        """
        self._require_feature()

        # Validate expression early
        self.parse_expression(expression)

        now = datetime.utcnow()
        next_run = self.calculate_next_run(expression, timezone, after=now)

        config = CronConfig(
            trigger_id=str(uuid.uuid4()),
            trigger_type=TriggerType.CRON,
            workflow_id=workflow_id,
            name=name,
            expression=expression,
            timezone=timezone,
            params=params or {},
            max_runs=max_runs,
            next_run=next_run,
            metadata=metadata or {},
        )

        return self.register(config)  # type: ignore[return-value]

    # ── Cron parsing ────────────────────────────────────────────────────

    @staticmethod
    def parse_expression(expression: str) -> Dict[str, Set[int]]:
        """
        Parse a 5-field cron expression into its component sets.

        Fields (left to right):
            minute (0-59), hour (0-23), day_of_month (1-31),
            month (1-12), day_of_week (0-6, 0 = Sunday).

        Returns:
            Dict with keys ``minute``, ``hour``, ``day_of_month``,
            ``month``, ``day_of_week``, each mapping to a ``Set[int]``.

        Raises:
            ``ValueError`` on malformed expressions.
        """
        tokens = expression.strip().split()
        if len(tokens) != 5:
            raise ValueError(
                "Cron expression must have exactly 5 fields, "
                "got {}: '{}'".format(len(tokens), expression)
            )

        return {
            "minute": _parse_cron_field(tokens[0], 0, 59),
            "hour": _parse_cron_field(tokens[1], 0, 23),
            "day_of_month": _parse_cron_field(tokens[2], 1, 31),
            "month": _parse_cron_field(tokens[3], 1, 12),
            "day_of_week": _parse_cron_field(tokens[4], 0, 6),
        }

    # ── Next-run calculation ────────────────────────────────────────────

    @staticmethod
    def calculate_next_run(
        expression: str,
        timezone: str = "UTC",
        after: Optional[datetime] = None,
    ) -> datetime:
        """
        Calculate the next datetime that matches *expression*.

        Scans forward minute-by-minute from *after* (default: now).
        A safety limit of 366 days prevents infinite loops on
        impossible expressions.

        Args:
            expression: 5-field cron expression.
            timezone: Timezone hint (currently only UTC is used).
            after: Starting point; defaults to ``datetime.utcnow()``.

        Returns:
            The next matching ``datetime`` (whole minute, seconds=0).

        Raises:
            ``ValueError`` if no match is found within 366 days.
        """
        fields = CronTriggerManager.parse_expression(expression)
        if after is None:
            after = datetime.utcnow()

        # Start from the next whole minute
        candidate = after.replace(second=0, microsecond=0) + timedelta(
            minutes=1
        )

        # Safety: don't scan more than 366 days (~527_040 minutes)
        max_candidate = candidate + timedelta(days=366)

        while candidate < max_candidate:
            # day_of_week: Python weekday() gives 0=Monday..6=Sunday
            # Cron convention: 0=Sunday..6=Saturday
            python_dow = candidate.weekday()  # 0=Mon
            cron_dow = (python_dow + 1) % 7  # shift to 0=Sun

            if (
                candidate.minute in fields["minute"]
                and candidate.hour in fields["hour"]
                and candidate.day in fields["day_of_month"]
                and candidate.month in fields["month"]
                and cron_dow in fields["day_of_week"]
            ):
                return candidate

            candidate += timedelta(minutes=1)

        raise ValueError(
            "No matching time found within 366 days for "
            "expression: '{}'".format(expression)
        )

    # ── Runtime checks ──────────────────────────────────────────────────

    def should_run(self, trigger_id: str) -> bool:
        """
        Check whether a trigger should fire right now.

        A trigger should fire when:
        - It exists and is ACTIVE.
        - ``next_run`` is at or before ``utcnow()``.
        - ``max_runs`` has not been reached (if set).
        """
        config = self.get(trigger_id)
        if config is None:
            return False

        cron_cfg: CronConfig = config  # type: ignore[assignment]

        if cron_cfg.status != TriggerStatus.ACTIVE:
            return False

        if cron_cfg.next_run is None:
            return False

        now = datetime.utcnow()
        if cron_cfg.next_run > now:
            return False

        if (
            cron_cfg.max_runs is not None
            and cron_cfg.run_count >= cron_cfg.max_runs
        ):
            return False

        return True

    def record_run(self, trigger_id: str) -> CronConfig:
        """
        Record that a trigger has fired.

        Updates ``last_run``, increments ``run_count``, and computes
        the next ``next_run``.  If ``max_runs`` is reached the trigger
        is automatically set to DISABLED.

        Returns:
            The updated ``CronConfig``.

        Raises:
            ``KeyError`` if the trigger does not exist.
        """
        config = self.get(trigger_id)
        if config is None:
            raise KeyError(
                "Trigger not found: {}".format(trigger_id)
            )

        cron_cfg: CronConfig = config  # type: ignore[assignment]
        now = datetime.utcnow()

        cron_cfg.last_run = now
        cron_cfg.run_count += 1
        cron_cfg.updated_at = now

        # Check max_runs
        if (
            cron_cfg.max_runs is not None
            and cron_cfg.run_count >= cron_cfg.max_runs
        ):
            cron_cfg.status = TriggerStatus.DISABLED
            cron_cfg.next_run = None
            logger.info(
                "Cron trigger %s reached max_runs (%d), disabled",
                trigger_id,
                cron_cfg.max_runs,
            )
        else:
            cron_cfg.next_run = self.calculate_next_run(
                cron_cfg.expression,
                cron_cfg.timezone,
                after=now,
            )

        return cron_cfg

    def get_due_triggers(self) -> List[CronConfig]:
        """
        Return all ACTIVE cron triggers whose ``next_run`` is now or
        in the past (i.e. they should fire).
        """
        now = datetime.utcnow()
        due: List[CronConfig] = []
        for config in self._triggers.values():
            if not isinstance(config, CronConfig):
                continue
            if config.status != TriggerStatus.ACTIVE:
                continue
            if config.next_run is not None and config.next_run <= now:
                # Also respect max_runs
                if (
                    config.max_runs is not None
                    and config.run_count >= config.max_runs
                ):
                    continue
                due.append(config)
        return due

    # ── Async scheduler ─────────────────────────────────────────────────

    async def start_scheduler(
        self,
        on_trigger: Callable[
            [TriggerEvent], Coroutine[Any, Any, None]
        ],
    ) -> None:
        """
        Start the async scheduler loop.

        Polls every 60 seconds for due triggers.  For each due trigger
        a ``TriggerEvent`` is created, ``record_run`` is called, and
        *on_trigger* is awaited with the event.

        Args:
            on_trigger: Async callback invoked for each fired trigger.
        """
        if self._running:
            logger.warning("Cron scheduler is already running")
            return

        self._running = True
        logger.info("Cron scheduler started")

        async def _loop() -> None:
            while self._running:
                try:
                    due = self.get_due_triggers()
                    for cron_cfg in due:
                        event = TriggerEvent(
                            event_id=str(uuid.uuid4()),
                            trigger_id=cron_cfg.trigger_id,
                            trigger_type=TriggerType.CRON,
                            workflow_id=cron_cfg.workflow_id,
                            payload=dict(cron_cfg.params),
                            triggered_at=datetime.utcnow(),
                            metadata={
                                "expression": cron_cfg.expression,
                                "run_count": cron_cfg.run_count + 1,
                            },
                        )

                        self.record_run(cron_cfg.trigger_id)

                        try:
                            await on_trigger(event)
                        except Exception:
                            logger.exception(
                                "Error in on_trigger callback for %s",
                                cron_cfg.trigger_id,
                            )
                except Exception:
                    logger.exception("Error in cron scheduler tick")

                # Sleep 60 seconds, but break early if stopped
                try:
                    await asyncio.wait_for(
                        self._sleep_event.wait(), timeout=60.0
                    )
                except asyncio.TimeoutError:
                    pass

        self._sleep_event = asyncio.Event()
        self._task = asyncio.ensure_future(_loop())

    async def stop_scheduler(self) -> None:
        """Stop the scheduler loop gracefully."""
        if not self._running:
            return

        self._running = False
        # Wake the sleep so the loop exits promptly
        if hasattr(self, "_sleep_event"):
            self._sleep_event.set()

        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
            self._task = None

        logger.info("Cron scheduler stopped")


__all__ = [
    "CronConfig",
    "CronTriggerManager",
]
