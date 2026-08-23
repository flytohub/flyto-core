# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Known-answer and falsification coverage for deterministic domain solvers."""

import hashlib
import json

import pytest
from starlette.testclient import TestClient

from core.api.server import create_app
from core.capability_manifest import build_capability_manifest, compute_manifest_hash
from core.catalog.module import get_module_detail, search_modules
from core.mcp_handler import execute_module
from core.modules.registry import ModuleRegistry


def _digest(value):
    canonical = json.dumps(value["evidence"], sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _assert_generic_envelope(value):
    assert set(value) == {"receipt_version", "success", "status", "evidence_id",
                          "evidence_sha256", "evidence"}
    assert value["receipt_version"] == "flyto.execution-verification-receipt.v1"
    assert value["success"] is True
    assert value["status"] == "verified"
    assert 1 <= len(value["evidence_id"]) <= 192
    assert ".." not in value["evidence_id"] and "//" not in value["evidence_id"]
    assert value["evidence_sha256"] == _digest(value)
    json.dumps(value, allow_nan=False)


@pytest.mark.asyncio
async def test_rigid_transform_known_answer_is_deterministic_and_tamper_evident():
    params = {"point": [1, 0, 0], "rotation": [[0, -1, 0], [1, 0, 0], [0, 0, 1]],
              "translation": [10, 20, 30], "source_frame": "sensor", "target_frame": "world",
              "length_unit": "m"}
    first = await execute_module("math.rigid_transform_3d", params)
    second = await execute_module("math.rigid_transform_3d", params)
    assert first == second
    _assert_generic_envelope(first)
    assert first["evidence"]["result"]["point"] == [10.0, 21.0, 30.0]
    first["evidence"]["result"]["point"][0] = 11.0
    assert first["evidence_sha256"] != _digest(first)


@pytest.mark.asyncio
async def test_rigid_transform_rejects_every_declared_invalid_class():
    valid = {"point": [1, 0, 0], "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
             "translation": [0, 0, 0], "source_frame": "sensor", "target_frame": "world", "length_unit": "m"}
    invalid = (
        {**valid, "point": [True, 0, 0]},
        {**valid, "translation": [float("nan"), 0, 0]},
        {**valid, "point": [1, 2]},
        {**valid, "source_frame": "world"},
        {**valid, "length_unit": "cm"},
        {**valid, "rotation": [[2, 0, 0], [0, 1, 0], [0, 0, 1]]},
        {**valid, "rotation": [[-1, 0, 0], [0, 1, 0], [0, 0, 1]]},
        {**valid, "point": [10 ** 400, 0, 0]},
        {**valid, "source_frame": "x" * 97},
        {**valid, "source_frame": "unsafe frame"},
    )
    for params in invalid:
        assert (await execute_module("math.rigid_transform_3d", params))["ok"] is False


@pytest.mark.asyncio
async def test_kinematics_known_answer_and_rejections():
    params = {"x0": 1, "v0": 2, "acceleration": 3, "time": 4,
              "solve_mode": "position_and_velocity", "position_unit": "m", "velocity_unit": "m/s",
              "acceleration_unit": "m/s^2", "time_unit": "s"}
    result = await execute_module("physics.kinematics_constant_acceleration", params)
    _assert_generic_envelope(result)
    assert result["evidence"]["result"] == {"position": 33.0, "velocity": 14.0}
    assert result["evidence"]["assumptions"][0].startswith("Acceleration is constant")
    for bad in ({**params, "time": -1}, {**params, "x0": True}, {**params, "time_unit": "ms"},
                {**params, "solve_mode": "velocity"}, {**params, "x0": 10 ** 400},
                {**params, "v0": 1e308, "time": 2}):
        assert (await execute_module("physics.kinematics_constant_acceleration", bad))["ok"] is False


@pytest.mark.asyncio
async def test_ideal_dilution_known_answer_disclaimer_and_rejections():
    params = {"stock_concentration": 2, "target_concentration": 0.5, "final_volume": 1,
              "concentration_unit": "mol/L", "volume_unit": "L", "solve_mode": "stock_and_diluent_volume"}
    result = await execute_module("chemistry.ideal_dilution", params)
    _assert_generic_envelope(result)
    assert result["evidence"]["result"] == {"stock_volume": 0.25, "diluent_volume": 0.75}
    assert result["evidence"]["assumptions"][0] == "IDEAL ARITHMETIC ONLY"
    for bad in ({**params, "target_concentration": 3}, {**params, "final_volume": 0},
                {**params, "stock_concentration": float("inf")}, {**params, "target_concentration": True},
                {**params, "volume_unit": "mL"}, {**params, "solve_mode": "stock_volume"}):
        assert (await execute_module("chemistry.ideal_dilution", bad))["ok"] is False

    stable = await execute_module("chemistry.ideal_dilution", {
        **params, "stock_concentration": 1e308, "target_concentration": 1e308,
        "final_volume": 1e308,
    })
    assert stable["evidence"]["result"] == {"stock_volume": 1e308, "diluent_volume": 0.0}


def test_semantics_reach_catalog_and_hashed_manifest():
    for module_id in ("math.rigid_transform_3d", "physics.kinematics_constant_acceleration", "chemistry.ideal_dilution"):
        detail = get_module_detail(module_id)
        assert detail["provides_capability"]
        assert all(detail["semantics"].values())
        assert next(hit for hit in search_modules(module_id.replace(".", " "), limit=100)
                    if hit["module_id"] == module_id)["semantics"] == detail["semantics"]
    manifest = build_capability_manifest()
    assert manifest["hash"] == compute_manifest_hash(manifest)
    contracts = manifest["semantic_contracts"]
    assert any(contract["module_id"] == "chemistry.ideal_dilution" for contract in contracts)


def test_search_matches_composite_goal_frames_by_exact_declared_semantic_tokens():
    expectations = {
        ("solve.rigid-transform-3d transform.point-3d data.compute-only "
         "domain.solve.requested"): "math.rigid_transform_3d",
        ("solve.constant-acceleration-kinematics compute.position-velocity "
         "data.compute-only domain.solve.requested"): "physics.kinematics_constant_acceleration",
        ("solve.ideal-dilution compute.stock-diluent-volume data.compute-only "
         "domain.solve.requested"): "chemistry.ideal_dilution",
    }
    provider_ids = set(expectations.values())
    for query, module_id in expectations.items():
        results = search_modules(query, limit=100)
        assert results[0]["module_id"] == module_id
        scores = {hit["module_id"]: hit["score"] for hit in results
                  if hit["module_id"] in provider_ids}
        assert scores[module_id] > max(
            scores[other_id] for other_id in provider_ids - {module_id}
        )

    # Capability identity is carried in results but is deliberately not a
    # search authority.
    assert not any(hit["module_id"] == "math.rigid_transform_3d"
                   for hit in search_modules("domain.solve.rigid-transform-3d"))

    # These are plausible strings synthesized from display metadata, but none
    # is a declared semantic identifier and semantic matching must not invent it.
    assert not any(hit["module_id"] == "chemistry.ideal_dilution"
                   for hit in search_modules("ideal-dilution-arithmetic-authority"))


@pytest.mark.parametrize("metadata", [
    {"provides_capability": "bad capability", "semantics": {}},
    {"provides_capability": "good.capability", "semantics": {}},
    {"provides_capability": "good.capability", "semantics": {"intent_ids": ["x"]}},
    {"provides_capability": "good.capability", "semantics": {"intent_ids": ["x"], "affordances": ["a"], "effects": ["e"], "handled_events": ["h"], "unknown": ["no"]}},
    {"provides_capability": "good.capability", "semantics": {"intent_ids": ["x", "x"], "affordances": ["a"], "effects": ["e"], "handled_events": ["h"]}},
])
def test_provider_source_boundary_fails_closed_without_registry_mutation(metadata):
    before = ModuleRegistry.module_count()
    assert "test.invalid_provider" not in ModuleRegistry.get_all_metadata()
    with pytest.raises(ValueError):
        ModuleRegistry.register("test.invalid_provider", object, metadata)
    assert ModuleRegistry.module_count() == before
    with pytest.raises(ValueError):
        ModuleRegistry.get("test.invalid_provider")
    assert "test.invalid_provider" not in ModuleRegistry.get_all_metadata()


def test_execution_api_preserves_the_solver_receipt(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    from core.api import security

    monkeypatch.setattr(security, "_TOKEN_DIR", tmp_path / ".flyto")
    app = create_app()

    params = {"stock_concentration": 2, "target_concentration": 0.5, "final_volume": 1,
              "concentration_unit": "mol/L", "volume_unit": "L", "solve_mode": "stock_and_diluent_volume"}
    with TestClient(app) as client:
        response = client.post(
            "/v1/execute", json={"module_id": "chemistry.ideal_dilution", "params": params},
            headers={"Authorization": f"Bearer {security._active_token}"},
        )
    payload = response.json()
    assert payload["ok"] is True
    _assert_generic_envelope(payload["data"])
    assert payload["data"]["evidence"]["solver_schema"] == "flyto.core.domain-solver-receipt.v1"


@pytest.mark.asyncio
async def test_digest_falsification_covers_nested_evidence_and_envelope_fields():
    params = {"x0": 1, "v0": 2, "acceleration": 3, "time": 4,
              "solve_mode": "position_and_velocity", "position_unit": "m", "velocity_unit": "m/s",
              "acceleration_unit": "m/s^2", "time_unit": "s"}
    value = await execute_module("physics.kinematics_constant_acceleration", params)
    original_digest = value["evidence_sha256"]
    value["evidence"]["checks"]["finite_inputs"] = False
    assert _digest(value) != original_digest
    value["evidence_sha256"] = "0" * 64
    assert value["evidence_sha256"] != _digest(value)
