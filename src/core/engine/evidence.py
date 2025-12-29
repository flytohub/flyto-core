"""
Step Evidence System

Records comprehensive execution evidence for each workflow step:
- Context snapshots (before/after)
- Screenshots (browser modules)
- DOM snapshots (browser modules)
- Execution metadata

This is a capability n8n lacks - full execution evidence with replay support.

Design principles:
- Non-blocking: Evidence capture failures don't break execution
- Filesystem-based: Works offline, no external dependencies
- Structured: JSONL for metadata, files for binary/HTML
"""

import asyncio
import copy
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class StepEvidence:
    """
    Evidence record for a single step execution.

    Captures complete execution state for debugging, replay, and audit.
    """
    # Identification
    step_id: str
    execution_id: str
    timestamp: datetime
    duration_ms: int

    # Context snapshots
    context_before: Dict[str, Any]
    context_after: Dict[str, Any]

    # UI evidence (browser modules only)
    screenshot_path: Optional[str] = None
    dom_snapshot_path: Optional[str] = None

    # Execution result
    status: Literal['success', 'error', 'skipped'] = 'success'
    error_message: Optional[str] = None
    output: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    module_id: Optional[str] = None
    step_index: Optional[int] = None
    attempt: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        # Convert datetime to ISO format
        if isinstance(data.get('timestamp'), datetime):
            data['timestamp'] = data['timestamp'].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepEvidence":
        """Create from dictionary"""
        # Convert ISO string back to datetime
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class BrowserContextProtocol(Protocol):
    """Protocol for browser context that provides page access"""

    def get_current_page(self) -> Any:
        """Get current browser page for screenshot/DOM capture"""
        ...


class EvidenceStore:
    """
    Stores execution evidence to filesystem.

    Directory structure:
        evidence/
        ├── exec_abc123/
        │   ├── evidence.jsonl    # All step metadata
        │   ├── step_1.png        # Screenshot
        │   ├── step_1.html       # DOM snapshot
        │   └── ...
        └── exec_def456/
            └── ...
    """

    def __init__(
        self,
        base_path: Path,
        capture_context: bool = True,
        max_context_depth: int = 5,
    ):
        """
        Initialize evidence store.

        Args:
            base_path: Base directory for evidence storage
            capture_context: Whether to capture context snapshots
            max_context_depth: Max nesting depth for context serialization
        """
        self.base_path = Path(base_path)
        self.capture_context = capture_context
        self.max_context_depth = max_context_depth

    def get_execution_dir(self, execution_id: str) -> Path:
        """Get/create directory for execution evidence"""
        path = self.base_path / execution_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def save_evidence(self, evidence: StepEvidence) -> None:
        """
        Save evidence metadata to JSONL file.

        Appends to evidence.jsonl in the execution directory.
        """
        try:
            exec_dir = self.get_execution_dir(evidence.execution_id)
            jsonl_path = exec_dir / "evidence.jsonl"

            # Serialize to JSON
            data = evidence.to_dict()
            # Truncate large context if needed
            data = self._truncate_large_values(data)
            line = json.dumps(data, default=str, ensure_ascii=False) + '\n'

            # Append to JSONL file
            # Using sync write for simplicity - could be async with aiofiles
            with open(jsonl_path, 'a', encoding='utf-8') as f:
                f.write(line)

            logger.debug(f"Saved evidence for step {evidence.step_id}")

        except Exception as e:
            logger.warning(f"Failed to save evidence for {evidence.step_id}: {e}")

    async def save_screenshot(
        self,
        execution_id: str,
        step_id: str,
        screenshot_bytes: bytes,
    ) -> str:
        """
        Save screenshot and return relative path.

        Args:
            execution_id: Execution ID
            step_id: Step ID (used as filename)
            screenshot_bytes: PNG image data

        Returns:
            Relative filename (e.g., "step_1.png")
        """
        try:
            exec_dir = self.get_execution_dir(execution_id)
            filename = f"{step_id}.png"
            path = exec_dir / filename

            with open(path, 'wb') as f:
                f.write(screenshot_bytes)

            logger.debug(f"Saved screenshot: {path}")
            return filename

        except Exception as e:
            logger.warning(f"Failed to save screenshot for {step_id}: {e}")
            return ""

    async def save_dom_snapshot(
        self,
        execution_id: str,
        step_id: str,
        dom_html: str,
    ) -> str:
        """
        Save DOM snapshot and return relative path.

        Args:
            execution_id: Execution ID
            step_id: Step ID (used as filename)
            dom_html: HTML content

        Returns:
            Relative filename (e.g., "step_1.html")
        """
        try:
            exec_dir = self.get_execution_dir(execution_id)
            filename = f"{step_id}.html"
            path = exec_dir / filename

            with open(path, 'w', encoding='utf-8') as f:
                f.write(dom_html)

            logger.debug(f"Saved DOM snapshot: {path}")
            return filename

        except Exception as e:
            logger.warning(f"Failed to save DOM snapshot for {step_id}: {e}")
            return ""

    async def load_evidence(self, execution_id: str) -> List[StepEvidence]:
        """
        Load all evidence for an execution.

        Args:
            execution_id: Execution ID to load

        Returns:
            List of StepEvidence records in execution order
        """
        exec_dir = self.base_path / execution_id
        jsonl_path = exec_dir / "evidence.jsonl"

        if not jsonl_path.exists():
            return []

        evidence_list = []
        try:
            with open(jsonl_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        evidence_list.append(StepEvidence.from_dict(data))
        except Exception as e:
            logger.warning(f"Failed to load evidence for {execution_id}: {e}")

        return evidence_list

    async def load_step_evidence(
        self,
        execution_id: str,
        step_id: str,
    ) -> Optional[StepEvidence]:
        """
        Load evidence for a specific step.

        Args:
            execution_id: Execution ID
            step_id: Step ID to find

        Returns:
            StepEvidence if found, None otherwise
        """
        all_evidence = await self.load_evidence(execution_id)
        for evidence in all_evidence:
            if evidence.step_id == step_id:
                return evidence
        return None

    async def get_screenshot_path(
        self,
        execution_id: str,
        step_id: str,
    ) -> Optional[Path]:
        """Get full path to screenshot file if it exists"""
        path = self.base_path / execution_id / f"{step_id}.png"
        return path if path.exists() else None

    async def get_dom_snapshot_path(
        self,
        execution_id: str,
        step_id: str,
    ) -> Optional[Path]:
        """Get full path to DOM snapshot file if it exists"""
        path = self.base_path / execution_id / f"{step_id}.html"
        return path if path.exists() else None

    async def list_executions(self) -> List[str]:
        """List all execution IDs with evidence"""
        if not self.base_path.exists():
            return []

        return [
            d.name for d in self.base_path.iterdir()
            if d.is_dir() and (d / "evidence.jsonl").exists()
        ]

    async def delete_execution(self, execution_id: str) -> bool:
        """
        Delete all evidence for an execution.

        Args:
            execution_id: Execution ID to delete

        Returns:
            True if deleted, False if not found
        """
        import shutil
        exec_dir = self.base_path / execution_id
        if exec_dir.exists():
            shutil.rmtree(exec_dir)
            return True
        return False

    def _truncate_large_values(
        self,
        data: Any,
        max_str_length: int = 10000,
        current_depth: int = 0,
    ) -> Any:
        """Truncate large string values to prevent huge JSONL files"""
        if current_depth > self.max_context_depth:
            return "[truncated: max depth]"

        if isinstance(data, dict):
            return {
                k: self._truncate_large_values(v, max_str_length, current_depth + 1)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            if len(data) > 100:
                return data[:100] + ["[truncated: list too long]"]
            return [
                self._truncate_large_values(v, max_str_length, current_depth + 1)
                for v in data
            ]
        elif isinstance(data, str) and len(data) > max_str_length:
            return data[:max_str_length] + f"... [truncated: {len(data)} chars]"
        elif isinstance(data, bytes):
            return f"[binary data: {len(data)} bytes]"
        return data


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


# =============================================================================
# ExecutorHooks Integration
# =============================================================================

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
        from .hooks import HookResult
        return HookResult.continue_execution()

    def on_workflow_complete(self, context: Any) -> None:
        """Called when workflow completes successfully"""
        pass

    def on_workflow_failed(self, context: Any) -> None:
        """Called when workflow fails"""
        pass

    def on_module_missing(self, context: Any) -> Any:
        """Called when module is not found"""
        from .hooks import HookResult
        return HookResult.abort_execution(f"Module not found: {context.module_id}")

    def on_pre_execute(self, context: Any) -> Any:
        """Called before each step - capture context before"""
        from .hooks import HookResult
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
        from .hooks import HookResult
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
        from .hooks import HookResult
        return HookResult.continue_execution()

    def on_retry(self, context: Any) -> Any:
        """Called before retry"""
        from .hooks import HookResult
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
