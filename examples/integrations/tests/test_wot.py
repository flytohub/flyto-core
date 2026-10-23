from dataclasses import replace

import pytest
from flyto_ecosystems.wot import (
    TD_CONTEXT,
    export_thing_description,
    import_thing_description,
)


@pytest.fixture
def td():
    return {
        "@context": TD_CONTEXT, "title": "Ceiling light",
        "securityDefinitions": {"token": {"scheme": "bearer"}},
        "security": "token",
        "properties": {"brightness": {
            "readOnly": True,
            "forms": [{"href": "https://lights.local/api/brightness", "op": "readproperty"}],
        }},
        "actions": {
            "turn-on": {
                "safe": False, "idempotent": True,
                "forms": [{"href": "https://lights.local/api/turn_on", "op": "invokeaction"}],
            },
        },
        "events": {"power_changed": {
            "forms": [{"href": "https://lights.local/api/events", "subprotocol": "sse"}],
        }},
    }


def test_import_is_always_unapproved_and_never_dereferences(td):
    offers = import_thing_description(td, resource_id="light-1")
    assert {x.capability_id for x in offers} == {
        "vendor.wot.property_brightness",
        "vendor.wot.action_turn_on",
        "vendor.wot.event_power_changed",
    }
    assert all(x.approval_status == "DISCOVERED" for x in offers)
    assert offers[1].safe is False
    assert offers[1].idempotent is True


def test_export_requires_real_authorized_forms(td):
    offers = import_thing_description(td, resource_id="light-1")
    approved = tuple(replace(x, approval_status="APPROVED") for x in offers)
    with pytest.raises(ValueError, match="security"):
        export_thing_description(approved, title="light", security_definitions={
            "nosec": {"scheme": "nosec"},
        }, security="nosec", forms_by_capability={})
    with pytest.raises(ValueError, match="forms"):
        export_thing_description(approved, title="light", security_definitions={
            "token": {"scheme": "bearer"},
        }, security="token", forms_by_capability={})
    forms = {o.capability_id: [{"href": f"https://lights.local/{o.name}"}] for o in approved}
    exported = export_thing_description(
        approved, title="light", security_definitions={"token": {"scheme": "bearer"}},
        security="token", forms_by_capability=forms,
    )
    assert exported["actions"]["turn-on"]["idempotent"] is True
    assert exported["security"] == "token"
    assert "forms" in exported["properties"]["brightness"]


@pytest.mark.parametrize("mutation", [
    {"security": "other"},
    {"securityDefinitions": {}},
    {"@context": "https://example.org/not-td"},
    {"title": ""},
    {"actions": {"turn_on": {"safe": "true", "forms": [{"href": "https://l/a"}]}}},
    {"actions": {"turn_on": {"idempotent": 1, "forms": [{"href": "https://l/a"}]}}},
    {"actions": {"turn_on": {"forms": [{"href": "file:///etc/passwd"}]}}},
    {"actions": {"turn_on": {"forms": [{"href": "https://user:secret@host/"}]}}},
    {"actions": {"turn-on": {"forms": [{"href": "https://l/a"}]},
                 "turn_on": {"forms": [{"href": "https://l/b"}]}}},
])
def test_bad_external_data_fails_closed(td, mutation):
    td.update(mutation)
    with pytest.raises(ValueError):
        import_thing_description(td, resource_id="light-1")


def test_undeclared_action_flags_are_not_assumed_safe(td):
    td["actions"]["turn-on"] = {"forms": [{"href": "https://lights.local/api/turn_on"}]}
    offers = import_thing_description(td, resource_id="light-1")
    action = next(x for x in offers if x.kind == "action")
    assert not action.safe and not action.idempotent


def test_unapproved_offers_are_not_exported(td):
    offers = import_thing_description(td, resource_id="light-1")
    result = export_thing_description(
        offers, title="light", security_definitions={"token": {"scheme": "bearer"}},
        security="token", forms_by_capability={},
    )
    assert not any(result[key] for key in ("properties", "actions", "events"))
