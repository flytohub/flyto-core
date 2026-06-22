# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Manual, evidence-only LLM review boundary for Warroom."""

from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from .engine import redact


@register_module(
    module_id="warroom.llm_review",
    version="1.0.0",
    category="warroom",
    tags=["warroom", "llm", "review", "manual", "evidence"],
    label="Warroom LLM Review",
    description="Prepare redacted evidence for manual LLM review; never gates by itself",
    icon="Brain",
    color="#A855F7",
    input_types=["object"],
    output_types=["object"],
    can_receive_from=["warroom.*", "data.*", "flow.*"],
    can_connect_to=["warroom.*", "data.*", "notify.*"],
    params_schema={
        "enabled": {"type": "boolean", "default": False},
        "evidence_pack": {"type": "object", "required": True},
        "question": {"type": "string", "required": False},
    },
    output_schema={
        "ok": {"type": "boolean"},
        "status": {"type": "string"},
        "advisory_only": {"type": "boolean"},
        "redacted_evidence": {"type": "object"},
    },
    timeout_ms=30000,
)
class WarroomLlmReviewModule(BaseModule):
    """Prepare evidence for opt-in LLM review without making gate decisions."""

    module_name = "Warroom LLM Review"
    module_description = "Manual evidence-only LLM review boundary"

    def validate_params(self) -> None:
        if not isinstance(self.params.get("evidence_pack"), dict):
            raise ValueError("evidence_pack object is required")

    async def execute(self) -> Dict[str, Any]:
        redacted = redact(self.params["evidence_pack"])
        if not self.params.get("enabled", False):
            return {
                "ok": True,
                "status": "skipped_disabled",
                "advisory_only": True,
                "message": "LLM review is disabled by default. Deterministic evidence remains authoritative.",
                "redacted_evidence": redacted,
            }
        return {
            "ok": True,
            "status": "ready_for_manual_review",
            "advisory_only": True,
            "question": self.params.get("question", "Review uncertain Warroom evidence."),
            "redacted_evidence": redacted,
        }
