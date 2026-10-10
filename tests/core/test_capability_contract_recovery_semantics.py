# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Recovery semantics in the capability contract (2.39.0).

A ``recovery`` block may state, as data, what a stopped call may be worked
round with: the stop-reason families it answers (``on``), the semantic roles a
way round is made of (``alternatives``), what the way round must still reach
(``preserves``), where it may run (``resource_scope``), and the roles the
capability itself fills (``fills``). ``capabilities`` becomes optional; the
2.36 host-report keys keep validating, normalizing and hashing as before.

The vocabulary below is deliberately neutral: a queue, a document store, a
lift or a vehicle reads the same.
"""

import copy
import json
from pathlib import Path

import pytest

from core.capability_contract import (
    RECOVERY_FIELDS,
    RECOVERY_PRESERVES,
    RECOVERY_RESOURCE_SCOPES,
    RECOVERY_ROLE_PATTERN,
    RECOVERY_ROLES_MAX,
    RECOVERY_STOP_FAMILIES,
    validate_contract,
)
from core.modules.registry import ModuleRegistry


def contract(recovery):
    return {
        "actuates": True,
        "safety_class": "controlled",
        "requires_safe_stop": True,
        "cancellable": True,
        "idempotent": True,
        "recovery": recovery,
    }


WAY_ROUND = {
    "on": ["obstruction"],
    "alternatives": ["reorient", "reposition", "travel_to"],
    "preserves": ["destination"],
    "resource_scope": "same_resource",
    "fills": ["reposition"],
}


def test_the_vocabularies_are_published_for_providers_and_hosts():
    assert RECOVERY_STOP_FAMILIES == ("obstruction", "no_passage", "stopped_short")
    assert RECOVERY_PRESERVES == ("destination", "target")
    assert RECOVERY_RESOURCE_SCOPES == ("same_resource",)
    assert RECOVERY_ROLES_MAX == 8
    assert frozenset(
        ("capabilities", "observe", "guidance", "on", "alternatives", "preserves", "resource_scope", "fills")
    ) == RECOVERY_FIELDS
    # The feature test a provider uses before sending the semantic keys.
    assert "fills" in RECOVERY_FIELDS


def test_a_full_way_round_normalizes_in_declared_order():
    normalized = validate_contract(contract(copy.deepcopy(WAY_ROUND)))["recovery"]
    assert normalized == WAY_ROUND
    # alternatives is a preference: its order is kept, never sorted.
    assert normalized["alternatives"] == ["reorient", "reposition", "travel_to"]


def test_fills_alone_is_a_declaration_without_capabilities():
    assert validate_contract(contract({"fills": ["reorient"]}))["recovery"] == {"fills": ["reorient"]}


def test_semantics_and_the_host_report_coexist():
    block = {
        "capabilities": ["queue.retry-later"],
        "observe": "recovery_context",
        "guidance": "Retry later.",
        **copy.deepcopy(WAY_ROUND),
    }
    assert validate_contract(contract(copy.deepcopy(block)))["recovery"] == block


def test_every_family_and_both_preserves_are_admitted():
    block = {
        "on": list(RECOVERY_STOP_FAMILIES),
        "alternatives": ["retry.elsewhere"],
        "preserves": list(RECOVERY_PRESERVES),
        "resource_scope": "same_resource",
    }
    assert validate_contract(contract(copy.deepcopy(block)))["recovery"] == block


def test_a_2_36_report_block_normalizes_and_hashes_exactly_as_before():
    report = {"capabilities": ["queue.cancel"], "observe": "recovery_context", "guidance": "Cancel."}
    normalized = validate_contract(contract(copy.deepcopy(report)))
    assert normalized["recovery"] == report
    assert list(normalized["recovery"]) == ["capabilities", "observe", "guidance"]
    # The pre-2.39 normalized form, written out by hand.
    expected = {
        "schema": "flyto.capability-contract.v1",
        "actuates": True,
        "safety_class": "controlled",
        "requires_safe_stop": True,
        "cancellable": True,
        "idempotent": True,
        "effects": [],
        "requires": [],
        "evidence": [],
        "recovery": report,
    }
    assert json.dumps(normalized, sort_keys=True) == json.dumps(expected, sort_keys=True)


def test_the_normalized_block_does_not_alias_the_input():
    source = contract(copy.deepcopy(WAY_ROUND))
    normalized = validate_contract(source)
    source["recovery"]["alternatives"].append("injected")
    source["recovery"]["fills"].append("injected")
    assert normalized["recovery"] == WAY_ROUND


def _with(**changes):
    block = copy.deepcopy(WAY_ROUND)
    for key, value in changes.items():
        if value is _DROP:
            block.pop(key)
        else:
            block[key] = value
    return block


_DROP = object()

REFUSED = [
    ("empty block", {}, "must declare capabilities, alternatives or fills"),
    ("observe only", {"observe": "recovery_context"}, "must declare capabilities, alternatives or fills"),
    ("unknown key", _with(order=1), "unknown keys: order"),
    ("bound smuggled in", _with(max_rounds=3), "unknown keys: max_rounds"),
    ("on not a list", _with(on="obstruction"), r"recovery\.on must be a list"),
    ("on empty", _with(on=[]), r"recovery\.on must be a list of 1\.\.3"),
    ("on unknown family", _with(on=["weather"]), r"recovery\.on may name only"),
    ("on duplicate", _with(on=["obstruction", "obstruction"]), r"recovery\.on contains duplicates"),
    ("on without alternatives", _with(alternatives=_DROP), "declared together"),
    ("alternatives without on", _with(on=_DROP), "declared together"),
    ("alternatives without scope", _with(resource_scope=_DROP), "requires contract.recovery.resource_scope"),
    ("alternatives empty", _with(alternatives=[]), r"recovery\.alternatives must hold 1\.\.8"),
    ("alternatives too many", _with(alternatives=[f"role{index}" for index in range(9)]), "1..8"),
    ("alternatives duplicate", _with(alternatives=["reorient", "reorient"]), "names a role twice"),
    ("alternative not a role", _with(alternatives=["Reorient"]), r"alternatives\[0\] must be a role"),
    ("alternative not a string", _with(alternatives=[3]), r"alternatives\[0\] must be a role"),
    ("alternative too long", _with(alternatives=["a" * 97]), r"alternatives\[0\] must be a role"),
    ("alternatives a mapping", _with(alternatives={"reorient": 1}), "must be a list of roles"),
    ("preserves unknown", _with(preserves=["everything"]), r"recovery\.preserves may name only"),
    ("preserves a string", _with(preserves="destination"), r"recovery\.preserves must be a list"),
    ("preserves duplicate", _with(preserves=["target", "target"]), "contains duplicates"),
    ("scope other resource", _with(resource_scope="any_resource"), "resource_scope must be one of same_resource"),
    ("scope a list", _with(resource_scope=["same_resource"]), "resource_scope must be one of"),
    ("preserves without a way round", {"fills": ["reposition"], "preserves": ["target"]}, "describe a way round"),
    ("scope without a way round", {"fills": ["reposition"], "resource_scope": "same_resource"}, "describe a way round"),
    ("fills empty", {"fills": []}, r"recovery\.fills must hold 1\.\.8"),
    ("fills bad role", {"fills": ["re position"]}, r"fills\[0\] must be a role"),
    ("fills duplicate", {"fills": ["a", "a"]}, "names a role twice"),
    ("capabilities still bounded", {"capabilities": []}, "1..8"),
]


@pytest.mark.parametrize("name, block, message", REFUSED, ids=[row[0] for row in REFUSED])
def test_invalid_recovery_semantics_are_refused(name, block, message):
    with pytest.raises(ValueError, match=message):
        validate_contract(contract(block))


def test_roles_use_the_named_pattern():
    assert RECOVERY_ROLE_PATTERN.fullmatch("travel_to")
    assert RECOVERY_ROLE_PATTERN.fullmatch("vendor.acme-reposition")
    assert not RECOVERY_ROLE_PATTERN.fullmatch("motion advance")
    assert not RECOVERY_ROLE_PATTERN.fullmatch("_hidden")


def test_the_registry_publishes_the_declaration():
    from core.modules.base import BaseModule

    class _Module(BaseModule):
        async def execute(self):  # pragma: no cover - never executed here
            return {}

    module_id = "zz_recovery_semantics.reposition"
    try:
        ModuleRegistry.register(
            module_id,
            _Module,
            {
                "module_id": module_id,
                "category": "zz_recovery_semantics",
                "stability": "stable",
                "ui_label": module_id,
                "ui_description": "recovery semantics",
                "provides_capability": module_id,
                "params_schema": {},
                "contract": contract(copy.deepcopy(WAY_ROUND)),
            },
        )
        assert ModuleRegistry.get_metadata(module_id)["contract"]["recovery"] == WAY_ROUND
    finally:
        ModuleRegistry.unregister(module_id)


def test_the_shared_vectors_hold():
    """Blocks a host reads as declarations are admitted unchanged; malformed ones are not."""
    path = Path(__file__).parent / "vectors" / "capability_contract_recovery_semantics.json"
    vectors = json.loads(path.read_text(encoding="utf-8"))
    for item in vectors["admitted"]:
        assert validate_contract(contract(copy.deepcopy(item["recovery"])))["recovery"] == item["recovery"]
    for item in vectors["refused"]:
        with pytest.raises(ValueError):
            validate_contract(contract(copy.deepcopy(item["recovery"])))
