#!/usr/bin/env bash
set -euo pipefail

# Non-actuating consumer verifier for flyto-modules-robotics.
# It proves registration and the authoring contract only. It never contacts ROS,
# a gateway, a simulator, or physical hardware.

python - <<'PY'
import asyncio
import json

import flyto_modules_robotics as robotics
from core.modules.registry.core import ModuleRegistry

plugins = ModuleRegistry.discover_plugins(force=True)
assert "robotics" in plugins, plugins

module_ids = sorted(
    module_id for module_id in ModuleRegistry._modules
    if module_id.startswith("robotics.")
)
assert module_ids == ["robotics.move", "robotics.stop", "robotics.turn"], module_ids

cases = {
    "robotics.move": ({"distance_m": 0.4}, "motion.advance"),
    "robotics.turn": ({"degrees": 30}, "motion.rotate"),
    "robotics.stop": ({}, "motion.halt"),
}

for module_id, (params, capability_id) in cases.items():
    module = ModuleRegistry.get(module_id)
    metadata = ModuleRegistry.get_metadata(module_id) or {}
    assert metadata.get("requires_credentials") is False, (module_id, metadata)

    result = asyncio.run(module(params, {"resource_id": "verify-robot"}).execute())
    assert result["ok"] is True, (module_id, result)
    assert result["dispatched"] is False
    assert result["commanded_resource"] == "verify-robot"

    request = result["capability_request"]
    assert request["contract_version"] == "flyto.capability-request.v1"
    assert request["resource_id"] == "verify-robot"
    assert request["capability_id"] == capability_id

    encoded = json.dumps(result, sort_keys=True)
    for forbidden in (
        "requires_device",
        "flyto.robotics.plan.v1",
        "127.0.0.1",
        ":8766",
        "FLYTO_ROBOTICS_GATEWAY_URL",
        "FLYTO_ROBOTICS_DELIVERY_TOKEN",
    ):
        assert forbidden not in encoded, (module_id, forbidden)

print("robotics capability-request consumer verification passed")
PY
