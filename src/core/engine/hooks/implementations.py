"""
Hook Implementations

Concrete implementations of executor hooks.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from .base import ExecutorHooks
from .models import HookAction, HookContext, HookResult

logger = logging.getLogger(__name__)


class LoggingHooks(ExecutorHooks):
    """
    Hooks that log execution events.

    Useful for debugging and audit trails.
    """

    def __init__(
        self,
        logger_name: str = "flyto.executor",
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
