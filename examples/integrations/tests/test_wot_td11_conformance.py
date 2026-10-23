"""W3C WoT TD 1.1 conformance against the official JSON Schema.

The adapter's admission must never be wider than the W3C schema: a Thing
Description the schema refuses is not a Thing Description, so importing it
would turn malformed vendor data into Flyto2 offers. The schema is vendored
byte-for-byte (see flyto_ecosystems/schemas/NOTICE) and pinned by digest here.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

from flyto_ecosystems import wot  # noqa: E402
from flyto_ecosystems.wot import (  # noqa: E402
    TD_CONTEXT,
    export_thing_description,
    import_thing_description,
)

SCHEMA_PATH = Path(wot.__file__).parent / "schemas" / "w3c-wot-td-1.1.schema.json"
SCHEMA_SHA256 = "fd44f319f94c6f16f66978860ef2f9f4e0e9fd7fc5835a2f3840b9cf2002e0f1"
TD_V1 = "https://www.w3.org/2019/wot/td/v1"


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _schema_accepts(td: dict) -> bool:
    return jsonschema.Draft7Validator(_schema()).is_valid(td)


def _lamp() -> dict:
    """Example 1 of the TD 1.1 Recommendation, with bearer instead of basic."""
    return {
        "@context": TD_CONTEXT,
        "id": "urn:uuid:0804d572-cce8-422a-bb7c-4412fcd56f06",
        "title": "MyLampThing",
        "securityDefinitions": {"bearer_sc": {"scheme": "bearer", "in": "header"}},
        "security": "bearer_sc",
        "properties": {"status": {
            "type": "string",
            "forms": [{"href": "https://mylamp.example.com/status"}],
        }},
        "actions": {"toggle": {
            "forms": [{"href": "https://mylamp.example.com/toggle"}],
        }},
        "events": {"overheating": {
            "data": {"type": "string"},
            "forms": [{"href": "https://mylamp.example.com/oh", "subprotocol": "longpoll"}],
        }},
    }


def _set(path: tuple, value):
    def mutate(td: dict) -> None:
        node = td
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    return mutate


def _drop(path: tuple):
    def mutate(td: dict) -> None:
        node = td
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]
    return mutate


# Each case is something a real vendor TD can contain. Whether the official
# schema accepts it is asserted, not assumed, so the corpus cannot drift from
# the schema it is checking against.
CORPUS = [
    ("recommendation example", lambda td: None, True),
    ("context: old then new URI", _set(("@context",), [TD_V1, TD_CONTEXT]), True),
    ("context: new URI then extension", _set(("@context",), [TD_CONTEXT, {"saref": "https://saref.etsi.org/core/"}]), True),
    ("context: extension before TD URI", _set(("@context",), ["https://example.org/ext", TD_CONTEXT]), False),
    ("context: new URI then old URI", _set(("@context",), [TD_CONTEXT, TD_V1]), False),
    ("property without forms", _drop(("properties", "status", "forms")), False),
    ("action with empty forms", _set(("actions", "toggle", "forms"), []), False),
    ("event form without href", _set(("events", "overheating", "forms"), [{"subprotocol": "longpoll"}]), False),
    ("security scheme without scheme", _set(("securityDefinitions",), {"bearer_sc": {"in": "header"}}), False),
    ("property form with action op", _set(("properties", "status", "forms"), [{"href": "https://l/s", "op": "invokeaction"}]), False),
    ("action form with property op", _set(("actions", "toggle", "forms"), [{"href": "https://l/t", "op": ["readproperty"]}]), False),
    ("event form with action op", _set(("events", "overheating", "forms"), [{"href": "https://l/o", "op": "invokeaction"}]), False),
    ("property op list", _set(("properties", "status", "forms"), [{"href": "https://l/s", "op": ["readproperty", "observeproperty"]}]), True),
    ("title is not a string", _set(("title",), 7), False),
    ("security array", _set(("security",), ["bearer_sc"]), True),
]


def test_vendored_schema_is_the_official_unmodified_copy():
    digest = hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()
    assert digest == SCHEMA_SHA256
    assert _schema()["$id"] == "https://www.w3.org/2022/wot/td-schema/v1.1"


@pytest.mark.parametrize(("label", "mutate", "schema_valid"), CORPUS, ids=[c[0] for c in CORPUS])
def test_admission_is_never_wider_than_the_official_schema(label, mutate, schema_valid):
    td = _lamp()
    mutate(td)
    assert _schema_accepts(td) is schema_valid, f"corpus expectation drifted: {label}"
    if schema_valid:
        assert import_thing_description(td, resource_id="lamp-1")
    else:
        with pytest.raises(ValueError):
            import_thing_description(td, resource_id="lamp-1")


def test_forward_mapping_of_the_recommendation_example():
    offers = {o.capability_id: o for o in import_thing_description(_lamp(), resource_id="lamp-1")}
    assert set(offers) == {
        "vendor.wot.property_status",
        "vendor.wot.action_toggle",
        "vendor.wot.event_overheating",
    }
    assert all(o.approval_status == "DISCOVERED" and o.resource_id == "lamp-1" for o in offers.values())
    # An action with no declared flags is assumed neither safe nor idempotent.
    toggle = offers["vendor.wot.action_toggle"]
    assert (toggle.safe, toggle.idempotent, toggle.observable) == (False, False, False)
    assert offers["vendor.wot.property_status"].observable is True
    assert offers["vendor.wot.event_overheating"].observable is True


def test_write_only_property_has_no_read_mapping_and_is_refused():
    td = _lamp()
    td["properties"]["status"]["writeOnly"] = True
    assert _schema_accepts(td)
    # Flyto2 maps a property to an observation; a value that cannot be read
    # has no such meaning, so it is refused rather than offered as observable.
    with pytest.raises(ValueError, match="writeOnly"):
        import_thing_description(td, resource_id="lamp-1")


def test_semantic_annotations_cannot_claim_a_flyto2_capability():
    td = _lamp()
    td["@type"] = ["robotics.motion.navigate", "saref:Actuator"]
    td["actions"]["toggle"]["@type"] = "robotics.motion.navigate"
    td["actions"]["toggle"]["safe"] = True
    assert _schema_accepts(td)
    offers = import_thing_description(td, resource_id="lamp-1")
    # Capability identifiers come from the affordance name in the vendor
    # namespace only; a description is never an approval.
    assert {o.capability_id for o in offers} == {
        "vendor.wot.property_status",
        "vendor.wot.action_toggle",
        "vendor.wot.event_overheating",
    }
    assert all(o.approval_status == "DISCOVERED" for o in offers)


def test_reverse_mapping_exports_a_schema_valid_td_that_round_trips():
    offers = import_thing_description(_lamp(), resource_id="lamp-1")
    approved = tuple(replace(o, approval_status="APPROVED") for o in offers)
    forms = {
        o.capability_id: [{"href": f"https://host.example.com/{o.name}"}]
        for o in approved
    }
    exported = export_thing_description(
        approved, title="MyLampThing",
        security_definitions={"bearer_sc": {"scheme": "bearer"}},
        security="bearer_sc", forms_by_capability=forms,
    )
    validator = jsonschema.Draft7Validator(_schema())
    errors = sorted(validator.iter_errors(exported), key=lambda e: list(e.path))
    assert not errors, [e.message for e in errors]
    again = import_thing_description(copy.deepcopy(exported), resource_id="lamp-1")
    assert [(o.capability_id, o.kind, o.safe, o.idempotent, o.observable) for o in again] == [
        (o.capability_id, o.kind, o.safe, o.idempotent, o.observable) for o in offers
    ]


def test_export_refuses_host_forms_the_schema_would_refuse():
    offers = import_thing_description(_lamp(), resource_id="lamp-1")
    approved = tuple(replace(o, approval_status="APPROVED") for o in offers)
    forms = {o.capability_id: [{"href": "https://h/x"}] for o in approved}
    forms["vendor.wot.action_toggle"] = [{"href": "https://h/t", "op": "readproperty"}]
    with pytest.raises(ValueError):
        export_thing_description(
            approved, title="MyLampThing",
            security_definitions={"bearer_sc": {"scheme": "bearer"}},
            security="bearer_sc", forms_by_capability=forms,
        )
