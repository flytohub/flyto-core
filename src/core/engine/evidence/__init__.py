"""
Evidence Module

Records comprehensive execution evidence for each workflow step.
"""

from .models import (
    BrowserContextProtocol,
    StepEvidence,
)
from .store import EvidenceStore
from .hook import StepEvidenceHook
from .executor_hooks import (
    EvidenceExecutorHooks,
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
    "StepEvidenceHook",
    "EvidenceExecutorHooks",
    # Factory functions
    "create_evidence_executor_hooks",
    "create_evidence_hook",
    "create_evidence_store",
]
