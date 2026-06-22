# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Replay Warroom scenarios through the deterministic test runner."""

from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from ..testing.runner import execute_test_steps
from .engine import evaluate_run


@register_module(
    module_id="warroom.run",
    version="1.0.0",
    category="warroom",
    tags=["warroom", "replay", "testing", "deterministic"],
    label="Warroom Run",
    description="Replay generated Warroom scenarios and return deterministic evidence",
    icon="PlayCircle",
    color="#22C55E",
    input_types=["object"],
    output_types=["object"],
    can_receive_from=["warroom.*", "testing.*", "flow.*", "start"],
    can_connect_to=["warroom.*", "testing.*", "verify.*", "data.*", "file.*"],
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
class WarroomRunModule(BaseModule):
    """Replay deterministic Warroom scenarios."""

    module_name = "Warroom Run"
    module_description = "Replay generated Warroom scenarios"

    def validate_params(self) -> None:
        if not isinstance(self.params.get("scenarios"), dict):
            raise ValueError("scenarios object is required")

    async def execute(self) -> Dict[str, Any]:
        scenarios = self.params["scenarios"]
        result = await execute_test_steps(
            scenarios.get("steps", []),
            context={key: value for key, value in self.context.items() if key != "params"},
            stop_on_failure=self.params.get("stop_on_failure", True),
            timeout_per_step=self.params.get("timeout_per_step", 30000),
        )
        result["evaluation"] = evaluate_run(result)
        return result
