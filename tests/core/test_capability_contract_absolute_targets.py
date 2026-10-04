# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Absolute-target evidence (2.38.0): ``distance_to`` and ``angle_to``.

Every v1 measure before 2.38.0 compared two phases, so an end state -- "it is
now at the asked place", "the car is on the asked floor" -- could not be
proven, and a provider reporting success while stopped short was believed.
These ops compare the last declared phase with a target taken from the call's
own arguments.

The verdicts in ``vectors/capability_contract_absolute_targets.json`` are the
parity set: a host that re-implements ``judge`` (Flyto2 Cloud does) must
reproduce each one exactly, so this suite pins them to this implementation.
"""

import copy
import json
import math
from pathlib import Path

import pytest

from core.capability_contract import (
    ABSOLUTE_OPS,
    ANGLE_OPS,
    judge,
    validate_contract,
    validate_evidence,
)

VECTORS = json.loads(
    (Path(__file__).parent / "vectors" / "capability_contract_absolute_targets.json").read_text()
)["cases"]

NAVIGATE_PARAMS = {
    "x": {"type": "number", "min": -1000.0, "max": 1000.0, "unit": "m", "required": True},
    "y": {"type": "number", "min": -1000.0, "max": 1000.0, "unit": "m", "required": True},
    "yaw_radians": {"type": "number", "min": -math.pi, "max": math.pi, "unit": "rad", "required": False},
    "label": {"type": "string"},
}

POSITION = {
    "kind": "arrival",
    "observe": "map_pose",
    "phases": ["after", "settled"],
    "measure": {"op": "distance_to", "fields": ["x", "y"], "frame": "map"},
    "expect": {"arguments": {"x": "x", "y": "y"}},
    "tolerance": {"absolute": 0.3},
}

HEADING = {
    "kind": "arrival.heading",
    "observe": "map_pose",
    "phases": ["after", "settled"],
    "measure": {"op": "angle_to", "fields": ["yaw"], "frame": "map"},
    "expect": {"argument": "yaw_radians", "optional": True},
    "tolerance": {"absolute": 0.3},
}


def navigate_contract(*evidence):
    return {
        "actuates": True,
        "safety_class": "movement",
        "requires_safe_stop": True,
        "cancellable": True,
        "idempotent": True,
        "effects": ["position.changed"],
        "evidence": [copy.deepcopy(item) for item in evidence],
    }


def map_pose(x, y, yaw=0.0, frame="map"):
    return {"frame": frame, "x": x, "y": y, "yaw": yaw}


# ---------------------------------------------------------------------------
# Vocabulary and normalization
# ---------------------------------------------------------------------------


def test_the_absolute_ops_are_published():
    assert ABSOLUTE_OPS == ("distance_to", "angle_to")
    assert "angle_to" in ANGLE_OPS and "distance_to" not in ANGLE_OPS


def test_a_navigate_contract_normalizes_with_its_frame_and_targets():
    contract = validate_contract(navigate_contract(POSITION, HEADING), NAVIGATE_PARAMS)
    position, heading = contract["evidence"]
    assert position["measure"] == {"op": "distance_to", "fields": ["x", "y"], "frame": "map"}
    assert position["expect"] == {"arguments": {"x": "x", "y": "y"}}
    assert position["tolerance"] == {"absolute": 0.3, "relative": 0}
    assert position["phases"] == ["after", "settled"]
    assert heading["expect"] == {"argument": "yaw_radians", "optional": True}


def test_optional_false_and_an_absent_frame_normalize_away():
    spec = copy.deepcopy(HEADING)
    spec["expect"]["optional"] = False
    del spec["measure"]["frame"]
    normalized = validate_evidence(spec, NAVIGATE_PARAMS)
    assert normalized["expect"] == {"argument": "yaw_radians"}
    assert "frame" not in normalized["measure"]


def test_a_relative_op_may_name_a_frame_and_keeps_its_old_shape_without_one():
    relative = {
        "kind": "displacement",
        "observe": "pose",
        "phases": ["before", "after"],
        "measure": {"op": "distance", "fields": ["x", "y"]},
        "expect": {"value": 0},
        "tolerance": {"absolute": 0.05},
    }
    assert validate_evidence(relative)["measure"] == {"op": "distance", "fields": ["x", "y"]}
    framed = copy.deepcopy(relative)
    framed["measure"]["frame"] = "odom"
    assert validate_evidence(framed)["measure"]["frame"] == "odom"
    unusable = judge(framed, {}, {"before": map_pose(0, 0), "after": map_pose(0, 0)})
    assert unusable["usable"] is False and unusable["reason"] == "phase 'before' is not in frame 'odom'"


def test_a_relative_op_still_requires_before():
    spec = {
        "kind": "displacement",
        "observe": "pose",
        "phases": ["after", "settled"],
        "measure": {"op": "distance", "fields": ["x", "y"]},
        "expect": {"value": 0},
        "tolerance": {"absolute": 0.05},
    }
    with pytest.raises(ValueError, match="phases must include before and after"):
        validate_evidence(spec)


def _with(base, path, value):
    spec = copy.deepcopy(base)
    target = spec
    for key in path[:-1]:
        target = target[key]
    if value is _DELETE:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return spec


_DELETE = object()


@pytest.mark.parametrize(
    "spec, message",
    [
        (_with(POSITION, ["phases"], ["before", "settled"]), "phases must include after"),
        (_with(POSITION, ["expect"], {"argument": "x"}), "expect must be {'arguments'"),
        (_with(POSITION, ["expect"], {"arguments": {"x": "x"}}), "exactly the measured fields"),
        (_with(POSITION, ["expect"], {"arguments": {"x": "x", "y": "y", "z": "x"}}), "exactly the measured fields"),
        (_with(POSITION, ["expect"], {"arguments": ["x", "y"]}), "exactly the measured fields"),
        (_with(POSITION, ["expect"], {"arguments": {"x": "x", "y": "nope"}}), "'nope' is not a key in params_schema"),
        (_with(POSITION, ["expect"], {"arguments": {"x": "x", "y": "label"}}), "must name a number or integer"),
        (_with(POSITION, ["expect"], {"arguments": {"x": "x", "y": ""}}), "must be a parameter name"),
        (_with(POSITION, ["expect"], {"arguments": {"x": "x", "y": "y"}, "scale": 2}), "expect must be {'arguments'"),
        (_with(POSITION, ["tolerance"], {"absolute": 0.3, "relative": 0.1}), "relative must be 0 for op distance_to"),
        (_with(POSITION, ["measure", "frame"], "Map Frame"), "measure.frame 'Map Frame' does not match"),
        (_with(POSITION, ["measure", "frame"], ""), "measure.frame must be a non-empty string"),
        (_with(POSITION, ["measure", "heading_field"], "yaw"), "heading_field is only allowed with op along"),
        (_with(POSITION, ["measure", "fields"], ["x", "y", "z", "w"]), "1..3 identifiers"),
        (_with(HEADING, ["measure", "fields"], ["yaw", "pitch"]), "angle_to takes exactly one field"),
        (_with(HEADING, ["expect"], {"value": 0}), "expect must be {'argument'"),
        (_with(HEADING, ["expect"], {"argument": "yaw_radians", "scale": 1}), "expect must be {'argument'"),
        (_with(HEADING, ["expect", "optional"], "yes"), "optional must be a bool"),
        (_with(HEADING, ["expect", "argument"], "x"), "optional contradicts required parameter 'x'"),
        (_with(HEADING, ["tolerance"], {"relative": 0.2}), "relative must be 0 for op angle_to"),
        (_with(_with(POSITION, ["phases"], ["after"]), ["settle"], {"max_drift": 0.02}),
         "settle requires 'settled' in phases"),
    ],
)
def test_every_absolute_rule_rejects_with_a_precise_message(spec, message):
    with pytest.raises(ValueError, match=message.replace("{", r"\{").replace("(", r"\(")):
        validate_contract(navigate_contract(spec), NAVIGATE_PARAMS)


def test_judge_without_a_schema_skips_only_the_parameter_checks():
    spec = _with(POSITION, ["expect"], {"arguments": {"x": "east", "y": "north"}})
    verdict = judge(spec, {"east": 1.0, "north": 0.0}, {"after": map_pose(1.0, 0.1), "settled": map_pose(1.0, 0.1)})
    assert verdict["usable"] is True and verdict["measured"] == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# Judgement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", VECTORS, ids=[case["name"] for case in VECTORS])
def test_the_parity_vectors(case):
    assert judge(case["spec"], case["arguments"], case["observations"]) == case["verdict"]


def test_a_success_reported_short_of_the_target_is_not_arrival():
    """The robot reported success and stopped 0.63 m before the asked place."""
    asked = {"x": 1.196, "y": -0.005, "yaw_radians": 0.0028}
    stopped = map_pose(0.566, -0.005, 0.01)
    verdict = judge(POSITION, asked, {"after": stopped, "settled": stopped})
    assert verdict["usable"] is False
    assert verdict["measured"] == pytest.approx(0.63)
    assert verdict["expected"] == 0.0 and verdict["allowed"] == 0.3
    # The heading was reached, which proves nothing about the place.
    assert judge(HEADING, asked, {"after": stopped, "settled": stopped})["usable"] is True


def test_the_arithmetic_by_hand():
    verdict = judge(POSITION, {"x": 1.0, "y": 0.0}, {"after": map_pose(9, 9), "settled": map_pose(1.02, 0.11)})
    # sqrt((1.02 - 1.0)^2 + (0.11 - 0.0)^2), on settled; after is not read.
    assert verdict["measured"] == pytest.approx(0.111803, abs=1e-6)
    assert verdict["usable"] is True and verdict["settle_drift"] is None

    heading = judge(HEADING, {"yaw_radians": 3.1}, {"after": map_pose(0, 0, -3.1), "settled": map_pose(0, 0, -3.1)})
    # error = |wrap(-3.1 - 3.1)| = 2*pi - 6.2
    assert heading["usable"] is True
    assert abs(heading["measured"] - heading["expected"] + 2 * math.pi) == pytest.approx(2 * math.pi - 6.2)


def test_a_declared_before_phase_must_be_observed_but_is_not_measured():
    spec = _with(POSITION, ["phases"], ["before", "after", "settled"])
    far_start = {"before": map_pose(50.0, 50.0), "after": map_pose(1.0, 0.0), "settled": map_pose(1.0, 0.0)}
    assert judge(spec, {"x": 1.0, "y": 0.0}, far_start)["measured"] == 0.0
    missing = {"after": map_pose(1.0, 0.0), "settled": map_pose(1.0, 0.0)}
    assert judge(spec, {"x": 1.0, "y": 0.0}, missing)["reason"] == "phase 'before' was not observed"


def test_an_optional_target_is_checked_when_given():
    asked = {"x": 0.0, "y": 0.0, "yaw_radians": 1.0}
    verdict = judge(HEADING, asked, {"after": map_pose(0, 0, 1.5), "settled": map_pose(0, 0, 1.5)})
    assert verdict["usable"] is False and verdict["expected"] == 1.0


def test_non_mapping_arguments_are_not_an_omitted_target():
    verdict = judge(HEADING, None, {"after": map_pose(0, 0, 0), "settled": map_pose(0, 0, 0)})
    assert verdict["usable"] is False
    assert verdict["reason"] == "argument 'yaw_radians' is missing or not a finite number"


def test_judge_does_not_mutate_absolute_inputs():
    spec, arguments = copy.deepcopy(POSITION), {"x": 1.0, "y": 2.0}
    observations = {"after": map_pose(1.0, 2.0), "settled": map_pose(1.0, 2.0)}
    snapshot = copy.deepcopy((spec, arguments, observations))
    judge(spec, arguments, observations)
    assert (spec, arguments, observations) == snapshot


# ---------------------------------------------------------------------------
# The generic capability host judges an arrival from the declared observation
# ---------------------------------------------------------------------------


class _NavigatingAdapter:
    """Reports success, and stops ``short`` metres before the asked x."""

    resource_id = "resource-01"
    deployment_mode = "simulation"

    def __init__(self, short):
        self.short = short
        self.at = {"x": 0.0, "y": 0.0, "yaw": 0.0}
        self.phases = []

    def observe(self, *, phase="preflight", execution_id=None):
        self.phases.append(phase)
        # Odometry and the same pose in the map frame, as an equipment adapter
        # with localization reports them; only map_pose is declared.
        return {
            "deployment_mode": self.deployment_mode,
            "pose": {"frame": "odom", **self.at},
            "map_pose": {"frame": "map", **self.at},
        }

    def invoke(self, request):
        from types import SimpleNamespace

        self.at = {"x": request.arguments["x"] - self.short, "y": request.arguments["y"], "yaw": 0.0}
        return SimpleNamespace(call_id=request.call_id, outcome="completed", detail="", evidence={})

    def cancel(self, call_id):  # pragma: no cover - never cancelled here
        raise AssertionError("not cancelled")

    def safe_stop(self):  # pragma: no cover - a completed call needs none
        raise AssertionError("not stopped")

    def disconnect(self):
        pass


@pytest.mark.parametrize("short, verified", [(0.63, False), (0.1, True)])
def test_the_capability_host_judges_arrival_from_the_map_pose(short, verified):
    import asyncio

    from core.capability_host import CapabilityHost

    contract = validate_contract(navigate_contract(POSITION, HEADING), NAVIGATE_PARAMS)
    adapter = _NavigatingAdapter(short)
    host = CapabilityHost(
        adapter_id="fake.adapter",
        resource_id="resource-01",
        adapter_factory=lambda resource_id: adapter,
        contract_lookup=lambda capability_id: (contract, None, "declared"),
        run_id="run-test",
        sleep=lambda seconds: None,
        allow=["thing.navigate"],
    )
    record = asyncio.run(host.invoke({
        "resource_id": "resource-01",
        "capability_id": "thing.navigate",
        "arguments": {"x": 1.196, "y": -0.005},
    }))
    assert record["outcome"] == "completed"
    assert "before" not in adapter.phases  # no declared spec reads it
    position, heading = record["verification"]["verdicts"]
    assert position["kind"] == "arrival" and position["measured"] == pytest.approx(short)
    assert heading["usable"] is True and heading["measured"] is None  # no heading asked
    assert record["verification"]["verified"] is verified
