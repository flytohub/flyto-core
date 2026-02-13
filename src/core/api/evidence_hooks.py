"""
API Evidence Hooks

ExecutorHooks implementation that collects step evidence via the EvidenceStore.
Designed to run inside an already-running event loop (FastAPI).
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

from core.engine.hooks import ExecutorHooks, HookContext, HookResult
from core.engine.evidence import EvidenceStore, StepEvidence

logger = logging.getLogger(__name__)


class APIEvidenceHooks(ExecutorHooks):
    """
    Collects context_before / context_after for every step and persists
    them via EvidenceStore.  Unlike EvidenceExecutorHooks this class is
    async-safe — it schedules saves as fire-and-forget tasks so the
    workflow engine is not blocked.
    """

    def __init__(self, evidence_store: EvidenceStore, execution_id: str):
        self.store = evidence_store
        self.execution_id = execution_id
        self._step_starts: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_workflow_start(self, context: HookContext) -> HookResult:
        return HookResult.continue_execution()

    def on_workflow_complete(self, context: HookContext) -> None:
        pass

    def on_workflow_failed(self, context: HookContext) -> None:
        pass

    # ------------------------------------------------------------------
    # Step hooks
    # ------------------------------------------------------------------

    def on_pre_execute(self, context: HookContext) -> HookResult:
        step_id = context.step_id or "unknown"
        self._step_starts[step_id] = {
            "time": time.time(),
            "context_before": _safe_copy(context.variables),
            "module_id": context.module_id,
            "step_index": context.step_index,
        }
        return HookResult.continue_execution()

    def on_post_execute(self, context: HookContext) -> HookResult:
        step_id = context.step_id or "unknown"
        start_info = self._step_starts.pop(step_id, None)

        if start_info is None:
            return HookResult.continue_execution()

        duration_ms = int((time.time() - start_info["time"]) * 1000)

        evidence = StepEvidence(
            step_id=step_id,
            execution_id=self.execution_id,
            timestamp=datetime.now(),
            duration_ms=duration_ms,
            context_before=start_info["context_before"],
            context_after=_safe_copy(context.variables),
            status="success",
            output=_result_to_dict(context.result),
            module_id=start_info.get("module_id"),
            step_index=start_info.get("step_index"),
        )

        # Save synchronously — we're inside the engine's event loop
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.store.save_evidence(evidence))
        except RuntimeError:
            asyncio.run(self.store.save_evidence(evidence))

        return HookResult.continue_execution()

    def on_error(self, context: HookContext) -> HookResult:
        step_id = context.step_id or "unknown"
        start_info = self._step_starts.pop(step_id, None)

        duration_ms = 0
        context_before: Dict[str, Any] = {}
        if start_info:
            duration_ms = int((time.time() - start_info["time"]) * 1000)
            context_before = start_info["context_before"]

        evidence = StepEvidence(
            step_id=step_id,
            execution_id=self.execution_id,
            timestamp=datetime.now(),
            duration_ms=duration_ms,
            context_before=context_before,
            context_after=_safe_copy(context.variables),
            status="error",
            error_message=context.error_message or str(context.error),
            module_id=context.module_id,
            step_index=context.step_index,
        )

        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.store.save_evidence(evidence))
        except RuntimeError:
            asyncio.run(self.store.save_evidence(evidence))

        return HookResult.continue_execution()

    def on_retry(self, context: HookContext) -> HookResult:
        return HookResult.continue_execution()

    def on_module_missing(self, context: HookContext) -> HookResult:
        return HookResult.abort_execution(f"Module not found: {context.module_id}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_copy(variables: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow-copy variables, replacing non-serialisable objects with placeholders."""
    out: Dict[str, Any] = {}
    for k, v in variables.items():
        if isinstance(v, (str, int, float, bool, type(None))):
            out[k] = v
        elif isinstance(v, (dict, list)):
            try:
                import json
                json.dumps(v, default=str)
                out[k] = v
            except (TypeError, ValueError):
                out[k] = f"<non-serialisable {type(v).__name__}>"
        else:
            out[k] = f"<{type(v).__name__}>"
    return out


def _result_to_dict(result: Any) -> Dict[str, Any]:
    """Coerce a step result to a JSON-safe dict."""
    if result is None:
        return {}
    if isinstance(result, dict):
        return result
    return {"value": str(result)}
