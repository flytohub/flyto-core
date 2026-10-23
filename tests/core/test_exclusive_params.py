"""Parameters that rule each other out are declared, shown and refused as such.

`browser.wait` waits for a duration OR for a selector. With a selector set the
module never reads ``duration_ms`` (``wait.py``: the selector branch returns
before the sleep), yet both could be filled and nothing said the duration was
ignored (Cloud gap G-15). The params schema now says so with
``exclusive_with``: a field naming the fields that, once set, rule it out.
Validation refuses a document that sets both with ``PARAMS_EXCLUSIVE``; a
panel greys the ruled-out field from the same declaration.
"""

from core.modules import atomic  # noqa: F401
from core.modules.registry import ModuleRegistry
from core.modules.schema import field
from core.validation.errors import ErrorCode
from core.validation.workflow import validate_node_params


def _wait(**params):
    return {"id": "wait", "module_id": "browser.wait", "params": params}


def _codes(errors):
    return [e.code for e in errors]


def test_the_field_builder_carries_the_declaration():
    built = field("duration_ms", type="number", exclusive_with=["selector"])
    assert built["duration_ms"]["exclusive_with"] == ["selector"]


def test_browser_wait_declares_that_a_selector_rules_out_the_duration():
    schema = ModuleRegistry.get_metadata("browser.wait")["params_schema"]
    assert schema["duration_ms"]["exclusive_with"] == ["selector"]


def test_setting_both_is_refused_with_a_typed_code_on_the_ruled_out_field():
    errors = validate_node_params(_wait(selector="text=Notices", duration_ms=1000))

    refused = [e for e in errors if e.code == ErrorCode.PARAMS_EXCLUSIVE]
    assert len(refused) == 1
    assert refused[0].path == "nodes[wait].params.duration_ms"
    assert refused[0].meta["param"] == "duration_ms"
    assert refused[0].meta["ruled_out_by"] == "selector"


def test_either_one_alone_is_accepted():
    assert ErrorCode.PARAMS_EXCLUSIVE not in _codes(validate_node_params(_wait(selector="text=Notices")))
    assert ErrorCode.PARAMS_EXCLUSIVE not in _codes(validate_node_params(_wait(duration_ms=500)))


def test_an_empty_ruling_field_does_not_rule_anything_out():
    assert ErrorCode.PARAMS_EXCLUSIVE not in _codes(validate_node_params(_wait(selector="", duration_ms=500)))
