"""
Executor Hooks Interface

Provides extension points for workflow execution lifecycle.
Allows external code to observe and modify execution behavior
without changing the core engine.

Design principles:
- Zero coupling: hooks are optional, engine works without them
- Protocol-based: any object implementing the protocol works
- Composable: multiple hooks can be combined
- Fail-safe: hook errors don't break execution
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Union

logger = logging.getLogger(__name__)


class HookAction(Enum):
    """Actions a hook can request"""
    CONTINUE = "continue"      # Proceed normally
    SKIP = "skip"              # Skip current step
    RETRY = "retry"            # Retry current step
    ABORT = "abort"            # Abort execution
    SUBSTITUTE = "substitute"  # Use substitute result


@dataclass
class HookContext:
    """
    Context passed to hook methods.

    Contains all information about the current execution state
    without exposing internal engine details.
    """
    # Workflow identification
    workflow_id: str
    workflow_name: str = ""

    # Current step info (if applicable)
    step_id: Optional[str] = None
    step_index: Optional[int] = None
    total_steps: Optional[int] = None
    module_id: Optional[str] = None

    # Execution state
    params: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)

    # Timing
    started_at: Optional[datetime] = None
    elapsed_ms: float = 0

    # Error info (for error hooks)
    error: Optional[Exception] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    # Result info (for post-execute hooks)
    result: Optional[Any] = None

    # Retry info
    attempt: int = 1
    max_attempts: int = 3

    # Custom metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "step_id": self.step_id,
            "step_index": self.step_index,
            "total_steps": self.total_steps,
            "module_id": self.module_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "elapsed_ms": self.elapsed_ms,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "attempt": self.attempt,
            "metadata": self.metadata,
        }


@dataclass
class HookResult:
    """
    Result returned by hook methods.

    Allows hooks to influence execution flow without
    direct access to engine internals.
    """
    action: HookAction = HookAction.CONTINUE

    # For SUBSTITUTE action
    substitute_result: Optional[Any] = None

    # For RETRY action
    retry_delay_ms: float = 1000

    # For ABORT action
    abort_reason: Optional[str] = None

    # Additional data to pass along
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def continue_execution(cls) -> "HookResult":
        """Helper to create continue result"""
        return cls(action=HookAction.CONTINUE)

    @classmethod
    def skip_step(cls) -> "HookResult":
        """Helper to create skip result"""
        return cls(action=HookAction.SKIP)

    @classmethod
    def retry_step(cls, delay_ms: float = 1000) -> "HookResult":
        """Helper to create retry result"""
        return cls(action=HookAction.RETRY, retry_delay_ms=delay_ms)

    @classmethod
    def abort_execution(cls, reason: str) -> "HookResult":
        """Helper to create abort result"""
        return cls(action=HookAction.ABORT, abort_reason=reason)

    @classmethod
    def substitute(cls, result: Any) -> "HookResult":
        """Helper to create substitute result"""
        return cls(action=HookAction.SUBSTITUTE, substitute_result=result)


class ExecutorHooks(ABC):
    """
    Abstract base class for executor hooks.

    Provides extension points for:
    - Module missing handling
    - Pre/post execution
    - Error handling
    - Workflow lifecycle

    All methods have default implementations that do nothing,
    allowing subclasses to override only what they need.
    """

    def on_workflow_start(self, context: HookContext) -> HookResult:
        """
        Called when workflow execution begins.

        Args:
            context: Execution context with workflow info

        Returns:
            HookResult indicating how to proceed
        """
        return HookResult.continue_execution()

    def on_workflow_complete(self, context: HookContext) -> None:
        """
        Called when workflow execution completes successfully.

        Args:
            context: Execution context with final state
        """
        pass

    def on_workflow_failed(self, context: HookContext) -> None:
        """
        Called when workflow execution fails.

        Args:
            context: Execution context with error info
        """
        pass

    def on_module_missing(self, context: HookContext) -> HookResult:
        """
        Called when a module is not found.

        This is a key extension point for:
        - Auto-installation of modules
        - Module substitution
        - Graceful degradation

        Args:
            context: Execution context with module_id

        Returns:
            HookResult (SKIP, SUBSTITUTE, or ABORT)
        """
        return HookResult.abort_execution(f"Module not found: {context.module_id}")

    def on_pre_execute(self, context: HookContext) -> HookResult:
        """
        Called before each step execution.

        Allows:
        - Parameter modification via metadata
        - Step skipping
        - Execution blocking

        Args:
            context: Execution context with step info

        Returns:
            HookResult indicating how to proceed
        """
        return HookResult.continue_execution()

    def on_post_execute(self, context: HookContext) -> HookResult:
        """
        Called after each step execution (success or failure).

        Allows:
        - Result transformation
        - Metric collection
        - Conditional retry

        Args:
            context: Execution context with result/error

        Returns:
            HookResult indicating how to proceed
        """
        return HookResult.continue_execution()

    def on_error(self, context: HookContext) -> HookResult:
        """
        Called when a step execution fails.

        Allows:
        - Error recovery
        - Retry logic
        - Error transformation

        Args:
            context: Execution context with error info

        Returns:
            HookResult (RETRY, SKIP, SUBSTITUTE, or ABORT)
        """
        return HookResult.continue_execution()

    def on_retry(self, context: HookContext) -> HookResult:
        """
        Called before a retry attempt.

        Args:
            context: Execution context with retry info

        Returns:
            HookResult indicating whether to proceed with retry
        """
        return HookResult.continue_execution()


class NullHooks(ExecutorHooks):
    """
    No-op hooks implementation.

    Used as default when no hooks are configured.
    All methods return continue/do nothing.
    """
    pass


class LoggingHooks(ExecutorHooks):
    """
    Hooks that log execution events.

    Useful for debugging and audit trails.
    """

    def __init__(
        self,
        logger_name: str = "flyto2.executor",
        log_level: int = logging.INFO,
        log_params: bool = False,
        log_results: bool = False,
    ):
        """
        Initialize logging hooks.

        Args:
            logger_name: Name of logger to use
            log_level: Default log level
            log_params: Whether to log step parameters
            log_results: Whether to log step results
        """
        self._logger = logging.getLogger(logger_name)
        self._level = log_level
        self._log_params = log_params
        self._log_results = log_results

    def on_workflow_start(self, context: HookContext) -> HookResult:
        self._logger.log(
            self._level,
            f"Workflow started: {context.workflow_id} ({context.workflow_name})"
        )
        return HookResult.continue_execution()

    def on_workflow_complete(self, context: HookContext) -> None:
        self._logger.log(
            self._level,
            f"Workflow completed: {context.workflow_id} "
            f"(elapsed: {context.elapsed_ms:.1f}ms)"
        )

    def on_workflow_failed(self, context: HookContext) -> None:
        self._logger.error(
            f"Workflow failed: {context.workflow_id} "
            f"- {context.error_type}: {context.error_message}"
        )

    def on_module_missing(self, context: HookContext) -> HookResult:
        self._logger.warning(f"Module not found: {context.module_id}")
        return HookResult.abort_execution(f"Module not found: {context.module_id}")

    def on_pre_execute(self, context: HookContext) -> HookResult:
        msg = (
            f"Step {context.step_index}/{context.total_steps}: "
            f"{context.module_id} ({context.step_id})"
        )
        if self._log_params and context.params:
            msg += f" params={context.params}"
        self._logger.log(self._level, msg)
        return HookResult.continue_execution()

    def on_post_execute(self, context: HookContext) -> HookResult:
        if context.error:
            self._logger.error(
                f"Step failed: {context.step_id} "
                f"- {context.error_type}: {context.error_message}"
            )
        else:
            msg = f"Step completed: {context.step_id} ({context.elapsed_ms:.1f}ms)"
            if self._log_results and context.result is not None:
                # Truncate large results
                result_str = str(context.result)
                if len(result_str) > 200:
                    result_str = result_str[:200] + "..."
                msg += f" result={result_str}"
            self._logger.log(self._level, msg)
        return HookResult.continue_execution()

    def on_error(self, context: HookContext) -> HookResult:
        self._logger.warning(
            f"Error in step {context.step_id}: "
            f"{context.error_type}: {context.error_message}"
        )
        return HookResult.continue_execution()

    def on_retry(self, context: HookContext) -> HookResult:
        self._logger.info(
            f"Retrying step {context.step_id}: "
            f"attempt {context.attempt}/{context.max_attempts}"
        )
        return HookResult.continue_execution()


class MetricsHooks(ExecutorHooks):
    """
    Hooks that collect execution metrics.

    Tracks timing, success/failure counts, and module usage.
    """

    def __init__(self):
        """Initialize metrics collection"""
        self._workflow_count = 0
        self._workflow_success = 0
        self._workflow_failed = 0
        self._step_count = 0
        self._step_success = 0
        self._step_failed = 0
        self._step_skipped = 0
        self._retry_count = 0
        self._total_duration_ms = 0.0
        self._module_usage: Dict[str, int] = {}
        self._module_errors: Dict[str, int] = {}
        self._current_workflow_start: Optional[float] = None

    def on_workflow_start(self, context: HookContext) -> HookResult:
        self._workflow_count += 1
        self._current_workflow_start = time.time()
        return HookResult.continue_execution()

    def on_workflow_complete(self, context: HookContext) -> None:
        self._workflow_success += 1
        if self._current_workflow_start:
            duration = (time.time() - self._current_workflow_start) * 1000
            self._total_duration_ms += duration
        self._current_workflow_start = None

    def on_workflow_failed(self, context: HookContext) -> None:
        self._workflow_failed += 1
        if self._current_workflow_start:
            duration = (time.time() - self._current_workflow_start) * 1000
            self._total_duration_ms += duration
        self._current_workflow_start = None

    def on_pre_execute(self, context: HookContext) -> HookResult:
        self._step_count += 1
        if context.module_id:
            self._module_usage[context.module_id] = (
                self._module_usage.get(context.module_id, 0) + 1
            )
        return HookResult.continue_execution()

    def on_post_execute(self, context: HookContext) -> HookResult:
        if context.error:
            self._step_failed += 1
            if context.module_id:
                self._module_errors[context.module_id] = (
                    self._module_errors.get(context.module_id, 0) + 1
                )
        else:
            self._step_success += 1
        return HookResult.continue_execution()

    def on_retry(self, context: HookContext) -> HookResult:
        self._retry_count += 1
        return HookResult.continue_execution()

    def get_metrics(self) -> Dict[str, Any]:
        """Get collected metrics"""
        return {
            "workflows": {
                "total": self._workflow_count,
                "success": self._workflow_success,
                "failed": self._workflow_failed,
                "success_rate": (
                    self._workflow_success / self._workflow_count
                    if self._workflow_count > 0 else 0
                ),
            },
            "steps": {
                "total": self._step_count,
                "success": self._step_success,
                "failed": self._step_failed,
                "skipped": self._step_skipped,
                "success_rate": (
                    self._step_success / self._step_count
                    if self._step_count > 0 else 0
                ),
            },
            "retries": self._retry_count,
            "total_duration_ms": self._total_duration_ms,
            "avg_workflow_duration_ms": (
                self._total_duration_ms / self._workflow_count
                if self._workflow_count > 0 else 0
            ),
            "module_usage": dict(self._module_usage),
            "module_errors": dict(self._module_errors),
        }

    def reset(self) -> None:
        """Reset all metrics"""
        self._workflow_count = 0
        self._workflow_success = 0
        self._workflow_failed = 0
        self._step_count = 0
        self._step_success = 0
        self._step_failed = 0
        self._step_skipped = 0
        self._retry_count = 0
        self._total_duration_ms = 0.0
        self._module_usage.clear()
        self._module_errors.clear()


class CompositeHooks(ExecutorHooks):
    """
    Combines multiple hooks into one.

    Calls each hook in order. If any hook returns a non-CONTINUE
    action, that action is used (first wins).

    Errors in individual hooks are caught and logged,
    allowing other hooks to continue.
    """

    def __init__(self, hooks: Optional[List[ExecutorHooks]] = None):
        """
        Initialize composite hooks.

        Args:
            hooks: List of hooks to combine
        """
        self._hooks: List[ExecutorHooks] = hooks or []

    def add_hook(self, hook: ExecutorHooks) -> None:
        """Add a hook to the composite"""
        self._hooks.append(hook)

    def remove_hook(self, hook: ExecutorHooks) -> bool:
        """Remove a hook from the composite"""
        if hook in self._hooks:
            self._hooks.remove(hook)
            return True
        return False

    def _call_hooks(
        self,
        method_name: str,
        context: HookContext,
        return_result: bool = True,
    ) -> HookResult:
        """
        Call a method on all hooks.

        Args:
            method_name: Name of hook method to call
            context: Context to pass
            return_result: Whether method returns HookResult

        Returns:
            First non-CONTINUE result, or CONTINUE
        """
        result = HookResult.continue_execution()
        found_non_continue = False

        for hook in self._hooks:
            try:
                method = getattr(hook, method_name, None)
                if method is None:
                    continue

                if return_result:
                    hook_result = method(context)
                    # First non-continue wins, but still call remaining hooks
                    if (hook_result and
                        hook_result.action != HookAction.CONTINUE and
                        not found_non_continue):
                        result = hook_result
                        found_non_continue = True
                else:
                    method(context)

            except Exception as e:
                logger.warning(
                    f"Hook error in {hook.__class__.__name__}.{method_name}: {e}"
                )

        return result

    def on_workflow_start(self, context: HookContext) -> HookResult:
        return self._call_hooks("on_workflow_start", context)

    def on_workflow_complete(self, context: HookContext) -> None:
        self._call_hooks("on_workflow_complete", context, return_result=False)

    def on_workflow_failed(self, context: HookContext) -> None:
        self._call_hooks("on_workflow_failed", context, return_result=False)

    def on_module_missing(self, context: HookContext) -> HookResult:
        return self._call_hooks("on_module_missing", context)

    def on_pre_execute(self, context: HookContext) -> HookResult:
        return self._call_hooks("on_pre_execute", context)

    def on_post_execute(self, context: HookContext) -> HookResult:
        return self._call_hooks("on_post_execute", context)

    def on_error(self, context: HookContext) -> HookResult:
        return self._call_hooks("on_error", context)

    def on_retry(self, context: HookContext) -> HookResult:
        return self._call_hooks("on_retry", context)


# =============================================================================
# Convenience functions
# =============================================================================

def create_hooks(
    logging_enabled: bool = False,
    metrics_enabled: bool = False,
    custom_hooks: Optional[List[ExecutorHooks]] = None,
    log_params: bool = False,
    log_results: bool = False,
) -> ExecutorHooks:
    """
    Create a hooks instance with common configurations.

    Args:
        logging_enabled: Enable logging hooks
        metrics_enabled: Enable metrics hooks
        custom_hooks: Additional custom hooks
        log_params: Log step parameters (if logging enabled)
        log_results: Log step results (if logging enabled)

    Returns:
        Configured ExecutorHooks instance
    """
    hooks_list: List[ExecutorHooks] = []

    if logging_enabled:
        hooks_list.append(LoggingHooks(
            log_params=log_params,
            log_results=log_results,
        ))

    if metrics_enabled:
        hooks_list.append(MetricsHooks())

    if custom_hooks:
        hooks_list.extend(custom_hooks)

    if not hooks_list:
        return NullHooks()

    if len(hooks_list) == 1:
        return hooks_list[0]

    return CompositeHooks(hooks_list)
