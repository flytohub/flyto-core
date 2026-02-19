# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Execution Timeout Guard

Provides configurable timeout protection at workflow and step levels.
Free tier — essential safety feature for all users.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, TypeVar

from ..hooks.base import ExecutorHooks
from ..hooks.models import HookContext, HookResult

T = TypeVar("T")

# Default timeouts
DEFAULT_WORKFLOW_TIMEOUT_MS = 300_000  # 5 minutes
DEFAULT_STEP_TIMEOUT_MS = 60_000      # 1 minute


class ExecutionTimeoutError(Exception):
    """
    Raised when an execution exceeds its configured timeout.

    Carries structured metadata about what timed out and where.
    """

    def __init__(
        self,
        message: str,
        timeout_ms: float,
        label: str = "",
        workflow_id: Optional[str] = None,
        step_id: Optional[str] = None,
    ):
        super().__init__(message)
        self.timeout_ms = timeout_ms
        self.label = label
        self.workflow_id = workflow_id
        self.step_id = step_id

    def to_dict(self) -> dict:
        """Serialize error details for logging/callbacks."""
        return {
            "message": str(self),
            "timeout_ms": self.timeout_ms,
            "label": self.label,
            "workflow_id": self.workflow_id,
            "step_id": self.step_id,
        }


# Type alias for the timeout callback
TimeoutCallback = Callable[[ExecutionTimeoutError], Any]


class TimeoutGuard:
    """
    Execution timeout protection.

    Provides configurable timeouts at workflow and step level.
    Free tier — essential safety feature.
    """

    def __init__(
        self,
        workflow_timeout_ms: float = DEFAULT_WORKFLOW_TIMEOUT_MS,
        step_timeout_ms: float = DEFAULT_STEP_TIMEOUT_MS,
        on_timeout_callback: Optional[TimeoutCallback] = None,
    ):
        """
        Initialize the timeout guard.

        Args:
            workflow_timeout_ms: Maximum time for entire workflow (default 5 min).
            step_timeout_ms: Maximum time for a single step (default 1 min).
            on_timeout_callback: Optional callback invoked when any timeout occurs.
                                 Receives the ExecutionTimeoutError instance.
        """
        self.workflow_timeout_ms = workflow_timeout_ms
        self.step_timeout_ms = step_timeout_ms
        self.on_timeout_callback = on_timeout_callback

    def _notify_timeout(self, error: ExecutionTimeoutError) -> None:
        """Invoke the timeout callback if configured."""
        if self.on_timeout_callback is not None:
            self.on_timeout_callback(error)

    async def execute_with_timeout(
        self,
        coro: Awaitable[T],
        timeout_ms: Optional[float] = None,
        label: str = "operation",
    ) -> T:
        """
        Wrap a coroutine with a timeout.

        Uses asyncio.wait_for() for Python 3.10 compatibility.

        Args:
            coro: The awaitable to execute.
            timeout_ms: Timeout in milliseconds. Uses step_timeout_ms if None.
            label: Human-readable label for error messages.

        Returns:
            The coroutine's result.

        Raises:
            ExecutionTimeoutError: If the coroutine exceeds the timeout.
        """
        effective_timeout_ms = timeout_ms if timeout_ms is not None else self.step_timeout_ms
        timeout_seconds = effective_timeout_ms / 1000.0

        try:
            result = await asyncio.wait_for(coro, timeout=timeout_seconds)
            return result
        except asyncio.TimeoutError:
            timeout_label = "{} ({}ms)".format(label, int(effective_timeout_ms))
            error = ExecutionTimeoutError(
                message="Execution timed out: {}".format(timeout_label),
                timeout_ms=effective_timeout_ms,
                label=label,
            )
            self._notify_timeout(error)
            raise error from None

    async def guard_workflow(
        self,
        coro: Awaitable[T],
        workflow_id: Optional[str] = None,
    ) -> T:
        """
        Wrap workflow execution with workflow-level timeout.

        Args:
            coro: The workflow coroutine to execute.
            workflow_id: Identifier of the workflow for error reporting.

        Returns:
            The workflow result.

        Raises:
            ExecutionTimeoutError: If the workflow exceeds workflow_timeout_ms.
        """
        timeout_seconds = self.workflow_timeout_ms / 1000.0
        wf_label = "workflow"
        if workflow_id:
            wf_label = "workflow[{}]".format(workflow_id)

        try:
            result = await asyncio.wait_for(coro, timeout=timeout_seconds)
            return result
        except asyncio.TimeoutError:
            error = ExecutionTimeoutError(
                message="Workflow timed out after {}ms: {}".format(
                    int(self.workflow_timeout_ms), wf_label
                ),
                timeout_ms=self.workflow_timeout_ms,
                label=wf_label,
                workflow_id=workflow_id,
            )
            self._notify_timeout(error)
            raise error from None

    async def guard_step(
        self,
        coro: Awaitable[T],
        step_id: Optional[str] = None,
        module_id: Optional[str] = None,
        custom_timeout_ms: Optional[float] = None,
    ) -> T:
        """
        Wrap step execution with step-level timeout.

        Args:
            coro: The step coroutine to execute.
            step_id: Identifier of the step for error reporting.
            module_id: Module being executed in this step.
            custom_timeout_ms: Override the default step timeout for this step.

        Returns:
            The step result.

        Raises:
            ExecutionTimeoutError: If the step exceeds its timeout.
        """
        effective_timeout_ms = custom_timeout_ms if custom_timeout_ms is not None else self.step_timeout_ms
        timeout_seconds = effective_timeout_ms / 1000.0

        # Build a descriptive label
        parts = []
        if step_id:
            parts.append("step={}".format(step_id))
        if module_id:
            parts.append("module={}".format(module_id))
        step_label = "step[{}]".format(", ".join(parts)) if parts else "step"

        try:
            result = await asyncio.wait_for(coro, timeout=timeout_seconds)
            return result
        except asyncio.TimeoutError:
            error = ExecutionTimeoutError(
                message="Step timed out after {}ms: {}".format(
                    int(effective_timeout_ms), step_label
                ),
                timeout_ms=effective_timeout_ms,
                label=step_label,
                step_id=step_id,
            )
            self._notify_timeout(error)
            raise error from None


class TimeoutHooks(ExecutorHooks):
    """
    ExecutorHooks implementation for timeout enforcement.

    Tracks workflow start time and checks elapsed time budget
    before each step execution.

    Usage:
        guard = TimeoutGuard(workflow_timeout_ms=120000)
        hooks = TimeoutHooks(guard)
        # Pass hooks to executor
    """

    def __init__(self, guard: Optional[TimeoutGuard] = None):
        """
        Args:
            guard: TimeoutGuard instance. Creates one with defaults if None.
        """
        self._guard = guard or TimeoutGuard()
        self._workflow_start_times: dict = {}  # workflow_id -> start timestamp (ms)
        self._workflow_timeouts: dict = {}     # workflow_id -> timeout_ms

    def on_workflow_start(self, context: HookContext) -> HookResult:
        """
        Store workflow start time and read timeout from context metadata.

        Metadata key: 'workflow_timeout_ms' overrides the guard default.
        """
        now_ms = time.monotonic() * 1000.0
        self._workflow_start_times[context.workflow_id] = now_ms

        # Allow per-workflow timeout override via context metadata
        timeout_ms = context.metadata.get(
            "workflow_timeout_ms",
            self._guard.workflow_timeout_ms,
        )
        self._workflow_timeouts[context.workflow_id] = float(timeout_ms)

        return HookResult.continue_execution()

    def on_pre_execute(self, context: HookContext) -> HookResult:
        """
        Check if workflow has exceeded total time budget before running the next step.

        Returns ABORT if the budget is exhausted.
        """
        start_ms = self._workflow_start_times.get(context.workflow_id)
        if start_ms is None:
            # No start time recorded — can't enforce, continue
            return HookResult.continue_execution()

        now_ms = time.monotonic() * 1000.0
        elapsed_ms = now_ms - start_ms
        budget_ms = self._workflow_timeouts.get(
            context.workflow_id,
            self._guard.workflow_timeout_ms,
        )

        if elapsed_ms >= budget_ms:
            reason = "Workflow {} exceeded time budget: {:.0f}ms / {:.0f}ms".format(
                context.workflow_id, elapsed_ms, budget_ms
            )

            # Create and notify timeout error
            error = ExecutionTimeoutError(
                message=reason,
                timeout_ms=budget_ms,
                label="workflow[{}]".format(context.workflow_id),
                workflow_id=context.workflow_id,
                step_id=context.step_id,
            )
            self._guard._notify_timeout(error)

            return HookResult.abort_execution(reason)

        return HookResult.continue_execution()

    def on_workflow_complete(self, context: HookContext) -> None:
        """Clean up tracking state for completed workflow."""
        self._workflow_start_times.pop(context.workflow_id, None)
        self._workflow_timeouts.pop(context.workflow_id, None)

    def on_workflow_failed(self, context: HookContext) -> None:
        """Clean up tracking state for failed workflow."""
        self._workflow_start_times.pop(context.workflow_id, None)
        self._workflow_timeouts.pop(context.workflow_id, None)
