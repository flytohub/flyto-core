# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Verify the optional robotics extension remains an authoring-only capability source.

The robotics plugin does not execute motion from Core. It emits a canonical
`flyto.capability-request.v1` for commanded equipment; Cloud/AI Space policy and
an external adapter own execution. These tests are optional because the
extension is not a base Core dependency.
"""

from __future__ import annotations

import asyncio
import ast
import inspect
import json
import sys
from contextlib import suppress
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.engine.outcome import default_for, is_side_effecting, read_envelope
from core.engine.step_executor.executor import _apply_outcome_contract
from core.modules.registry import ModuleRegistry


GROUP = ["robotics.move", "robotics.turn", "robotics.stop"]
PARAMS = {
    "robotics.move": {"distance_m": 0.5},
    "robotics.turn": {"degrees": 90},
    "robotics.stop": {},
}
EXPECTED_CAPABILITY = {
    "robotics.move": "motion.advance",
    "robotics.turn": "motion.rotate",
    "robotics.stop": "motion.halt",
}


def ensure_modules_loaded() -> None:
    from core.modules import atomic  # noqa: F401

    with suppress(Exception):
        from core.modules import composite  # noqa: F401


ensure_modules_loaded()


@pytest.fixture(autouse=True)
def _skip_without_the_extension():
    pytest.importorskip(
        "flyto_modules_robotics",
        reason="the optional robotics extension is not installed",
    )
    missing = [module_id for module_id in GROUP if not ModuleRegistry.has(module_id)]
    if missing:
        pytest.skip(f"flyto_modules_robotics registered no {missing}")


def run(module_id: str, params: dict, context: dict | None = None) -> dict:
    module = ModuleRegistry.get(module_id)
    return asyncio.run(module(dict(params), dict(context or {})).execute())


def source_tree(module_id: str):
    path = inspect.getsourcefile(ModuleRegistry.get(module_id))
    assert path
    return ast.parse(Path(path).read_text(encoding="utf-8")), path


@pytest.mark.parametrize("module_id", GROUP)
def test_robotics_step_emits_one_canonical_capability_request(module_id):
    payload = run(module_id, PARAMS[module_id], {"resource_id": "robot-1"})

    assert payload["ok"] is True
    assert payload["dispatched"] is False
    assert payload["commanded_resource"] == "robot-1"

    request = payload["capability_request"]
    assert request["contract_version"] == "flyto.capability-request.v1"
    assert request["resource_id"] == "robot-1"
    assert request["capability_id"] == EXPECTED_CAPABILITY[module_id]
    assert isinstance(request["arguments"], dict)
    assert request["goal"]

    encoded = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "requires_device",
        "flyto.robotics.plan.v1",
        "127.0.0.1",
        ":8766",
        "FLYTO_ROBOTICS_GATEWAY_URL",
        "FLYTO_ROBOTICS_DELIVERY_TOKEN",
    ):
        assert forbidden not in encoded


@pytest.mark.parametrize("module_id", GROUP)
def test_robotics_authoring_step_has_no_execution_outcome_rung(module_id):
    metadata = ModuleRegistry.get_metadata(module_id) or {}
    payload = run(module_id, PARAMS[module_id], {"resource_id": "robot-1"})

    assert metadata.get("requires_credentials") is False
    assert not metadata.get("credential_keys")
    assert not metadata.get("required_secrets")
    assert not metadata.get("env_vars")
    assert is_side_effecting(module_id, metadata) is False
    assert default_for(module_id, metadata) is None
    assert read_envelope(payload) is None

    instance = ModuleRegistry.get(module_id)(
        dict(PARAMS[module_id]),
        {"resource_id": "robot-1"},
    )
    stamped = _apply_outcome_contract(instance, asyncio.run(instance.execute()))
    assert "outcome" not in stamped


@pytest.mark.parametrize("module_id", GROUP)
def test_robotics_step_never_imports_a_transport_or_ros_runtime(module_id):
    tree, path = source_tree(module_id)
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    forbidden = ("gateway", "rclpy", "nav2", "roslib", "serial", "requests", "httpx")
    assert not any(any(part in name for part in forbidden) for name in imports), path


@pytest.mark.parametrize("module_id", GROUP)
def test_missing_commanded_resource_is_an_explicit_step_failure(module_id):
    payload = run(module_id, PARAMS[module_id], {})

    assert payload["ok"] is False
    assert payload["dispatched"] is False
    assert payload["commanded_resource"] == ""
    assert payload["error"]
    assert "capability_request" not in payload
