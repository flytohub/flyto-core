"""
Server State

Manages cross-request state: browser sessions, running workflows, evidence, replay.
"""

import logging
from pathlib import Path
from typing import Any, Dict

from core.engine.evidence import EvidenceStore, create_evidence_store
from core.engine.replay import ReplayManager, create_replay_manager

logger = logging.getLogger(__name__)

# Default evidence directory
DEFAULT_EVIDENCE_PATH = Path("./evidence")


class ServerState:
    """Singleton-ish state shared across all API requests."""

    def __init__(self, evidence_path: Path = DEFAULT_EVIDENCE_PATH):
        self.browser_sessions: Dict[str, Any] = {}
        self.running_workflows: Dict[str, Any] = {}
        self.evidence_store: EvidenceStore = create_evidence_store(evidence_path)
        self.replay_manager: ReplayManager = create_replay_manager(evidence_path)
        self._evidence_path = evidence_path
        logger.info("ServerState initialized (evidence: %s)", evidence_path)

    @property
    def evidence_path(self) -> Path:
        return self._evidence_path
