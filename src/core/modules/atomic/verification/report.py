# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Create deterministic verification evidence reports."""

from ...registry import register_module
from ..warroom.report import WarroomReportModule


@register_module(
    module_id="verification.report",
    version="1.0.0",
    category="verification",
    tags=["verification", "report", "evidence", "json", "markdown"],
    label="Verification Report",
    description="Create a deterministic verification evidence pack and optional report file",
    icon="FileCheck",
    color="#6366F1",
    input_types=["object"],
    output_types=["object", "string"],
    can_receive_from=["verification.*", "testing.*", "verify.*", "data.*", "flow.*"],
    can_connect_to=["file.*", "verification.*", "data.*", "notify.*"],
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
class VerificationReportModule(WarroomReportModule):
    """Generate deterministic verification evidence report."""

    module_name = "Verification Report"
    module_description = "Create deterministic verification evidence pack"

