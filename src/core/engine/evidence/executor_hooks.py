"""
Evidence Executor Hooks

ExecutorHooks wrapper for evidence capture.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from .hook import StepEvidenceHook
from .models import BrowserContextProtocol
from .store import EvidenceStore

logger = logging.getLogger(__name__)


class EvidenceExecutorHooks:
    """
    ExecutorHooks wrapper for evidence capture.

    Integrates StepEvidenceHook with the WorkflowEngine hooks system.

    Usage:
        store = EvidenceStore(Path("./evidence"))
        evidence_hooks = EvidenceExecutorHooks(store, "exec_123")

        # Compose with other hooks
        from .hooks import CompositeHooks, LoggingHooks
        composite = CompositeHooks([LoggingHooks(), evidence_hooks])

        # Pass to WorkflowEngine
        engine = WorkflowEngine(workflow, hooks=composite)
    """

    def __init__(
        self,
        store: EvidenceStore,
        execution_id: str,
        browser_context: Optional[BrowserContextProtocol] = None,
        capture_screenshots: bool = True,
        capture_dom: bool = True,
    ):
        """
        Initialize evidence hooks.

        Args:
            store: EvidenceStore instance
            execution_id: Unique execution identifier
            browser_context: Optional browser context for screenshots
            capture_screenshots: Whether to capture screenshots
            capture_dom: Whether to capture DOM snapshots
        """
        self._hook = StepEvidenceHook(
            store=store,
            execution_id=execution_id,
            browser_context=browser_context,
            capture_screenshots=capture_screenshots,
            capture_dom=capture_dom,
        )
        self._store = store
        self._execution_id = execution_id

    def set_browser_context(self, browser_context: BrowserContextProtocol) -> None:
        """Set browser context for screenshot capture"""
        self._hook.set_browser_context(browser_context)

    def on_workflow_start(self, context: Any) -> Any:
        """Called when workflow starts"""
        # Import here to avoid circular imports
        from ..hooks import HookResult
        return HookResult.continue_execution()

    def on_workflow_complete(self, context: Any) -> None:
        """Called when workflow completes successfully"""
        pass

    def on_workflow_failed(self, context: Any) -> None:
        """Called when workflow fails"""
        pass

    def on_module_missing(self, context: Any) -> Any:
        """Called when module is not found"""
        from ..hooks import HookResult
        return HookResult.abort_execution(f"Module not found: {context.module_id}")

    def on_pre_execute(self, context: Any) -> Any:
        """Called before each step - capture context before"""
        from ..hooks import HookResult
        try:
            # Run async hook in sync context
            asyncio.get_event_loop().run_until_complete(
                self._hook.on_pre_execute(context)
            )
        except RuntimeError:
            # No event loop running - create one
            asyncio.run(self._hook.on_pre_execute(context))
        except Exception as e:
            logger.warning(f"Evidence pre-execute failed: {e}")
        return HookResult.continue_execution()

    def on_post_execute(self, context: Any) -> Any:
        """Called after each step - capture evidence"""
        from ..hooks import HookResult
        try:
            asyncio.get_event_loop().run_until_complete(
                self._hook.on_post_execute(context)
            )
        except RuntimeError:
            asyncio.run(self._hook.on_post_execute(context))
        except Exception as e:
            logger.warning(f"Evidence post-execute failed: {e}")
        return HookResult.continue_execution()

    def on_error(self, context: Any) -> Any:
        """Called when step fails"""
        from ..hooks import HookResult
        return HookResult.continue_execution()

    def on_retry(self, context: Any) -> Any:
        """Called before retry"""
        from ..hooks import HookResult
        return HookResult.continue_execution()

    @property
    def store(self) -> EvidenceStore:
        """Get evidence store"""
        return self._store

    @property
    def execution_id(self) -> str:
        """Get execution ID"""
        return self._execution_id


# =============================================================================
# Factory functions
# =============================================================================

def create_evidence_store(
    base_path: Optional[Path] = None,
    capture_context: bool = True,
) -> EvidenceStore:
    """
    Create an evidence store with sensible defaults.

    Args:
        base_path: Base directory (defaults to ./evidence)
        capture_context: Whether to capture context snapshots

    Returns:
        Configured EvidenceStore
    """
    if base_path is None:
        base_path = Path("./evidence")
    return EvidenceStore(base_path, capture_context=capture_context)


def create_evidence_hook(
    store: EvidenceStore,
    execution_id: str,
    browser_context: Optional[BrowserContextProtocol] = None,
) -> StepEvidenceHook:
    """
    Create an evidence hook.

    Args:
        store: EvidenceStore to use
        execution_id: Unique execution identifier
        browser_context: Optional browser context for screenshots

    Returns:
        Configured StepEvidenceHook
    """
    return StepEvidenceHook(
        store=store,
        execution_id=execution_id,
        browser_context=browser_context,
    )


def create_evidence_executor_hooks(
    execution_id: str,
    base_path: Optional[Path] = None,
    browser_context: Optional[BrowserContextProtocol] = None,
    capture_screenshots: bool = True,
    capture_dom: bool = True,
) -> EvidenceExecutorHooks:
    """
    Create evidence executor hooks ready to use with WorkflowEngine.

    This is the recommended way to add evidence capture to workflow execution.

    Args:
        execution_id: Unique execution identifier
        base_path: Base directory for evidence (defaults to ./evidence)
        browser_context: Optional browser context for screenshots
        capture_screenshots: Whether to capture screenshots
        capture_dom: Whether to capture DOM snapshots

    Returns:
        Configured EvidenceExecutorHooks

    Example:
        from core.engine.evidence import create_evidence_executor_hooks
        from core.engine.hooks import CompositeHooks, LoggingHooks

        # Create evidence hooks
        evidence = create_evidence_executor_hooks("exec_123")

        # Optionally compose with other hooks
        hooks = CompositeHooks([LoggingHooks(), evidence])

        # Pass to engine
        engine = WorkflowEngine(workflow, hooks=hooks)
        result = await engine.execute()

        # Access evidence after execution
        evidence_list = await evidence.store.load_evidence("exec_123")
    """
    store = create_evidence_store(base_path)
    return EvidenceExecutorHooks(
        store=store,
        execution_id=execution_id,
        browser_context=browser_context,
        capture_screenshots=capture_screenshots,
        capture_dom=capture_dom,
    )
