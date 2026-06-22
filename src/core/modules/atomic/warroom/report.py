# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Build Warroom evidence reports."""

from pathlib import Path
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from .engine import evidence_pack, evidence_to_markdown, to_json


@register_module(
    module_id="warroom.report",
    version="1.0.0",
    category="warroom",
    tags=["warroom", "report", "evidence", "json", "markdown"],
    label="Warroom Report",
    description="Create a deterministic Warroom evidence pack and optional report file",
    icon="FileCheck",
    color="#6366F1",
    input_types=["object"],
    output_types=["object", "string"],
    can_receive_from=["warroom.*", "testing.*", "verify.*", "data.*", "flow.*"],
    can_connect_to=["file.*", "warroom.*", "data.*", "notify.*"],
    params_schema={
        "site_graph": {"type": "object", "required": False},
        "scenarios": {"type": "object", "required": False},
        "run_result": {"type": "object", "required": False},
        "artifacts": {"type": "object", "required": False},
        "format": {"type": "string", "default": "json", "description": "json or markdown"},
        "output_path": {"type": "string", "required": False},
    },
    output_schema={
        "ok": {"type": "boolean"},
        "evidence_pack": {"type": "object"},
        "report": {"type": "string"},
        "path": {"type": "string"},
    },
    timeout_ms=30000,
)
class WarroomReportModule(BaseModule):
    """Generate deterministic Warroom evidence report."""

    module_name = "Warroom Report"
    module_description = "Create deterministic Warroom evidence pack"

    def validate_params(self) -> None:
        self.format = self.params.get("format", "json")
        if self.format not in {"json", "markdown"}:
            raise ValueError("format must be json or markdown")

    async def execute(self) -> Dict[str, Any]:
        pack = evidence_pack(
            site_graph=self.params.get("site_graph"),
            scenarios=self.params.get("scenarios"),
            run_result=self.params.get("run_result"),
            artifacts=self.params.get("artifacts"),
        )
        report = evidence_to_markdown(pack) if self.format == "markdown" else to_json(pack)
        path_value = self.params.get("output_path") or ""
        if path_value:
            path = Path(path_value)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(report, encoding="utf-8")
        return {"ok": True, "evidence_pack": pack, "report": report, "path": path_value}
