"""
Step Evidence System

DEPRECATED: This file is maintained for backwards compatibility.
Please import from core.engine.evidence instead:

    from core.engine.evidence import EvidenceStore

All functionality has been split into:
- core/engine/evidence/models.py - StepEvidence dataclass and protocols
- core/engine/evidence/store.py - EvidenceStore class
- core/engine/evidence/hook.py - StepEvidenceHook class
- core/engine/evidence/executor_hooks.py - EvidenceExecutorHooks and factories

Original design principles:
- Non-blocking: Evidence capture failures don't break execution
- Filesystem-based: Works offline, no external dependencies
- Structured: JSONL for metadata, files for binary/HTML
"""

# Re-export for backwards compatibility
from .evidence import (
    # Models
    BrowserContextProtocol,
    StepEvidence,
    # Store
    EvidenceStore,
    # Hooks
    EvidenceExecutorHooks,
    StepEvidenceHook,
    # Factory functions
    create_evidence_executor_hooks,
    create_evidence_hook,
    create_evidence_store,
)

__all__ = [
    # Models
    "BrowserContextProtocol",
    "StepEvidence",
    # Store
    "EvidenceStore",
    # Hooks
    "EvidenceExecutorHooks",
    "StepEvidenceHook",
    # Factory functions
    "create_evidence_executor_hooks",
    "create_evidence_hook",
    "create_evidence_store",
]
