# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The 2.36.0 optional contract keys: role, artifacts, recovery, expected_duration_ms.

They let a host drop provider knowledge (which capability stops, which ones
return a picture, what substitutes on failure, how long a call may take). Each
is validated, appears in the normalized contract only when declared, and is
published through the registry, catalog detail and capability manifest. A
contract declaring none of them normalizes, and hashes, as it did on 2.35.
"""

import copy

import pytest

from core import capability_manifest
from core.capability_contract import (
    ARTIFACT_MAX_BYTES,
    EXPECTED_DURATION_MS_MAX,
    OPTIONAL_FIELDS,
    ROLES,
    validate_contract,
)
from core.capability_manifest import build_capability_manifest, compute_manifest_hash
from core.catalog.module import get_module_detail
from core.modules.base import BaseModule
from core.modules.registry import ModuleRegistry


def stop_contract(**overrides):
    contract = {
        "actuates": True,
        "safety_class": "controlled",
        "requires_safe_stop": False,
        "cancellable": False,
        "idempotent": True,
        "role": "safe_stop",
    }
    contract.update(overrides)
    return contract


def capture_contract(**overrides):
    contract = {
        "actuates": False,
        "safety_class": "read_only",
        "requires_safe_stop": False,
        "cancellable": False,
        "idempotent": True,
        "artifacts": [{"kind": "image", "media_types": ["image/jpeg", "image/png"], "max_bytes": 4_000_000}],
        "expected_duration_ms": 30_000,
    }
    contract.update(overrides)
    return contract


def task_contract(**overrides):
    contract = {
        "actuates": True,
        "safety_class": "controlled",
        "requires_safe_stop": True,
        "cancellable": True,
        "idempotent": True,
        "recovery": {
            "capabilities": ["queue.retry-later", "queue.cancel"],
            "observe": "recovery_context",
            "guidance": "If the order is locked, retry later; never cancel a paid order.",
        },
        "expected_duration_ms": 180_000,
    }
    contract.update(overrides)
    return contract


def test_the_feature_set_is_published_for_providers_to_detect():
    assert {"role", "artifacts", "recovery", "expected_duration_ms"} == OPTIONAL_FIELDS
    assert ROLES == ("safe_stop",)


def test_a_contract_without_the_new_keys_normalizes_without_them():
    normalized = validate_contract(
        {"actuates": False, "safety_class": "read_only", "requires_safe_stop": False,
         "cancellable": True, "idempotent": True}
    )
    assert not OPTIONAL_FIELDS & set(normalized)


def test_each_declared_key_is_normalized():
    assert validate_contract(stop_contract())["role"] == "safe_stop"
    capture = validate_contract(capture_contract())
    assert capture["artifacts"] == [
        {"kind": "image", "media_types": ["image/jpeg", "image/png"], "max_bytes": 4_000_000}
    ]
    assert capture["expected_duration_ms"] == 30_000
    task = validate_contract(task_contract())
    assert task["recovery"] == task_contract()["recovery"]
    assert task["expected_duration_ms"] == 180_000


def test_recovery_needs_only_capabilities():
    normalized = validate_contract(task_contract(recovery={"capabilities": ["queue.cancel"]}))
    assert normalized["recovery"] == {"capabilities": ["queue.cancel"]}


def test_the_normalized_keys_do_not_alias_the_input():
    source = capture_contract()
    normalized = validate_contract(source)
    source["artifacts"][0]["media_types"].append("image/gif")
    assert normalized["artifacts"][0]["media_types"] == ["image/jpeg", "image/png"]
    source = task_contract()
    normalized = validate_contract(source)
    source["recovery"]["capabilities"].append("queue.drop")
    assert normalized["recovery"]["capabilities"] == ["queue.retry-later", "queue.cancel"]


REFUSED = [
    ("unknown role", stop_contract(role="emergency"), "contract.role must be one of safe_stop"),
    ("role not a string", stop_contract(role=["safe_stop"]), "contract.role"),
    ("cancellable stop", stop_contract(cancellable=True), "role safe_stop requires"),
    ("stop needing a stop", stop_contract(requires_safe_stop=True), "role safe_stop requires"),
    ("non-idempotent stop", stop_contract(idempotent=False), "role safe_stop requires"),
    ("artifacts not a list", capture_contract(artifacts={"kind": "image"}), "contract.artifacts must be a list"),
    ("artifacts empty", capture_contract(artifacts=[]), "contract.artifacts must be a list of 1..8"),
    ("too many artifacts", capture_contract(artifacts=[
        {"kind": f"a{i}", "media_types": ["image/png"], "max_bytes": 1} for i in range(9)
    ]), "contract.artifacts must be a list of 1..8"),
    ("artifact unknown key", capture_contract(artifacts=[
        {"kind": "image", "media_types": ["image/png"], "max_bytes": 1, "width": 10}
    ]), "unknown keys: width"),
    ("artifact missing max_bytes", capture_contract(artifacts=[
        {"kind": "image", "media_types": ["image/png"]}
    ]), "missing required keys: max_bytes"),
    ("artifact bad kind", capture_contract(artifacts=[
        {"kind": "Image", "media_types": ["image/png"], "max_bytes": 1}
    ]), "identifier grammar"),
    ("media type with parameters", capture_contract(artifacts=[
        {"kind": "image", "media_types": ["image/png; q=1"], "max_bytes": 1}
    ]), "media_types\\[0\\]"),
    ("media type upper case", capture_contract(artifacts=[
        {"kind": "image", "media_types": ["Image/PNG"], "max_bytes": 1}
    ]), "media_types\\[0\\]"),
    ("media types empty", capture_contract(artifacts=[
        {"kind": "image", "media_types": [], "max_bytes": 1}
    ]), "media_types must be a list"),
    ("media types duplicated", capture_contract(artifacts=[
        {"kind": "image", "media_types": ["image/png", "image/png"], "max_bytes": 1}
    ]), "duplicates"),
    ("max_bytes zero", capture_contract(artifacts=[
        {"kind": "image", "media_types": ["image/png"], "max_bytes": 0}
    ]), "max_bytes must be an integer"),
    ("max_bytes too large", capture_contract(artifacts=[
        {"kind": "image", "media_types": ["image/png"], "max_bytes": ARTIFACT_MAX_BYTES + 1}
    ]), "max_bytes must be an integer"),
    ("max_bytes float", capture_contract(artifacts=[
        {"kind": "image", "media_types": ["image/png"], "max_bytes": 10.0}
    ]), "max_bytes must be an integer"),
    ("max_bytes bool", capture_contract(artifacts=[
        {"kind": "image", "media_types": ["image/png"], "max_bytes": True}
    ]), "max_bytes must be an integer"),
    ("duplicate artifact kinds", capture_contract(artifacts=[
        {"kind": "image", "media_types": ["image/png"], "max_bytes": 1},
        {"kind": "image", "media_types": ["image/jpeg"], "max_bytes": 1},
    ]), "same kind twice"),
    ("recovery not a mapping", task_contract(recovery=["queue.cancel"]), "contract.recovery must be a mapping"),
    ("recovery without capabilities", task_contract(recovery={"guidance": "wait"}), "missing required keys: capabilities"),
    ("recovery empty capabilities", task_contract(recovery={"capabilities": []}), "1..8"),
    ("recovery unknown key", task_contract(recovery={"capabilities": ["a.b"], "order": 1}), "unknown keys: order"),
    ("recovery bad observe", task_contract(recovery={"capabilities": ["a.b"], "observe": "Context"}),
     "contract.recovery.observe"),
    ("recovery empty guidance", task_contract(recovery={"capabilities": ["a.b"], "guidance": "  "}),
     "guidance must be non-empty"),
    ("recovery long guidance", task_contract(recovery={"capabilities": ["a.b"], "guidance": "x" * 501}),
     "guidance must be non-empty"),
    ("duration zero", task_contract(expected_duration_ms=0), "expected_duration_ms must be an integer"),
    ("duration too long", task_contract(expected_duration_ms=EXPECTED_DURATION_MS_MAX + 1),
     "expected_duration_ms must be an integer"),
    ("duration float", task_contract(expected_duration_ms=1000.0), "expected_duration_ms must be an integer"),
    ("duration bool", task_contract(expected_duration_ms=True), "expected_duration_ms must be an integer"),
]


@pytest.mark.parametrize("name, contract, message", REFUSED, ids=[row[0] for row in REFUSED])
def test_invalid_optional_keys_are_refused(name, contract, message):
    with pytest.raises(ValueError, match=message):
        validate_contract(contract)


# ---------------------------------------------------------------------------
# Publication: registry, catalog detail, manifest.
# ---------------------------------------------------------------------------


class _Module(BaseModule):
    async def execute(self):  # pragma: no cover - never executed here
        return {}


@pytest.fixture
def registered():
    ids = []

    def register(module_id, capability, contract):
        ModuleRegistry.register(
            module_id,
            _Module,
            {
                "module_id": module_id,
                "category": module_id.split(".")[0],
                "stability": "stable",
                "ui_label": module_id,
                "ui_description": "optional contract keys",
                "provides_capability": capability,
                "params_schema": {},
                "contract": copy.deepcopy(contract),
                "timeout_ms": 45_000,
            },
        )
        ids.append(module_id)
        capability_manifest._cached = None

    yield register
    for module_id in ids:
        ModuleRegistry.unregister(module_id)
    capability_manifest._cached = None


def test_the_keys_reach_metadata_detail_and_manifest(registered):
    registered("optionaltest.stop", "optionaltest.stop", stop_contract())
    registered("optionaltest.capture", "optionaltest.capture", capture_contract())
    stored = ModuleRegistry.get_metadata("optionaltest.stop")["contract"]
    assert stored["role"] == "safe_stop"
    detail = get_module_detail("optionaltest.capture")
    assert detail["contract"]["artifacts"][0]["kind"] == "image"
    assert detail["contract"]["expected_duration_ms"] == 30_000
    manifest = build_capability_manifest()
    assert manifest["contracts"]["optionaltest.stop"]["contract"]["role"] == "safe_stop"
    assert manifest["contracts"]["optionaltest.capture"]["contract"]["artifacts"] == [
        {"kind": "image", "media_types": ["image/jpeg", "image/png"], "max_bytes": 4_000_000}
    ]
    assert manifest["hash"] == compute_manifest_hash(manifest)


def test_registry_refuses_an_invalid_optional_key(registered):
    with pytest.raises(ValueError, match="role safe_stop requires"):
        registered("optionaltest.badstop", "optionaltest.badstop", stop_contract(cancellable=True))
    assert not ModuleRegistry.has("optionaltest.badstop")
