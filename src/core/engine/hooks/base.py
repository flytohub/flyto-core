"""
Hook Base Classes

Abstract base class and null implementation for executor hooks.
"""

from abc import ABC

from .models import HookContext, HookResult


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
