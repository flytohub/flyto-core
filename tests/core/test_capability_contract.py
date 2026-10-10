# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Capability contract ``flyto.capability-contract.v1``.

Covers the closed schema (every rule), registration through the decorator, the
raw ``ModuleRegistry.register`` path and a plugin entry point (an invalid
contract rolls the whole plugin back), the manifest's conditional ``contracts``
key, catalog detail, and the evidence arithmetic of :func:`judge` — which a
host re-implements from ``docs/CAPABILITY_CONTRACT.md`` and must match.
"""

import copy
import math

import pytest

from core import capability_manifest
from core.capability_contract import (
    CONTRACT_SCHEMA,
    MEASURE_OPS,
    PHASES,
    SAFETY_CLASSES,
    judge,
    validate_contract,
    wrap_angle,
)
from core.capability_manifest import build_capability_manifest, compute_manifest_hash
from core.catalog.module import get_module_detail
from core.modules.base import BaseModule
from core.modules.registry import ModuleRegistry, register_module
from core.modules.registry import core as registry_core

PI = math.pi

# ---------------------------------------------------------------------------
# Fixtures: a motion contract (spec section 2) and a domain-neutral one.
# ---------------------------------------------------------------------------

ADVANCE_PARAMS = {
    "distance_m": {"type": "number", "min": 0.05, "max": 2.0, "unit": "m", "required": True},
    "speed_mps": {"type": "number", "min": 0.02, "max": 0.25, "unit": "m/s", "default": 0.12},
}

DISPLACEMENT = {
    "kind": "displacement",
    "observe": "pose",
    "phases": ["before", "after", "settled"],
    "measure": {"op": "distance", "fields": ["x", "y"]},
    "expect": {"argument": "distance_m"},
    "tolerance": {"absolute": 0.03, "relative": 0.3},
    "settle": {"max_drift": 0.02},
}

ROTATION = {
    "kind": "rotation",
    "observe": "pose",
    "phases": ["before", "after"],
    "measure": {"op": "abs_angle_delta", "fields": ["yaw"]},
    "expect": {"argument": "yaw_radians"},
    "tolerance": {"absolute": 0.1, "relative": 0.2},
}

POSITION_DRIFT = {
    "kind": "position-drift",
    "observe": "pose",
    "phases": ["before", "after"],
    "measure": {"op": "distance", "fields": ["x", "y"]},
    "expect": {"value": 0},
    "tolerance": {"absolute": 0.05},
}


# Cloud parity (flyto-cloud services/space_tasks/motion_verification.py): the
# motion is projected onto the starting heading, measured before -> settled.
ALONG = {
    "kind": "displacement",
    "observe": "pose",
    "phases": ["before", "after", "settled"],
    "measure": {"op": "along", "fields": ["x", "y"], "heading_field": "yaw"},
    "expect": {"argument": "distance_m"},
    "tolerance": {"absolute": 0.03, "relative": 0.3},
    "settle": {"max_drift": 0.02},
}

RETREAT = {**ALONG, "expect": {"argument": "distance_m", "scale": -1}}

HEADING_HOLD = {
    "kind": "heading.hold",
    "observe": "pose",
    "phases": ["before", "after", "settled"],
    "measure": {"op": "abs_angle_delta", "fields": ["yaw"]},
    "expect": {"value": 0},
    "tolerance": {"absolute": 0.15},
}

SIGNED_ROTATION = {
    "kind": "rotation",
    "observe": "pose",
    "phases": ["before", "after", "settled"],
    "measure": {"op": "angle_delta", "fields": ["yaw"]},
    "expect": {"argument": "yaw_radians"},
    "tolerance": {"absolute": 0.1, "relative": 0.2},
    "settle": {"max_drift": 0.02},
}

ROTATION_DRIFT = {
    "kind": "position-drift",
    "observe": "pose",
    "phases": ["before", "after", "settled"],
    "measure": {"op": "distance", "fields": ["x", "y"]},
    "expect": {"value": 0},
    "tolerance": {"absolute": 0.05},
    "settle": {"max_drift": 0.02},
}


def advance_contract(**overrides):
    contract = {
        "actuates": True,
        "safety_class": "movement",
        "requires_safe_stop": True,
        "cancellable": True,
        "idempotent": True,
        "effects": ["position.changed"],
        "requires": ["observation.fresh"],
        "evidence": [copy.deepcopy(DISPLACEMENT)],
    }
    contract.update(overrides)
    return contract


def minimal_contract(**overrides):
    contract = {
        "actuates": False,
        "safety_class": "read_only",
        "requires_safe_stop": False,
        "cancellable": True,
        "idempotent": True,
    }
    contract.update(overrides)
    return contract


def evidence_contract(evidence, params=None):
    """An actuating contract carrying exactly one evidence spec."""
    return validate_contract(advance_contract(evidence=[evidence]), params or ADVANCE_PARAMS)


# ---------------------------------------------------------------------------
# Validation: shape and normalization
# ---------------------------------------------------------------------------


def test_vocabulary_is_the_published_one():
    assert CONTRACT_SCHEMA == "flyto.capability-contract.v1"
    assert SAFETY_CLASSES == ("read_only", "controlled", "movement", "dangerous")
    assert PHASES == ("before", "after", "settled")
    assert MEASURE_OPS == (
        "distance", "along", "delta", "angle_delta", "abs_angle_delta", "distance_to", "angle_to"
    )


def test_a_full_contract_normalizes_to_one_shape():
    normalized = validate_contract(advance_contract(), ADVANCE_PARAMS)
    assert normalized == {
        "schema": CONTRACT_SCHEMA,
        "actuates": True,
        "safety_class": "movement",
        "requires_safe_stop": True,
        "cancellable": True,
        "idempotent": True,
        "effects": ["position.changed"],
        "requires": ["observation.fresh"],
        "evidence": [{**DISPLACEMENT, "expect": {"argument": "distance_m", "scale": 1}}],
    }


def test_a_minimal_contract_gets_empty_lists_and_the_schema_id():
    normalized = validate_contract(minimal_contract(), {})
    assert normalized["schema"] == CONTRACT_SCHEMA
    assert normalized["effects"] == [] and normalized["requires"] == [] and normalized["evidence"] == []


def test_an_absent_tolerance_bound_normalizes_to_zero():
    normalized = evidence_contract(copy.deepcopy(POSITION_DRIFT))
    assert normalized["evidence"][0]["tolerance"] == {"absolute": 0.05, "relative": 0}


def test_the_normalized_contract_does_not_alias_the_input():
    source = advance_contract()
    normalized = validate_contract(source, ADVANCE_PARAMS)
    source["effects"].append("other.effect")
    source["evidence"][0]["measure"]["fields"].append("z")
    source["evidence"][0]["tolerance"]["absolute"] = 9
    assert normalized["effects"] == ["position.changed"]
    assert normalized["evidence"][0]["measure"]["fields"] == ["x", "y"]
    assert normalized["evidence"][0]["tolerance"]["absolute"] == 0.03


def test_an_explicit_matching_schema_id_is_accepted():
    assert validate_contract(minimal_contract(schema=CONTRACT_SCHEMA), {})["schema"] == CONTRACT_SCHEMA


def test_every_safety_class_is_accepted():
    for safety_class in ("controlled", "movement", "dangerous"):
        validate_contract(minimal_contract(actuates=True, safety_class=safety_class), {})
    validate_contract(minimal_contract(safety_class="read_only"), {})


def test_an_identifier_list_may_hold_sixteen_items():
    names = [f"effect.n{index}" for index in range(16)]
    assert validate_contract(minimal_contract(effects=names), {})["effects"] == names


def test_eight_evidence_items_are_accepted():
    contract = advance_contract(evidence=[copy.deepcopy(POSITION_DRIFT) for _ in range(8)])
    assert len(validate_contract(contract, ADVANCE_PARAMS)["evidence"]) == 8


# ---------------------------------------------------------------------------
# Validation: every rule, as a table of (contract, params_schema, message)
# ---------------------------------------------------------------------------


def _without(mapping, key):
    return {k: v for k, v in mapping.items() if k != key}


def _evidence(**overrides):
    item = copy.deepcopy(DISPLACEMENT)
    item.update(overrides)
    return item


REJECTED = [
    # Top level: closed key set, required keys, types.
    ("not a mapping", ["actuates"], {}, "contract must be a mapping"),
    ("unknown key", minimal_contract(bounds={}), {}, "unknown keys: bounds"),
    ("missing actuates", _without(minimal_contract(), "actuates"), {}, "missing required keys: actuates"),
    ("missing safety_class", _without(minimal_contract(), "safety_class"), {}, "missing required keys: safety_class"),
    ("missing requires_safe_stop", _without(minimal_contract(), "requires_safe_stop"), {},
     "missing required keys: requires_safe_stop"),
    ("missing cancellable", _without(minimal_contract(), "cancellable"), {}, "missing required keys: cancellable"),
    ("missing idempotent", _without(minimal_contract(), "idempotent"), {}, "missing required keys: idempotent"),
    ("wrong schema id", minimal_contract(schema="flyto.capability-contract.v2"), {}, "contract.schema must be"),
    ("int as bool", minimal_contract(actuates=1), {}, "contract.actuates must be a bool"),
    ("string as bool", minimal_contract(cancellable="true"), {}, "contract.cancellable must be a bool"),
    ("none as bool", minimal_contract(idempotent=None), {}, "contract.idempotent must be a bool"),
    ("unknown safety class", minimal_contract(safety_class="harmless"), {}, "contract.safety_class must be one of"),
    ("safety class not a string", minimal_contract(safety_class=1), {}, "contract.safety_class must be one of"),
    ("read_only that actuates", minimal_contract(actuates=True), {}, "read_only contradicts actuates"),
    # Identifier lists.
    ("effects not a list", minimal_contract(effects="position.changed"), {}, "contract.effects must be a list"),
    ("effects too long", minimal_contract(effects=[f"e.n{i}" for i in range(17)]), {}, "must hold 0..16"),
    ("requires too long", minimal_contract(requires=[f"r.n{i}" for i in range(17)]), {}, "contract.requires must hold"),
    ("duplicate effect", minimal_contract(effects=["a.b", "a.b"]), {}, "duplicate identifiers"),
    ("uppercase identifier", minimal_contract(effects=["Position.changed"]), {}, "identifier grammar"),
    ("leading digit", minimal_contract(effects=["1position"]), {}, "identifier grammar"),
    ("trailing separator", minimal_contract(effects=["position."]), {}, "identifier grammar"),
    ("double separator", minimal_contract(requires=["a..b"]), {}, "identifier grammar"),
    ("space", minimal_contract(requires=["a b"]), {}, "identifier grammar"),
    ("too long identifier", minimal_contract(effects=["a" * 97]), {}, "longer than 96"),
    ("non-string identifier", minimal_contract(effects=[1]), {}, "non-empty string identifier"),
    ("empty identifier", minimal_contract(effects=[""]), {}, "non-empty string identifier"),
    # Evidence list.
    ("evidence not a list", advance_contract(evidence=DISPLACEMENT), ADVANCE_PARAMS, "contract.evidence must be a list"),
    ("nine evidence items", advance_contract(evidence=[copy.deepcopy(POSITION_DRIFT)] * 9), ADVANCE_PARAMS,
     "at most 8"),
    ("evidence item not a mapping", advance_contract(evidence=["displacement"]), ADVANCE_PARAMS,
     "contract.evidence[0] must be a mapping"),
    ("evidence unknown key", advance_contract(evidence=[_evidence(weight=1)]), ADVANCE_PARAMS, "unknown keys: weight"),
    *[
        (f"evidence missing {key}", advance_contract(evidence=[_without(DISPLACEMENT, key)]), ADVANCE_PARAMS,
         f"missing required keys: {key}")
        for key in ("kind", "observe", "phases", "measure", "expect", "tolerance")
    ],
    ("bad kind", advance_contract(evidence=[_evidence(kind="Displacement")]), ADVANCE_PARAMS,
     "contract.evidence[0].kind"),
    ("bad observe", advance_contract(evidence=[_evidence(observe="pose!")]), ADVANCE_PARAMS,
     "contract.evidence[0].observe"),
    # Phases.
    ("phases empty", advance_contract(evidence=[_evidence(phases=[])]), ADVANCE_PARAMS, "phases must be a non-empty list"),
    ("phases unknown", advance_contract(evidence=[_evidence(phases=["before", "during"])]), ADVANCE_PARAMS,
     "phases may only contain"),
    ("phases duplicate", advance_contract(evidence=[_evidence(phases=["before", "after", "after"])]), ADVANCE_PARAMS,
     "phases contains duplicates"),
    ("phases out of order", advance_contract(evidence=[_evidence(phases=["after", "before", "settled"])]),
     ADVANCE_PARAMS, "ordered before, after, settled"),
    ("phases without before", advance_contract(evidence=[_evidence(phases=["after", "settled"])]), ADVANCE_PARAMS,
     "must include before and after"),
    ("phases without after", advance_contract(evidence=[_evidence(phases=["before", "settled"])]), ADVANCE_PARAMS,
     "must include before and after"),
    # Measure.
    ("measure not a mapping", advance_contract(evidence=[_evidence(measure="distance")]), ADVANCE_PARAMS,
     "measure must be a mapping"),
    ("measure unknown key", advance_contract(evidence=[_evidence(measure={"op": "distance", "fields": ["x"], "unit": "m"})]),
     ADVANCE_PARAMS, "measure has unknown keys: unit"),
    ("measure unknown op", advance_contract(evidence=[_evidence(measure={"op": "ratio", "fields": ["x"]})]),
     ADVANCE_PARAMS, "measure.op must be one of"),
    ("measure no fields", advance_contract(evidence=[_evidence(measure={"op": "distance", "fields": []})]),
     ADVANCE_PARAMS, "must hold 1..3"),
    ("measure four fields", advance_contract(evidence=[_evidence(measure={"op": "distance", "fields": ["w", "x", "y", "z"]})]),
     ADVANCE_PARAMS, "must hold 1..3"),
    ("measure duplicate field", advance_contract(evidence=[_evidence(measure={"op": "distance", "fields": ["x", "x"]})]),
     ADVANCE_PARAMS, "duplicate identifiers"),
    ("measure bad field", advance_contract(evidence=[_evidence(measure={"op": "distance", "fields": ["X"]})]),
     ADVANCE_PARAMS, "identifier grammar"),
    *[
        (f"{op} with two fields", advance_contract(evidence=[_evidence(measure={"op": op, "fields": ["x", "y"]})]),
         ADVANCE_PARAMS, f"op {op} takes exactly one field")
        for op in ("delta", "angle_delta", "abs_angle_delta")
    ],
    ("along with one field", advance_contract(evidence=[_evidence(
        measure={"op": "along", "fields": ["x"], "heading_field": "yaw"})]), ADVANCE_PARAMS,
     "op along takes exactly two position fields"),
    ("along with three fields", advance_contract(evidence=[_evidence(
        measure={"op": "along", "fields": ["x", "y", "z"], "heading_field": "yaw"})]), ADVANCE_PARAMS,
     "op along takes exactly two position fields"),
    ("along without heading_field", advance_contract(evidence=[_evidence(
        measure={"op": "along", "fields": ["x", "y"]})]), ADVANCE_PARAMS, "op along requires heading_field"),
    ("along bad heading_field", advance_contract(evidence=[_evidence(
        measure={"op": "along", "fields": ["x", "y"], "heading_field": "Yaw"})]), ADVANCE_PARAMS,
     "measure.heading_field"),
    ("along heading is a position field", advance_contract(evidence=[_evidence(
        measure={"op": "along", "fields": ["x", "y"], "heading_field": "x"})]), ADVANCE_PARAMS,
     "heading_field must not be one of the position fields"),
    *[
        (f"heading_field with {op}", advance_contract(evidence=[_evidence(
            measure={"op": op, "fields": ["x"], "heading_field": "yaw"})]), ADVANCE_PARAMS,
         "heading_field is only allowed with op along")
        for op in ("distance", "delta", "angle_delta", "abs_angle_delta")
    ],
    # Expect.
    ("expect scale zero", advance_contract(evidence=[_evidence(expect={"argument": "distance_m", "scale": 0})]),
     ADVANCE_PARAMS, "expect.scale must be a finite non-zero number"),
    ("expect scale nan", advance_contract(evidence=[_evidence(expect={"argument": "distance_m", "scale": math.nan})]),
     ADVANCE_PARAMS, "expect.scale must be a finite non-zero number"),
    ("expect scale bool", advance_contract(evidence=[_evidence(expect={"argument": "distance_m", "scale": True})]),
     ADVANCE_PARAMS, "expect.scale must be a finite non-zero number"),
    ("expect scale with value", advance_contract(evidence=[_evidence(expect={"value": 0, "scale": -1})]),
     ADVANCE_PARAMS, "expect must be exactly one of"),
    ("expect both", advance_contract(evidence=[_evidence(expect={"argument": "distance_m", "value": 1})]),
     ADVANCE_PARAMS, "expect must be exactly one of"),
    ("expect neither", advance_contract(evidence=[_evidence(expect={})]), ADVANCE_PARAMS, "expect must be exactly one of"),
    ("expect unknown key", advance_contract(evidence=[_evidence(expect={"parameter": "distance_m"})]), ADVANCE_PARAMS,
     "expect must be exactly one of"),
    ("expect argument not in schema", advance_contract(evidence=[_evidence(expect={"argument": "metres"})]),
     ADVANCE_PARAMS, "'metres' is not a key in params_schema"),
    ("expect argument not numeric", advance_contract(evidence=[_evidence(expect={"argument": "label"})]),
     {**ADVANCE_PARAMS, "label": {"type": "string"}}, "must name a number or integer parameter"),
    ("expect argument empty", advance_contract(evidence=[_evidence(expect={"argument": ""})]), ADVANCE_PARAMS,
     "expect.argument must be a parameter name"),
    ("expect value nan", advance_contract(evidence=[_evidence(expect={"value": math.nan})]), ADVANCE_PARAMS,
     "expect.value must be a finite number"),
    ("expect value inf", advance_contract(evidence=[_evidence(expect={"value": math.inf})]), ADVANCE_PARAMS,
     "expect.value must be a finite number"),
    ("expect value bool", advance_contract(evidence=[_evidence(expect={"value": True})]), ADVANCE_PARAMS,
     "expect.value must be a finite number"),
    ("expect value string", advance_contract(evidence=[_evidence(expect={"value": "1"})]), ADVANCE_PARAMS,
     "expect.value must be a finite number"),
    # Tolerance.
    ("tolerance empty", advance_contract(evidence=[_evidence(tolerance={})]), ADVANCE_PARAMS,
     "tolerance must be a mapping"),
    ("tolerance unknown key", advance_contract(evidence=[_evidence(tolerance={"absolute": 1, "percent": 2})]),
     ADVANCE_PARAMS, "tolerance has unknown keys: percent"),
    ("tolerance negative", advance_contract(evidence=[_evidence(tolerance={"absolute": -0.01})]), ADVANCE_PARAMS,
     "tolerance.absolute must be a finite non-negative number"),
    ("tolerance nan", advance_contract(evidence=[_evidence(tolerance={"relative": math.nan})]), ADVANCE_PARAMS,
     "tolerance.relative must be a finite non-negative number"),
    ("tolerance bool", advance_contract(evidence=[_evidence(tolerance={"absolute": True})]), ADVANCE_PARAMS,
     "tolerance.absolute must be a finite non-negative number"),
    # Settle.
    ("settle not a mapping", advance_contract(evidence=[_evidence(settle=0.02)]), ADVANCE_PARAMS,
     "settle must be a mapping"),
    ("settle unknown key", advance_contract(evidence=[_evidence(settle={"max_drift": 0.02, "window_s": 1})]),
     ADVANCE_PARAMS, "settle has unknown keys: window_s"),
    ("settle missing drift", advance_contract(evidence=[_evidence(settle={})]), ADVANCE_PARAMS,
     "settle is missing required keys: max_drift"),
    ("settle negative", advance_contract(evidence=[_evidence(settle={"max_drift": -1})]), ADVANCE_PARAMS,
     "max_drift must be a finite non-negative number"),
    ("settle without settled phase", advance_contract(evidence=[_evidence(phases=["before", "after"])]), ADVANCE_PARAMS,
     "settle requires 'settled' in phases"),
    # Parameter bounds of an actuating contract.
    ("actuating number without max", advance_contract(evidence=[]),
     {"distance_m": {"type": "number", "min": 0.05}}, "params_schema.distance_m"),
    ("actuating number without min", advance_contract(evidence=[]),
     {"distance_m": {"type": "number", "max": 2.0}}, "must declare finite 'min' and 'max'"),
    ("actuating integer without bounds", advance_contract(evidence=[]),
     {"floor": {"type": "integer"}}, "params_schema.floor"),
    ("actuating bool bound", advance_contract(evidence=[]),
     {"floor": {"type": "integer", "min": False, "max": 10}}, "params_schema.floor"),
    ("actuating infinite bound", advance_contract(evidence=[]),
     {"floor": {"type": "integer", "min": 0, "max": math.inf}}, "params_schema.floor"),
    ("actuating min above max", advance_contract(evidence=[]),
     {"floor": {"type": "integer", "min": 10, "max": 0}}, "'min' is greater than 'max'"),
    ("params_schema not a mapping", minimal_contract(), ["distance_m"], "params_schema must be a mapping"),
    ("params_schema not JSON", minimal_contract(), {"x": {"type": "number", "default": object()}},
     "params_schema must be JSON-serializable"),
    ("params_schema with nan", minimal_contract(), {"x": {"type": "number", "default": math.nan}},
     "params_schema must be JSON-serializable"),
]


@pytest.mark.parametrize(
    "contract, params_schema, message",
    [case[1:] for case in REJECTED],
    ids=[case[0] for case in REJECTED],
)
def test_every_rule_rejects_with_a_precise_message(contract, params_schema, message):
    with pytest.raises(ValueError) as caught:
        validate_contract(contract, params_schema)
    assert message in str(caught.value)


def test_bounds_are_not_required_when_the_contract_does_not_actuate():
    validate_contract(minimal_contract(), {"limit": {"type": "integer"}, "query": {"type": "string"}})


def test_bounds_are_only_required_of_numeric_parameters():
    validate_contract(
        advance_contract(evidence=[]),
        {"mode": {"type": "string"}, "enabled": {"type": "boolean"}, "floor": {"type": "integer", "min": 0, "max": 40}},
    )


def test_a_missing_params_schema_is_an_empty_one():
    validate_contract(advance_contract(evidence=[]), None)
    with pytest.raises(ValueError, match="not a key in params_schema"):
        validate_contract(advance_contract(), None)


def test_a_dict_subclass_is_not_a_contract():
    class Sneaky(dict):
        pass

    with pytest.raises(ValueError, match="contract must be a mapping"):
        validate_contract(Sneaky(minimal_contract()), {})


# ---------------------------------------------------------------------------
# judge(): the arithmetic every host must reproduce
# ---------------------------------------------------------------------------


def pose(x=0.0, y=0.0, yaw=0.0):
    return {"x": x, "y": y, "yaw": yaw}


@pytest.mark.parametrize(
    "angle, wrapped",
    [
        (0.0, 0.0),
        (PI, PI),
        (-PI, PI),
        (3 * PI, PI),
        (-3 * PI, PI),
        (2 * PI, 0.0),
        (PI + 0.1, -PI + 0.1),
        (-PI - 0.1, PI - 0.1),
        (7.0, 7.0 - 2 * PI),
    ],
)
def test_wrap_angle_lands_in_the_half_open_interval(angle, wrapped):
    result = wrap_angle(angle)
    assert -PI < result <= PI
    assert result == pytest.approx(wrapped, abs=1e-12)


# (name, spec, arguments, observations, usable, measured, expected, allowed, settle_drift)
JUDGED = [
    # Displacement, spec section 2: allowed = max(0.03, 0.3 * d), settle 0.02.
    ("advance exact", DISPLACEMENT, {"distance_m": 0.10},
     {"before": pose(), "after": pose(0.10), "settled": pose(0.10)}, True, 0.10, 0.10, 0.03, 0.0),
    ("advance measured to settled, not after", DISPLACEMENT, {"distance_m": 0.10},
     {"before": pose(), "after": pose(0.119), "settled": pose(0.12)}, True, 0.12, 0.10, 0.03, 0.001),
    ("advance short by more than the floor", DISPLACEMENT, {"distance_m": 0.10},
     {"before": pose(), "after": pose(0.065), "settled": pose(0.065)}, False, 0.065, 0.10, 0.03, 0.0),
    ("advance diagonal 3-4-5", DISPLACEMENT, {"distance_m": 0.5},
     {"before": pose(1.0, 1.0), "after": pose(1.3, 1.4), "settled": pose(1.3, 1.4)}, True, 0.5, 0.5, 0.15, 0.0),
    ("advance relative bound wins", DISPLACEMENT, {"distance_m": 2.0},
     {"before": pose(), "after": pose(2.55), "settled": pose(2.55)}, True, 2.55, 2.0, 0.6, 0.0),
    ("advance beyond relative bound", DISPLACEMENT, {"distance_m": 2.0},
     {"before": pose(), "after": pose(2.65), "settled": pose(2.65)}, False, 2.65, 2.0, 0.6, 0.0),
    ("advance settle drift too large", DISPLACEMENT, {"distance_m": 0.5},
     {"before": pose(), "after": pose(0.5), "settled": pose(0.5, 0.03)}, False, math.hypot(0.5, 0.03), 0.5, 0.15, 0.03),
    ("advance settle drift at the bound", DISPLACEMENT, {"distance_m": 0.5},
     {"before": pose(), "after": pose(0.5), "settled": pose(0.5, 0.02)}, True, math.hypot(0.5, 0.02), 0.5, 0.15, 0.02),
    # Rotation: allowed = max(0.1, 0.2 * |yaw|), abs of the argument.
    ("rotate +pi/2", ROTATION, {"yaw_radians": PI / 2},
     {"before": pose(yaw=0.0), "after": pose(yaw=PI / 2)}, True, PI / 2, PI / 2, 0.2 * PI / 2, None),
    ("rotate -pi/2 compares magnitudes", ROTATION, {"yaw_radians": -PI / 2},
     {"before": pose(yaw=0.0), "after": pose(yaw=-1.5)}, True, 1.5, PI / 2, 0.2 * PI / 2, None),
    ("rotate across the wrap", ROTATION, {"yaw_radians": 0.5},
     {"before": pose(yaw=3.0), "after": pose(yaw=3.5 - 2 * PI)}, True, 0.5, 0.5, 0.1, None),
    ("rotate small uses the floor", ROTATION, {"yaw_radians": 0.2},
     {"before": pose(yaw=1.0), "after": pose(yaw=1.35)}, False, 0.35, 0.2, 0.1, None),
    ("rotate pi reached the other way round", ROTATION, {"yaw_radians": PI},
     {"before": pose(yaw=0.0), "after": pose(yaw=-3.1)}, True, 3.1, PI, 0.2 * PI, None),
    ("rotation position drift within 0.05", POSITION_DRIFT, {},
     {"before": pose(), "after": pose(0.03, 0.04)}, True, 0.05, 0.0, 0.05, None),
    ("rotation position drift beyond 0.05", POSITION_DRIFT, {},
     {"before": pose(), "after": pose(0.04, 0.04)}, False, math.hypot(0.04, 0.04), 0.0, 0.05, None),
    # Signed ops.
    ("delta signed", {**POSITION_DRIFT, "measure": {"op": "delta", "fields": ["level"]},
                      "expect": {"value": -3}, "tolerance": {"absolute": 0.5}},
     {}, {"before": {"level": 10}, "after": {"level": 7}}, True, -3.0, -3.0, 0.5, None),
    ("delta wrong sign", {**POSITION_DRIFT, "measure": {"op": "delta", "fields": ["level"]},
                          "expect": {"value": -3}, "tolerance": {"absolute": 0.5}},
     {}, {"before": {"level": 7}, "after": {"level": 10}}, False, 3.0, -3.0, 0.5, None),
    ("angle_delta error wraps", {**ROTATION, "measure": {"op": "angle_delta", "fields": ["yaw"]},
                                 "tolerance": {"absolute": 0.1}},
     {"yaw_radians": PI}, {"before": pose(yaw=0.0), "after": pose(yaw=-PI + 0.05)}, True, -PI + 0.05, PI, 0.1, None),
    # Cloud parity cases (motion_verification.py constants).
    ("cloud advance 0.10, along 0.119 to settled", ALONG, {"distance_m": 0.10},
     {"before": pose(0, 0, 0), "after": pose(0.119, 0, 0.02), "settled": pose(0.119, 0, 0.02)},
     True, 0.119, 0.10, 0.03, 0.0),
    ("cloud advance heading held within 0.15", HEADING_HOLD, {},
     {"before": pose(0, 0, 0), "after": pose(0.119, 0, 0.02), "settled": pose(0.119, 0, 0.02)},
     True, 0.02, 0.0, 0.15, None),
    ("cloud heading changed 0.2 is not held", HEADING_HOLD, {},
     {"before": pose(0, 0, 0), "after": pose(0.1, 0, 0.2), "settled": pose(0.1, 0, 0.2)},
     False, 0.2, 0.0, 0.15, None),
    ("cloud retreat 0.2, along -0.19", RETREAT, {"distance_m": 0.2},
     {"before": pose(0, 0, 0), "after": pose(-0.19, 0, 0), "settled": pose(-0.19, 0, 0)},
     True, -0.19, -0.2, 0.06, 0.0),
    ("cloud retreat that went forward", RETREAT, {"distance_m": 0.2},
     {"before": pose(0, 0, 0), "after": pose(0.19, 0, 0), "settled": pose(0.19, 0, 0)},
     False, 0.19, -0.2, 0.06, 0.0),
    ("cloud along follows the starting heading", ALONG, {"distance_m": 0.5},
     {"before": pose(1, 1, PI / 2), "after": pose(1.02, 1.5, PI / 2), "settled": pose(1.02, 1.5, PI / 2)},
     True, 0.5, 0.5, 0.15, 0.0),
    ("cloud sideways slide is not progress", ALONG, {"distance_m": 0.5},
     {"before": pose(0, 0, PI / 2), "after": pose(0.5, 0, PI / 2), "settled": pose(0.5, 0, PI / 2)},
     False, 0.0, 0.5, 0.15, 0.0),
    ("cloud settle drift 0.03", ALONG, {"distance_m": 0.10},
     {"before": pose(0, 0, 0), "after": pose(0.10, 0, 0), "settled": pose(0.10, 0.03, 0)},
     False, 0.10, 0.10, 0.03, 0.03),
    ("cloud rotate across pi, asked 0.0832", SIGNED_ROTATION, {"yaw_radians": 0.0832},
     {"before": pose(yaw=3.10), "after": pose(yaw=-3.10), "settled": pose(yaw=-3.10)},
     True, wrap_angle(-6.2), 0.0832, 0.1, 0.0),
    ("cloud rotate across pi, asked 1.5708", SIGNED_ROTATION, {"yaw_radians": 1.5708},
     {"before": pose(yaw=3.10), "after": pose(yaw=-3.10), "settled": pose(yaw=-3.10)},
     False, wrap_angle(-6.2), 1.5708, 0.2 * 1.5708, 0.0),
    ("cloud rotate -3.0 wraps the error", SIGNED_ROTATION, {"yaw_radians": -3.0},
     {"before": pose(yaw=0.2), "after": pose(yaw=3.4 - 2 * PI), "settled": pose(yaw=3.4 - 2 * PI)},
     True, 3.2 - 2 * PI, -3.0, 0.6, 0.0),
    ("cloud drift 0.06 m during rotate", ROTATION_DRIFT, {},
     {"before": pose(), "after": pose(0.06, 0, 1.0), "settled": pose(0.06, 0, 1.0)},
     False, 0.06, 0.0, 0.05, 0.0),
    ("cloud rotate settled 0.03 later", SIGNED_ROTATION, {"yaw_radians": 1.0},
     {"before": pose(yaw=0.0), "after": pose(yaw=1.0), "settled": pose(yaw=1.03)},
     False, 1.03, 1.0, 0.2, 0.03),
    ("angle_delta wrong direction", {**ROTATION, "measure": {"op": "angle_delta", "fields": ["yaw"]},
                                     "tolerance": {"absolute": 0.1}},
     {"yaw_radians": -1.0}, {"before": pose(yaw=0.0), "after": pose(yaw=1.0)}, False, 1.0, -1.0, 0.1, None),
]


@pytest.mark.parametrize(
    "spec, arguments, observations, usable, measured, expected, allowed, settle_drift",
    [case[1:] for case in JUDGED],
    ids=[case[0] for case in JUDGED],
)
def test_judge_arithmetic(spec, arguments, observations, usable, measured, expected, allowed, settle_drift):
    verdict = judge(spec, arguments, observations)
    assert set(verdict) == {"usable", "measured", "expected", "allowed", "settle_drift", "reason"}
    assert verdict["usable"] is usable, verdict["reason"]
    assert verdict["measured"] == pytest.approx(measured, abs=1e-9)
    assert verdict["expected"] == pytest.approx(expected, abs=1e-12)
    assert verdict["allowed"] == pytest.approx(allowed, abs=1e-12)
    if settle_drift is None:
        assert verdict["settle_drift"] is None
    else:
        assert verdict["settle_drift"] == pytest.approx(settle_drift, abs=1e-9)
    assert isinstance(verdict["reason"], str) and verdict["reason"]


@pytest.mark.parametrize(
    "spec, arguments, observations, reason",
    [
        (DISPLACEMENT, {"distance_m": 0.1}, {"after": pose(0.1), "settled": pose(0.1)}, "phase 'before' was not observed"),
        (DISPLACEMENT, {"distance_m": 0.1}, {"before": pose(), "settled": pose(0.1)}, "phase 'after' was not observed"),
        (DISPLACEMENT, {"distance_m": 0.1}, {"before": pose(), "after": pose(0.1)}, "phase 'settled' was not observed"),
        (DISPLACEMENT, {"distance_m": 0.1}, {"before": {"x": 0.0}, "after": pose(0.1), "settled": pose(0.1)},
         "phase 'before' has no finite numeric field 'y'"),
        (DISPLACEMENT, {"distance_m": 0.1}, {"before": pose(), "after": pose(math.nan), "settled": pose(0.1)},
         "phase 'after' has no finite numeric field 'x'"),
        (DISPLACEMENT, {"distance_m": 0.1}, {"before": pose(), "after": {"x": True, "y": 0}, "settled": pose()},
         "phase 'after' has no finite numeric field 'x'"),
        (DISPLACEMENT, {"distance_m": 0.1}, {"before": pose(), "after": {"x": "0.1", "y": 0}, "settled": pose()},
         "phase 'after' has no finite numeric field 'x'"),
        (DISPLACEMENT, {"distance_m": 0.1}, {"before": "here", "after": pose(0.1), "settled": pose(0.1)},
         "phase 'before' was not observed"),
        (DISPLACEMENT, {}, {"before": pose(), "after": pose(0.1), "settled": pose(0.1)},
         "argument 'distance_m' is missing or not a finite number"),
        (DISPLACEMENT, {"distance_m": "0.1"}, {"before": pose(), "after": pose(0.1), "settled": pose(0.1)},
         "argument 'distance_m' is missing or not a finite number"),
        (DISPLACEMENT, {"distance_m": math.inf}, {"before": pose(), "after": pose(0.1), "settled": pose(0.1)},
         "argument 'distance_m' is missing or not a finite number"),
        (DISPLACEMENT, {"distance_m": 0.1}, None, "observations must be a mapping"),
        (ALONG, {"distance_m": 0.1},
         {"before": {"x": 0.0, "y": 0.0}, "after": pose(0.1), "settled": pose(0.1)},
         "phase 'before' has no finite numeric field 'yaw'"),
    ],
)
def test_missing_data_is_an_unusable_verdict_with_a_reason(spec, arguments, observations, reason):
    verdict = judge(spec, arguments, observations)
    assert verdict["usable"] is False
    assert reason in verdict["reason"]
    assert verdict["measured"] is None


def test_an_undeclared_settled_phase_is_not_required_or_judged():
    verdict = judge(ROTATION, {"yaw_radians": 1.0}, {"before": pose(), "after": pose(yaw=1.0)})
    assert verdict["usable"] is True and verdict["settle_drift"] is None


def test_along_reads_the_heading_from_before_only():
    verdict = judge(ALONG, {"distance_m": 0.1},
                    {"before": pose(0, 0, 0), "after": {"x": 0.1, "y": 0.0}, "settled": {"x": 0.1, "y": 0.0}})
    assert verdict["usable"] is True and verdict["measured"] == pytest.approx(0.1)


def test_scale_applies_before_abs_for_abs_angle_delta():
    spec = {**ROTATION, "expect": {"argument": "yaw_radians", "scale": -2}}
    verdict = judge(spec, {"yaw_radians": 0.5}, {"before": pose(yaw=0.0), "after": pose(yaw=-1.0)})
    assert verdict["expected"] == 1.0 and verdict["usable"] is True


def test_extra_phases_and_fields_are_ignored():
    verdict = judge(
        POSITION_DRIFT, {},
        {"before": {**pose(), "frame": "odom"}, "after": pose(0.01), "settled": pose(5.0), "during": pose(9)},
    )
    assert verdict["usable"] is True


def test_judge_refuses_a_malformed_spec():
    with pytest.raises(ValueError, match="measure.op must be one of"):
        judge({**DISPLACEMENT, "measure": {"op": "ratio", "fields": ["x"]}}, {"distance_m": 1}, {})


def test_judge_does_not_mutate_its_inputs():
    spec, arguments = copy.deepcopy(DISPLACEMENT), {"distance_m": 0.1}
    observations = {"before": pose(), "after": pose(0.1), "settled": pose(0.1)}
    snapshot = copy.deepcopy((spec, arguments, observations))
    judge(spec, arguments, observations)
    assert (spec, arguments, observations) == snapshot


# ---------------------------------------------------------------------------
# Registration: decorator, raw register(), plugin entry point
# ---------------------------------------------------------------------------


@pytest.fixture
def scratch_ids():
    """Module ids a test registers into the live registry, removed afterwards."""
    ids = []
    yield ids
    for module_id in ids:
        if ModuleRegistry.has(module_id):
            ModuleRegistry.unregister(module_id)
    capability_manifest._cached = None
    capability_manifest._cached_generation = -1


def _decorate(module_id, **kwargs):
    options = {
        "module_id": module_id,
        "version": "1.0.0",
        "category": "lift",
        "label": "Move lift to floor",
        "description": "Move a lift car to a floor and report where it stopped",
        "can_receive_from": ["*"],
        "can_connect_to": ["*"],
        "provides_capability": "lift.move_to_floor",
        "params_schema": {"floor": {"type": "integer", "min": 0, "max": 40, "required": True}},
        "contract": lift_contract(),
    }
    options.update(kwargs)

    @register_module(**options)
    async def module(context):
        return {"ok": True, "data": {}}

    return module


def lift_contract():
    return {
        "actuates": True,
        "safety_class": "movement",
        "requires_safe_stop": True,
        "cancellable": True,
        "idempotent": True,
        "effects": ["lift.floor-changed"],
        "requires": ["lift.doors-closed"],
        "evidence": [{
            "kind": "floor-reached",
            "observe": "lift-position",
            "phases": ["before", "after"],
            "measure": {"op": "delta", "fields": ["floor"]},
            "expect": {"argument": "floor"},
            "tolerance": {"absolute": 0},
        }],
    }


def test_the_decorator_stores_the_normalized_contract(scratch_ids):
    scratch_ids.append("lift.test_move_to_floor")
    _decorate("lift.test_move_to_floor")
    stored = ModuleRegistry.get_metadata("lift.test_move_to_floor")["contract"]
    assert stored == validate_contract(lift_contract(), {"floor": {"type": "integer", "min": 0, "max": 40}})
    assert stored["schema"] == CONTRACT_SCHEMA


def test_a_module_without_a_contract_has_no_contract_key(scratch_ids):
    scratch_ids.append("lift.test_plain")
    _decorate("lift.test_plain", contract=None, provides_capability=None)
    assert "contract" not in ModuleRegistry.get_metadata("lift.test_plain")


def test_the_decorator_requires_provides_capability(scratch_ids):
    scratch_ids.append("lift.test_no_capability")
    with pytest.raises(ValueError, match="'contract' requires 'provides_capability'"):
        _decorate("lift.test_no_capability", provides_capability=None)
    assert not ModuleRegistry.has("lift.test_no_capability")


def test_the_decorator_refuses_an_invalid_contract(scratch_ids):
    scratch_ids.append("lift.test_unbounded")
    with pytest.raises(ValueError, match="invalid capability contract: params_schema.floor"):
        _decorate("lift.test_unbounded", params_schema={"floor": {"type": "integer", "required": True}})
    assert not ModuleRegistry.has("lift.test_unbounded")


class _Module(BaseModule):
    async def execute(self):  # pragma: no cover - never executed here
        return {}


def _raw_metadata(module_id, capability="inventory.adjust", contract=None, params_schema=None):
    metadata = {
        "module_id": module_id,
        "category": module_id.split(".")[0],
        "stability": "stable",
        "ui_label": module_id,
        "ui_description": "adjusts stock on hand",
        "provides_capability": capability,
        "params_schema": params_schema if params_schema is not None else {
            "quantity": {"type": "integer", "min": -1000, "max": 1000},
        },
    }
    if contract is not None:
        metadata["contract"] = contract
    return metadata


def inventory_contract():
    return {
        "actuates": True,
        "safety_class": "controlled",
        "requires_safe_stop": False,
        "cancellable": False,
        "idempotent": True,
        "effects": ["inventory.changed"],
        "evidence": [{
            "kind": "stock-adjusted",
            "observe": "stock-level",
            "phases": ["before", "after"],
            "measure": {"op": "delta", "fields": ["on-hand"]},
            "expect": {"argument": "quantity"},
            "tolerance": {"absolute": 0},
        }],
    }


def test_register_validates_and_normalizes_a_raw_contract(scratch_ids):
    scratch_ids.append("inventory.test_adjust")
    source = inventory_contract()
    ModuleRegistry.register("inventory.test_adjust", _Module, _raw_metadata("inventory.test_adjust", contract=source))
    stored = ModuleRegistry.get_metadata("inventory.test_adjust")["contract"]
    assert stored["schema"] == CONTRACT_SCHEMA and stored["requires"] == []
    source["effects"].append("inventory.lost")
    assert ModuleRegistry.get_metadata("inventory.test_adjust")["contract"]["effects"] == ["inventory.changed"]


@pytest.mark.parametrize(
    "capability, contract, params_schema, message",
    [
        ("", inventory_contract(), None, "capability contracts require provides_capability"),
        ("inventory.adjust", {**inventory_contract(), "priority": 1}, None, "unknown keys: priority"),
        ("inventory.adjust", inventory_contract(), {"quantity": {"type": "integer"}}, "params_schema.quantity"),
        ("inventory.adjust", None, None, "contract must be a mapping"),
    ],
)
def test_register_refuses_an_invalid_raw_contract(scratch_ids, capability, contract, params_schema, message):
    scratch_ids.append("inventory.test_refused")
    metadata = _raw_metadata("inventory.test_refused", capability=capability, params_schema=params_schema)
    metadata["contract"] = contract
    with pytest.raises(ValueError, match=message):
        ModuleRegistry.register("inventory.test_refused", _Module, metadata)
    assert not ModuleRegistry.has("inventory.test_refused")


# Plugin path. Entry points are described, not installed, through the seam
# `_iter_entry_points` reads (same technique as test_capability_manifest.py).

_REGISTRY_STATE = (
    "_modules", "_metadata", "_plugins", "_initialized", "_loading_plugin", "_discovering",
    "_discovery_thread", "_plugin_contributions", "_core_baseline", "_pass_registered",
    "_pass_displaced", "_pass_touched", "_cleared", "_started_empty",
)


class _Groups(list):
    def get(self, group, default=None):
        return list(self)


class _EntryPoint:
    def __init__(self, name, register):
        self.name = name
        self.value = f"{name}_pkg:register_all"
        self._register = register

    def load(self):
        return self._register


@pytest.fixture
def plugins(monkeypatch):
    saved = {}
    for name in _REGISTRY_STATE:
        value = getattr(ModuleRegistry, name)
        saved[name] = value.copy() if hasattr(value, "copy") else value

    def install(*eps):
        monkeypatch.setattr(registry_core, "entry_points", lambda **kw: _Groups(eps), raising=False)
        ModuleRegistry._modules = {}
        ModuleRegistry._metadata = {}
        ModuleRegistry._plugins = {}
        ModuleRegistry._plugin_contributions = {}
        ModuleRegistry._core_baseline = {}
        ModuleRegistry._pass_registered = None
        ModuleRegistry._pass_touched = None
        ModuleRegistry._pass_displaced = {}
        ModuleRegistry._loading_plugin = ""
        ModuleRegistry._cleared = False
        ModuleRegistry._started_empty = True
        ModuleRegistry._initialized = False
        ModuleRegistry.discover_plugins(force=True)
        capability_manifest._cached = None
        capability_manifest._cached_generation = -1

    try:
        yield install
    finally:
        for name, value in saved.items():
            setattr(ModuleRegistry, name, value)
        capability_manifest._cached = None
        capability_manifest._cached_generation = -1


def _registers(*rows):
    def register_all():
        for module_id, capability, contract in rows:
            ModuleRegistry.register(module_id, _Module, _raw_metadata(module_id, capability, contract))

    return register_all


def test_a_plugin_contract_reaches_the_manifest(plugins):
    plugins(_EntryPoint("stockroom", _registers(("inventory.adjust", "inventory.adjust", inventory_contract()))))
    assert ModuleRegistry.get_metadata("inventory.adjust")["plugin"] == "stockroom"
    manifest = build_capability_manifest()
    assert manifest["contract_count"] == 1
    entry = manifest["contracts"]["inventory.adjust"]
    assert entry["module_id"] == "inventory.adjust"
    assert entry["contract"] == validate_contract(inventory_contract(), entry["params_schema"])
    assert entry["params_schema"] == {"quantity": {"type": "integer", "min": -1000, "max": 1000}}
    assert manifest["hash"] == compute_manifest_hash(manifest)


def test_a_plugin_with_an_invalid_contract_is_rolled_back_whole(plugins):
    broken = {**inventory_contract(), "safety_class": "harmless"}
    plugins(
        _EntryPoint("good", _registers(("scanner.read", "barcode.read", None))),
        _EntryPoint("broken", _registers(
            ("stock.count", "inventory.count", None),
            ("stock.adjust", "inventory.adjust", broken),
        )),
    )
    assert ModuleRegistry.has("scanner.read")
    assert not ModuleRegistry.has("stock.count"), "the half the plugin managed must not survive"
    assert not ModuleRegistry.has("stock.adjust")
    assert "broken" not in ModuleRegistry.get_plugins()
    assert "good" in ModuleRegistry.get_plugins()
    assert "contracts" not in build_capability_manifest()


# ---------------------------------------------------------------------------
# Manifest: `contracts` only when present, hash otherwise unchanged
# ---------------------------------------------------------------------------


def test_the_manifest_has_no_contracts_key_without_contracts(plugins):
    plugins(_EntryPoint("plain", _registers(("scanner.read", "barcode.read", None))))
    manifest = build_capability_manifest()
    assert "contracts" not in manifest and "contract_count" not in manifest


def test_adding_then_removing_a_contract_restores_the_exact_hash(plugins):
    plugins(_EntryPoint("plain", _registers(("scanner.read", "barcode.read", None))))
    before = build_capability_manifest()

    ModuleRegistry.register(
        "inventory.adjust", _Module, _raw_metadata("inventory.adjust", contract=inventory_contract())
    )
    with_contract = build_capability_manifest()
    assert with_contract["hash"] != before["hash"]
    assert set(with_contract) - set(before) == {"contracts", "contract_count"}

    ModuleRegistry.unregister("inventory.adjust")
    after = build_capability_manifest()
    assert after == before


def test_the_lowest_module_id_speaks_for_a_shared_capability(plugins):
    plugins(_EntryPoint("stockroom", _registers(
        ("inventory.adjust_b", "inventory.adjust", {**inventory_contract(), "idempotent": False}),
        ("inventory.adjust_a", "inventory.adjust", inventory_contract()),
    )))
    manifest = build_capability_manifest()
    assert manifest["contracts"]["inventory.adjust"]["module_id"] == "inventory.adjust_a"
    assert manifest["contracts"]["inventory.adjust"]["contract"]["idempotent"] is True


def test_the_manifest_contract_is_detached_from_the_registry(plugins):
    plugins(_EntryPoint("stockroom", _registers(("inventory.adjust", "inventory.adjust", inventory_contract()))))
    manifest = build_capability_manifest()
    manifest["contracts"]["inventory.adjust"]["contract"]["effects"].append("x.y")
    manifest["contracts"]["inventory.adjust"]["params_schema"]["quantity"]["max"] = 10**9
    again = build_capability_manifest()
    assert again["contracts"]["inventory.adjust"]["contract"]["effects"] == ["inventory.changed"]
    assert again["contracts"]["inventory.adjust"]["params_schema"]["quantity"]["max"] == 1000


# ---------------------------------------------------------------------------
# Catalog detail
# ---------------------------------------------------------------------------


def test_detail_reports_the_contract_and_the_real_timeout(scratch_ids):
    scratch_ids.extend(["lift.test_detail", "lift.test_detail_plain"])
    _decorate("lift.test_detail", timeout_ms=45000)
    _decorate("lift.test_detail_plain", contract=None, provides_capability=None)

    detail = get_module_detail("lift.test_detail")
    assert detail["contract"] == ModuleRegistry.get_metadata("lift.test_detail")["contract"]
    assert detail["provides_capability"] == "lift.move_to_floor"
    assert detail["timeout_ms"] == 45000
    assert detail["timeout"] == 45.0

    plain = get_module_detail("lift.test_detail_plain")
    assert plain["contract"] is None
    assert plain["timeout_ms"] is None and plain["timeout"] is None


# ---------------------------------------------------------------------------
# The worked examples in docs/CAPABILITY_CONTRACT.md, pinned to the digit
# ---------------------------------------------------------------------------


def test_documented_displacement_example():
    observations = {"before": {"x": 1.0, "y": 2.0}, "after": {"x": 1.1, "y": 2.04}, "settled": {"x": 1.11, "y": 2.04}}
    verdict = judge(DISPLACEMENT, {"distance_m": 0.10}, observations)
    assert verdict["usable"] is True
    assert round(verdict["measured"], 6) == 0.117047
    assert verdict["allowed"] == pytest.approx(0.03)
    assert round(verdict["settle_drift"], 6) == 0.010

    short = judge(DISPLACEMENT, {"distance_m": 0.10},
                  {"before": {"x": 1.0, "y": 2.0}, "after": {"x": 1.06, "y": 2.0}, "settled": {"x": 1.06, "y": 2.0}})
    assert short["usable"] is False and round(short["measured"], 6) == 0.06


def test_documented_along_examples():
    advance = judge(ALONG, {"distance_m": 0.10},
                    {"before": {"x": 1.0, "y": 1.0, "yaw": PI / 2},
                     "after": {"x": 1.01, "y": 1.11, "yaw": PI / 2},
                     "settled": {"x": 1.01, "y": 1.115, "yaw": PI / 2}})
    assert advance["usable"] is True
    assert round(advance["measured"], 6) == 0.115
    assert round(advance["settle_drift"], 6) == 0.005

    retreat = judge(RETREAT, {"distance_m": 0.2},
                    {"before": {"x": 0.0, "y": 0.0, "yaw": 0.0},
                     "after": {"x": -0.19, "y": 0.0, "yaw": 0.0},
                     "settled": {"x": -0.19, "y": 0.0, "yaw": 0.0}})
    assert retreat["usable"] is True
    assert retreat["expected"] == -0.2 and retreat["allowed"] == pytest.approx(0.06)


def test_documented_rotation_example():
    verdict = judge(ROTATION, {"yaw_radians": -1.0}, {"before": {"yaw": 3.0}, "after": {"yaw": -2.25}})
    assert verdict["usable"] is True
    assert round(verdict["measured"], 6) == 1.033185
    assert verdict["expected"] == 1.0 and verdict["allowed"] == pytest.approx(0.2)
    assert verdict["settle_drift"] is None
