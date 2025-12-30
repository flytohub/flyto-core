"""
Step Evidence Hook

Hook that captures comprehensive execution evidence.
"""

import copy
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from .models import BrowserContextProtocol, StepEvidence
from .store import EvidenceStore

logger = logging.getLogger(__name__)


class StepEvidenceHook:
    """
    Hook that captures comprehensive execution evidence.

    Integrates with WorkflowEngine via on_pre_execute/on_post_execute.

    Usage:
        store = EvidenceStore(Path("./evidence"))
        hook = StepEvidenceHook(store, execution_id="exec_123")

        # In workflow engine:
        await hook.on_pre_execute(hook_context)
        # ... execute step ...
        await hook.on_post_execute(hook_context)
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
        Initialize evidence hook.

        Args:
            store: EvidenceStore instance
            execution_id: Unique execution identifier
            browser_context: Optional browser context for screenshots
            capture_screenshots: Whether to capture screenshots
            capture_dom: Whether to capture DOM snapshots
        """
        self.store = store
        self.execution_id = execution_id
        self.browser_context = browser_context
        self.capture_screenshots = capture_screenshots
        self.capture_dom = capture_dom

        # Per-step state
        self._context_before: Dict[str, Any] = {}
        self._start_time: Optional[datetime] = None

    def set_browser_context(self, browser_context: BrowserContextProtocol) -> None:
        """Set browser context for screenshot capture"""
        self.browser_context = browser_context

    async def on_pre_execute(self, ctx: Any) -> None:
        """
        Capture context before step execution.

        Args:
            ctx: HookContext from workflow engine
        """
        try:
            # Deep copy context to capture before state
            self._context_before = copy.deepcopy(
                getattr(ctx, 'variables', {})
            )
            self._start_time = datetime.now()
        except Exception as e:
            logger.warning(f"Failed to capture pre-execute context: {e}")
            self._context_before = {}
            self._start_time = datetime.now()

    async def on_post_execute(self, ctx: Any) -> None:
        """
        Capture evidence after step execution.

        Args:
            ctx: HookContext from workflow engine
        """
        try:
            # Calculate duration
            if self._start_time:
                duration_ms = int(
                    (datetime.now() - self._start_time).total_seconds() * 1000
                )
            else:
                duration_ms = 0

            # Get step info from context
            step_id = getattr(ctx, 'step_id', None) or 'unknown'
            module_id = getattr(ctx, 'module_id', None)
            step_index = getattr(ctx, 'step_index', None)
            error = getattr(ctx, 'error', None)
            result = getattr(ctx, 'result', None)
            variables = getattr(ctx, 'variables', {})

            # Determine if this is a browser module
            is_browser = module_id and module_id.startswith('browser.')

            # Create evidence record
            evidence = StepEvidence(
                step_id=step_id,
                execution_id=self.execution_id,
                timestamp=self._start_time or datetime.now(),
                duration_ms=duration_ms,
                context_before=self._context_before,
                context_after=dict(variables) if variables else {},
                status='error' if error else 'success',
                error_message=str(error) if error else None,
                output=dict(result) if isinstance(result, dict) else {},
                module_id=module_id,
                step_index=step_index,
                attempt=getattr(ctx, 'attempt', 1),
            )

            # Capture browser evidence if applicable
            if is_browser and self.browser_context:
                evidence = await self._capture_browser_evidence(evidence)

            # Save evidence
            await self.store.save_evidence(evidence)

        except Exception as e:
            logger.warning(f"Failed to capture post-execute evidence: {e}")

        finally:
            # Reset state
            self._context_before = {}
            self._start_time = None

    async def _capture_browser_evidence(
        self,
        evidence: StepEvidence,
    ) -> StepEvidence:
        """
        Capture screenshot and DOM for browser modules.

        Non-blocking - failures logged but don't affect execution.
        """
        if not self.browser_context:
            return evidence

        try:
            page = self.browser_context.get_current_page()
            if not page:
                return evidence

            # Capture screenshot
            if self.capture_screenshots:
                try:
                    screenshot = await page.screenshot()
                    if screenshot:
                        evidence.screenshot_path = await self.store.save_screenshot(
                            evidence.execution_id,
                            evidence.step_id,
                            screenshot
                        )
                except Exception as e:
                    logger.debug(f"Screenshot capture failed: {e}")

            # Capture DOM
            if self.capture_dom:
                try:
                    dom = await page.content()
                    if dom:
                        evidence.dom_snapshot_path = await self.store.save_dom_snapshot(
                            evidence.execution_id,
                            evidence.step_id,
                            dom
                        )
                except Exception as e:
                    logger.debug(f"DOM capture failed: {e}")

        except Exception as e:
            logger.warning(f"Browser evidence capture failed: {e}")

        return evidence
