"""
Workflow Debug Control

Pause, resume, breakpoints, and step mode functionality.
"""

import logging
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)


class DebugController:
    """
    Manages workflow debugging state.

    Features:
    - Pause/resume execution
    - Breakpoint management
    - Step mode (single-step execution)
    - State snapshots
    """

    def __init__(
        self,
        breakpoints: Optional[Set[str]] = None,
        step_mode: bool = False,
    ):
        """
        Initialize debug controller.

        Args:
            breakpoints: Initial set of step IDs to break at
            step_mode: Enable step-by-step execution
        """
        self._paused: bool = False
        self._cancelled: bool = False
        self._step_mode: bool = step_mode
        self._step_requested: bool = False
        self._breakpoints: Set[str] = breakpoints or set()

    async def should_pause_at_step(
        self,
        step_id: str,
        step_index: int,
        start_step: Optional[int] = None,
    ) -> bool:
        """
        Determine if execution should pause before this step.

        Pauses when:
        - Breakpoint is set on this step_id
        - Step mode is enabled (pause after each step)
        - Explicit pause was requested

        Args:
            step_id: Current step ID
            step_index: Current step index
            start_step: Starting step index (for step mode check)
        """
        # Check explicit pause flag
        if self._paused:
            return True

        # Check breakpoint
        if step_id in self._breakpoints:
            logger.info(f"Breakpoint hit at step '{step_id}'")
            self._paused = True
            return True

        # Check step mode (but allow first step to run, pause before second)
        effective_start = start_step if start_step is not None else 0
        if self._step_mode and step_index > effective_start:
            logger.debug(f"Step mode: pausing before step {step_index}")
            self._paused = True
            return True

        return False

    def cancel(self) -> None:
        """Cancel execution."""
        self._cancelled = True
        logger.info("Execution cancelled")

    def pause(self) -> None:
        """Request pause at next step."""
        self._paused = True
        logger.info("Pause requested")

    def resume(self) -> None:
        """Clear pause flag."""
        self._paused = False
        logger.info("Resume requested")

    def step_over(self) -> bool:
        """
        Execute one step and pause again.

        Returns:
            True if step-over was initiated, False if not paused
        """
        if not self._paused:
            logger.warning("step_over called but not paused")
            return False

        self._step_requested = True
        self._paused = False
        self._step_mode = True
        logger.info("Step-over requested")
        return True

    def clear_step_request(self) -> None:
        """Clear step request flag after stepping."""
        self._step_requested = False

    def add_breakpoint(self, step_id: str) -> None:
        """Add a breakpoint at the specified step."""
        self._breakpoints.add(step_id)
        logger.info(f"Breakpoint added at step '{step_id}'")

    def remove_breakpoint(self, step_id: str) -> bool:
        """
        Remove a breakpoint from the specified step.

        Returns:
            True if breakpoint was removed, False if it didn't exist
        """
        if step_id in self._breakpoints:
            self._breakpoints.discard(step_id)
            logger.info(f"Breakpoint removed from step '{step_id}'")
            return True
        return False

    def clear_breakpoints(self) -> None:
        """Remove all breakpoints."""
        count = len(self._breakpoints)
        self._breakpoints.clear()
        logger.info(f"Cleared {count} breakpoints")

    def get_breakpoints(self) -> Set[str]:
        """Get all current breakpoints."""
        return self._breakpoints.copy()

    @property
    def is_paused(self) -> bool:
        """Check if paused."""
        return self._paused

    @property
    def is_cancelled(self) -> bool:
        """Check if cancelled."""
        return self._cancelled

    @property
    def step_mode(self) -> bool:
        """Check if step mode is enabled."""
        return self._step_mode

    @step_mode.setter
    def step_mode(self, value: bool) -> None:
        """Enable or disable step mode."""
        self._step_mode = value
        logger.info(f"Step mode {'enabled' if value else 'disabled'}")

    @property
    def step_requested(self) -> bool:
        """Check if step-over was requested."""
        return self._step_requested

    def get_debug_state(self) -> Dict[str, Any]:
        """Get current debug state."""
        return {
            'is_paused': self._paused,
            'is_cancelled': self._cancelled,
            'step_mode': self._step_mode,
            'step_requested': self._step_requested,
            'breakpoints': list(self._breakpoints),
        }
