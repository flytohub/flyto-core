# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Generate deterministic Warroom replay scenarios."""

from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from .engine import generate_scenarios, scenarios_to_yaml


@register_module(
    module_id="warroom.generate_scenarios",
    version="1.0.0",
    category="warroom",
    tags=["warroom", "scenario", "yaml", "deterministic"],
    label="Warroom Generate Scenarios",
    description="Generate replayable Flyto2 YAML scenarios from a Warroom site graph",
    icon="FileCode",
    color="#14B8A6",
    input_types=["object"],
    output_types=["object", "string"],
    can_receive_from=["warroom.*", "data.*", "flow.*", "start"],
    can_connect_to=["warroom.*", "testing.*", "file.*", "data.*"],
    params_schema={
        "site_graph": {"type": "object", "required": True, "description": "Warroom site graph"},
        "name": {"type": "string", "required": False, "description": "Scenario bundle name"},
        "output_format": {"type": "string", "default": "yaml", "description": "yaml or object"},
    },
    output_schema={
        "ok": {"type": "boolean"},
        "scenarios": {"type": "object"},
        "workflow": {"type": "string"},
    },
    timeout_ms=30000,
)
class WarroomGenerateScenariosModule(BaseModule):
    """Generate replayable scenarios from a Warroom graph."""

    module_name = "Warroom Generate Scenarios"
    module_description = "Generate deterministic replay YAML"

    def validate_params(self) -> None:
        if not isinstance(self.params.get("site_graph"), dict):
            raise ValueError("site_graph object is required")

    async def execute(self) -> Dict[str, Any]:
        scenarios = generate_scenarios(
            self.params["site_graph"],
            name=self.params.get("name", "Warroom Generated Regression"),
        )
        workflow = scenarios_to_yaml(scenarios)
        return {"ok": True, "scenarios": scenarios, "workflow": workflow}
