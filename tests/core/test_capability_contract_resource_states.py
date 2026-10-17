# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Resource states and parts in the capability contract (2.41.0).

``requires`` already named the states a call needs. ``establishes`` names the
states a completed call leaves true, so a host can check a precondition and a
planner can order calls ("stand" before "walk"); a ``safe_stop`` uses it to
say what a stop leaves the resource in. ``occupies`` names the parts of the
resource a running call holds, so two calls on one multi-part resource
conflict only when they overlap. A contract that declares neither normalizes
and hashes exactly as on 2.40, and occupies the whole resource.

The vocabulary is a provider's: these tests use neutral names a robot, a lift
or a production cell would read the same way.
"""

import copy
import json
from pathlib import Path

import pytest

from core.capability_contract import OCCUPIES_MAX, RESOURCE_STATE_FIELDS, validate_contract

VECTORS = json.loads(
    (Path(__file__).parent / "vectors" / "capability_contract_resource_states.json").read_text("utf-8")
)


def _contract(base: str, fragment: dict) -> dict:
    return {**copy.deepcopy(VECTORS[base]), **copy.deepcopy(fragment)}


def test_the_feature_test_and_bound_are_published():
    assert frozenset(("establishes", "occupies")) == RESOURCE_STATE_FIELDS
    assert OCCUPIES_MAX == 8


@pytest.mark.parametrize("vector", VECTORS["admitted"], ids=lambda v: v["name"])
def test_admitted_contracts_keep_what_they_declare(vector):
    normalized = validate_contract(_contract("base", vector["fragment"]))
    for key, value in vector["fragment"].items():
        assert normalized[key] == value


@pytest.mark.parametrize("vector", VECTORS["admitted_stops"], ids=lambda v: v["name"])
def test_a_stop_may_say_what_it_leaves_the_resource_in(vector):
    normalized = validate_contract(_contract("stop_base", vector["fragment"]))
    assert normalized["role"] == "safe_stop"
    assert normalized["establishes"] == vector["fragment"]["establishes"]


@pytest.mark.parametrize("vector", VECTORS["refused"], ids=lambda v: v["name"])
def test_refused_contracts_name_the_key(vector):
    key = next(iter(vector["fragment"]))
    with pytest.raises(ValueError, match=f"contract.{key}"):
        validate_contract(_contract("base", vector["fragment"]))


@pytest.mark.parametrize("vector", VECTORS["refused_stops"], ids=lambda v: v["name"])
def test_a_stop_never_occupies_what_it_must_interrupt(vector):
    with pytest.raises(ValueError, match="safe_stop must not declare occupies"):
        validate_contract(_contract("stop_base", vector["fragment"]))


def test_a_contract_without_them_normalizes_and_hashes_exactly_as_before():
    normalized = validate_contract(copy.deepcopy(VECTORS["base"]))
    # The 2.40 normalized form, written out by hand.
    expected = {
        "schema": "flyto.capability-contract.v1",
        "actuates": True,
        "safety_class": "movement",
        "requires_safe_stop": True,
        "cancellable": True,
        "idempotent": False,
        "effects": [],
        "requires": [],
        "evidence": [],
    }
    assert json.dumps(normalized, sort_keys=True) == json.dumps(expected, sort_keys=True)


def test_the_normalized_lists_do_not_alias_the_input():
    source = _contract("base", {"establishes": ["posture.walking"], "occupies": ["locomotion"]})
    normalized = validate_contract(source)
    source["establishes"].append("injected")
    source["occupies"].append("injected")
    assert normalized["establishes"] == ["posture.walking"]
    assert normalized["occupies"] == ["locomotion"]
