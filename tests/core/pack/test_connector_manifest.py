"""The ``connector`` section of ``flyto.pack.v1``: a provider's API declared as data.

Every refusal is typed and names the operation it is about, so a provider
developer reads which declaration to fix, not which line of core failed.
"""

import copy
import json
import re
from pathlib import Path

import pytest

from core.pack import compatibility
from core.pack.connector import CONSEQUENCE_CONTRACTS, CONSEQUENCES
from core.pack.manifest import PackManifestError, read_pack_manifest, validate_pack_manifest

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "packs" / "ratings-connector"


def example():
    return json.loads((EXAMPLE / "flyto-pack.json").read_text(encoding="utf-8"))


def operation(doc, op_id):
    return next(op for op in doc["connector"]["operations"] if op["id"] == op_id)


def refused(doc):
    with pytest.raises(PackManifestError) as caught:
        validate_pack_manifest(doc)
    return caught.value


# -- the example validates and becomes modules ---------------------------------


def test_the_example_validates():
    manifest = read_pack_manifest(EXAMPLE)
    assert manifest["runtime"]["binding"] == "connector"
    ids = [row["module_id"] for row in manifest["modules"]]
    assert ids == ["ratings.company.get", "ratings.findings.list", "ratings.portfolio.list"]


def test_an_operation_row_takes_its_params_from_inputs():
    manifest = validate_pack_manifest(example())
    row = next(r for r in manifest["modules"] if r["module_id"] == "ratings.findings.list")
    assert row["params_schema"]["company"]["type"] == "string"
    assert row["params_schema"]["company"]["required"] is True  # a path parameter is always required
    assert row["params_schema"]["severity"].get("required", False) is False
    assert row["requires_credentials"] is True


def test_an_operation_row_carries_its_consequence_as_a_contract():
    manifest = validate_pack_manifest(example())
    row = next(r for r in manifest["modules"] if r["module_id"] == "ratings.company.get")
    assert row["provides_capability"] == "ratings.company.get"
    assert row["contract"]["safety_class"] == "read_only"
    assert row["contract"]["actuates"] is False
    assert row["contract"]["effects"] == ["read"]


@pytest.mark.parametrize("consequence", CONSEQUENCES)
def test_every_consequence_level_has_one_contract(consequence):
    doc = example()
    operation(doc, "company.get")["consequence"] = consequence
    row = next(r for r in validate_pack_manifest(doc)["modules"] if r["module_id"] == "ratings.company.get")
    expected = CONSEQUENCE_CONTRACTS[consequence]
    assert row["contract"]["safety_class"] == expected["safety_class"]
    assert row["contract"]["effects"] == list(expected["effects"])


def test_the_consequence_vocabulary_is_the_five_levels():
    assert CONSEQUENCES == ("observe", "reversible", "external_write", "real_world", "irreversible")


def test_the_normalized_connector_keeps_what_later_lanes_read():
    manifest = validate_pack_manifest(example())
    op = next(o for o in manifest["connector"]["operations"] if o["id"] == "company.get")
    assert op["consequence"] == "observe"
    assert op["inputs"]["company"]["scope"] == "company"
    assert op["result_scope"] == "$.guid"
    assert op["requires"] == {"features": []}
    assert op["consumes"] is None


def test_requires_and_consumes_are_kept_as_declared():
    doc = example()
    op = operation(doc, "company.get")
    op["requires"] = {"features": {"any": ["spm", "cm"]}}
    op["consumes"] = {"meter": "lookups", "amount": 1}
    normalized = next(o for o in validate_pack_manifest(doc)["connector"]["operations"] if o["id"] == "company.get")
    assert normalized["requires"] == {"features": {"any": ["spm", "cm"]}}
    assert normalized["consumes"] == {"meter": "lookups", "amount": 1}


def test_a_connector_pack_needs_2_41():
    needed, features = compatibility.required_host(validate_pack_manifest(example()))
    assert needed == "2.41.0"
    assert "pack.connector" in features


# -- refusals --------------------------------------------------------------------


def test_an_operation_without_a_consequence_is_refused_by_name():
    doc = example()
    del operation(doc, "findings.list")["consequence"]
    error = refused(doc)
    assert error.code == "CONSEQUENCE_MISSING"
    assert error.operation == "findings.list"
    assert "findings.list" in str(error)


def test_a_null_consequence_is_missing_too():
    doc = example()
    operation(doc, "findings.list")["consequence"] = None
    assert refused(doc).code == "CONSEQUENCE_MISSING"


def test_an_unknown_consequence_is_refused():
    doc = example()
    operation(doc, "company.get")["consequence"] = "harmless"
    error = refused(doc)
    assert error.code == "CONSEQUENCE_UNKNOWN" and error.operation == "company.get"


def test_a_path_parameter_with_no_input_is_refused():
    doc = example()
    operation(doc, "company.get")["path"] = "/v1/companies/{company}/{tab}"
    error = refused(doc)
    assert error.code == "PATH_PARAM_UNDECLARED" and error.operation == "company.get"
    assert "tab" in str(error)


@pytest.mark.parametrize(
    "entry",
    [
        {"kind": "api_token", "header": "Authorization", "credential": "x", "token": "abc123"},
        {"kind": "api_token", "header": "Authorization", "credential": "x", "value": "abc"},
        {"kind": "oauth2_client_credentials", "token_url": "https://id.example/token", "credential": "c",
         "client_secret": "s3cr3t"},
        {"kind": "api_token", "header": "Authorization", "credential": "eyJhbGciOi.eyJzdWIiOiIx.c2lnbmF0dXJl"},
        {"kind": "api_token", "header": "Authorization", "credential": "Bearer abcdefghijklmnopqrstuvwxyz"},
    ],
)
def test_an_inline_secret_in_auth_is_refused(entry):
    doc = example()
    doc["connector"]["auth"] = [entry]
    assert refused(doc).code == "INLINE_SECRET"


def test_an_inline_secret_in_an_input_default_is_refused():
    doc = example()
    operation(doc, "company.get")["inputs"]["api_key"] = {"type": "string", "default": "k-123"}
    error = refused(doc)
    assert error.code == "INLINE_SECRET" and error.operation == "company.get"


def test_a_secret_in_the_base_url_is_refused():
    doc = example()
    doc["connector"]["base_url"] = "https://user:pass@api.ratings.example"
    assert refused(doc).code == "INLINE_SECRET"


def test_an_unknown_auth_kind_is_refused():
    doc = example()
    doc["connector"]["auth"] = [{"kind": "magic_cookie", "credential": "x"}]
    assert refused(doc).code == "UNKNOWN_AUTH_KIND"


@pytest.mark.parametrize("field", ["sensitive", "result_scope"])
@pytest.mark.parametrize("path", ["findings[*]", "$..assets", "$.items[?(@.x)]", "$.items[0:2]", "$."])
def test_a_path_that_does_not_parse_is_refused(field, path):
    doc = example()
    op = operation(doc, "findings.list")
    op[field] = [path] if field == "sensitive" else path
    error = refused(doc)
    assert error.code == "INVALID_JSONPATH" and error.operation == "findings.list"


def test_a_connector_needs_the_connector_binding():
    doc = example()
    doc["runtime"] = {"binding": "http", "locality": "same_host"}
    assert refused(doc).code == "CONNECTOR_BINDING"


def test_the_connector_binding_needs_a_connector():
    doc = example()
    del doc["connector"]
    assert refused(doc).code == "CONNECTOR_REQUIRED"


def test_modules_are_derived_never_declared_beside_a_connector():
    doc = example()
    doc["modules"] = [{"module_id": "ratings.extra"}]
    assert refused(doc).code == "MODULES_DERIVED"


def test_a_connector_pack_has_one_namespace():
    doc = example()
    doc["pack"]["namespaces"] = ["ratings", "other"]
    assert refused(doc).code == "INVALID_NAMESPACE"


def test_plain_http_is_refused_off_loopback():
    doc = example()
    doc["connector"]["base_url"] = "http://api.ratings.example"
    assert refused(doc).code == "INVALID_BASE_URL"


def test_duplicate_operation_ids_are_refused():
    doc = example()
    doc["connector"]["operations"].append(copy.deepcopy(operation(doc, "company.get")))
    assert refused(doc).code == "DUPLICATE_ID"


def test_a_body_input_on_a_read_is_refused():
    doc = example()
    operation(doc, "company.get")["inputs"]["note"] = {"type": "string", "in": "body"}
    error = refused(doc)
    assert error.code == "INVALID_CONNECTOR" and error.operation == "company.get"


def test_an_unknown_pagination_strategy_is_refused():
    doc = example()
    operation(doc, "findings.list")["paginate"]["strategy"] = "guess"
    error = refused(doc)
    assert error.code == "INVALID_PAGINATION" and error.operation == "findings.list"


def test_existing_packs_normalize_exactly_as_before():
    node = ROOT / "examples" / "packs" / "node-greeter"
    manifest = read_pack_manifest(node)
    assert "connector" not in manifest


# -- domain neutrality -----------------------------------------------------------


def test_no_provider_is_named_in_core_pack_code():
    provider = re.compile(r"(?i)bit" + r"sight")
    for path in (ROOT / "src" / "core" / "pack").glob("*.py"):
        assert not provider.search(path.read_text(encoding="utf-8")), path.name
    for path in EXAMPLE.rglob("*"):
        if path.is_file():
            assert not provider.search(path.read_text(encoding="utf-8")), path.name


# -- conformance -----------------------------------------------------------------


def test_the_example_is_conformant_offline(host_version_241):
    from core.pack.conformance import conform

    report = conform(EXAMPLE, run=True)
    verdicts = {item["check"]: item["verdict"] for item in report["results"]}
    assert report["conformant"] is True, report
    assert verdicts["installs"] == "pass"
    # Calling a connector reaches the provider, so the offline suite never does.
    assert verdicts["operations_called"] == "not_applicable"
