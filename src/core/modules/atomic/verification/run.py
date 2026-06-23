# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Replay deterministic verification scenarios."""

from ...registry import register_module
from ..warroom.run import WarroomRunModule


@register_module(
    module_id="verification.run",
    version="1.0.0",
    category="verification",
    tags=["verification", "replay", "testing", "deterministic"],
    label="Verification Run",
    description="Replay generated verification scenarios and return deterministic evidence",
    icon="PlayCircle",
    color="#22C55E",
    input_types=["object"],
    output_types=["object"],
    can_receive_from=["verification.*", "testing.*", "flow.*", "start"],
    can_connect_to=["verification.*", "testing.*", "verify.*", "data.*", "file.*"],
    params_schema={
        "scenarios": {"type": "object", "required": True, "description": "Scenario object with steps"},
        "stop_on_failure": {"type": "boolean", "default": True},
        "timeout_per_step": {"type": "number", "default": 30000},
    },
    output_schema={
        "ok": {"type": "boolean"},
        "passed": {"type": "number"},
        "failed": {"type": "number"},
        "results": {"type": "array"},
        "evaluation": {"type": "object"},
    },
    timeout_ms=300000,
)
class VerificationRunModule(WarroomRunModule):
    """Replay deterministic verification scenarios."""

    module_name = "Verification Run"
    module_description = "Replay generated verification scenarios"

