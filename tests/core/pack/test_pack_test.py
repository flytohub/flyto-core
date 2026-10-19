"""``flyto pack test``: a pack's operations run against its recorded fixtures, offline.

The fixtures are recorded exchanges (a request and the provider's answer)
plus the calls to make and what each should come back as. A loopback fake
provider is built from the exchanges alone, and every call goes through the
real connector runtime and the real pre-check gate: the module registry,
the credential resolved by name from ``secrets``, the entitlements probe, the
scope grants and the result filter. Nothing reaches a real provider.

Each operation is reported on its own, with typed failures: a sensitive path
or a result path that names nothing in what was recorded, a ``result_scope``
that never named an item, a probe answer outside its declared shape, a
request nobody recorded, an operation no call exercises. The offline
conformance suite (``pack conform``) runs as part of it.
"""

import copy
import json
import os
import shutil

import pytest
from devkit_helpers import ROOT, cli, decided_scaffold, edit_json, operation, read_json, write_json

from core.pack.recorded import (
    FIXTURES_PATH,
    FIXTURES_SCHEMA,
    render,
    run_pack_tests,
    run_pack_tests_async,
)

RATINGS = ROOT / "examples" / "packs" / "ratings-connector"
RECORDED = read_json(ROOT / "tests" / "core" / "pack" / "fixtures" / "connector_recorded.json")


def by_operation(report):
    return {item["operation"]: item for item in report["operations"]}


def codes(report, op_id):
    return [failure["code"] for failure in by_operation(report)[op_id]["failures"]]


def ratings_fixtures():
    entitlements = RECORDED["entitlements"]
    company = {**RECORDED["company"], "guid": "c-1"}
    return {
        "schema": FIXTURES_SCHEMA,
        "customers": {
            "ratings_only": {"credential": "fixture-token-a",
                             "offered": ["account.entitlements", "company.get", "findings.list", "portfolio.list"]},
            "ratings_and_monitoring": {"credential": "fixture-token-ab"},
        },
        "exchanges": [
            {"customer": "ratings_only", "request": {"method": "GET", "path": "/v1/account/entitlements"},
             "response": {"status": 200, "body": entitlements["ratings_only"]}},
            {"customer": "ratings_and_monitoring", "request": {"method": "GET", "path": "/v1/account/entitlements"},
             "response": {"status": 200, "body": entitlements["ratings_and_monitoring"]}},
            {"request": {"method": "GET", "path": "/v1/companies/c-1"}, "response": {"body": company}},
            {"request": {"method": "GET", "path": "/v1/companies/c-1/findings", "query": {"offset": "0"}},
             "response": {"body": {"results": RECORDED["findings"]}}},
            {"request": {"method": "GET", "path": "/v1/portfolio"}, "response": {"body": RECORDED["portfolio"]}},
            {"request": {"method": "POST", "path": "/v1/portfolio/companies", "body": {"company": "c-1"}},
             "response": {"body": RECORDED["portfolio_added"]}},
        ],
        "calls": [
            {"operation": "company.get", "customer": "ratings_only", "input": {"company": "c-1"}},
            {"operation": "findings.list", "customer": "ratings_only", "input": {"company": "c-1"}},
            {"operation": "portfolio.list", "customer": "ratings_only", "grants": {"company": ["c-1"]}},
            {"operation": "portfolio.add", "customer": "ratings_and_monitoring", "input": {"company": "c-1"}},
            {"operation": "portfolio.add", "customer": "ratings_only", "input": {"company": "c-1"},
             "expect": {"error_code": "FEATURE_NOT_ENTITLED"}},
        ],
    }


@pytest.fixture
def ratings(tmp_path):
    target = tmp_path / "ratings"
    shutil.copytree(RATINGS, target)
    (target / FIXTURES_PATH).parent.mkdir(exist_ok=True)
    write_json(target / FIXTURES_PATH, ratings_fixtures())
    return target


def fixtures_of(pack_dir, change):
    return edit_json(pack_dir / FIXTURES_PATH, change)


# -- a pack that passes -------------------------------------------------------------------


def test_the_decided_scaffold_passes_every_operation_and_conformance(tmp_path):
    report = run_pack_tests(decided_scaffold(tmp_path))
    assert report["passed"] is True, render(report)
    assert [item["operation"] for item in report["operations"]] == ["account.entitlements", "item.get"]
    assert all(item["verdict"] == "pass" for item in report["operations"])
    assert report["conformance"]["conformant"] is True
    assert report["probe"]["example_customer"]["features"] == ["items"]


def test_the_ratings_example_passes_with_recorded_exchanges(ratings):
    report = run_pack_tests(ratings)
    assert report["passed"] is True, render(report)
    ops = by_operation(report)
    assert ops["portfolio.add"]["calls"] == 2
    assert ops["findings.list"]["checks"]["sensitive"] == {"$.items[*].assets": "matched"}
    assert ops["portfolio.list"]["checks"]["result_scope"] == "matched"
    assert ops["findings.list"]["checks"]["data_path"] == "matched"


def test_the_gate_really_runs_a_refusal_is_the_gates_own(ratings):
    # The fixture expects a feature refusal; if the expectation is changed to
    # success, the real gate's refusal shows up as the typed mismatch.
    fixtures_of(ratings, lambda doc: doc["calls"][4].pop("expect"))
    report = run_pack_tests(ratings)
    failure = by_operation(report)["portfolio.add"]["failures"][0]
    assert failure["code"] == "UNEXPECTED_RESULT"
    assert failure["actual"] == "FEATURE_NOT_ENTITLED"


def test_the_credential_reaches_the_fake_provider_by_name_only(ratings):
    # A customer whose credential the fake does not know is answered 401 by
    # it, so the call fails as the provider refusing it, not as a pass.
    fixtures_of(ratings, lambda doc: doc["calls"].append(
        {"operation": "company.get", "customer": "ratings_only", "input": {"company": "c-1"},
         "secrets": {"ratings_api_token": "a-different-value"}}))
    report = run_pack_tests(ratings)
    assert "UNEXPECTED_RESULT" in codes(report, "company.get")


# -- typed failures, per operation ----------------------------------------------------------


def test_a_sensitive_path_that_names_nothing_recorded_fails_that_operation_only(ratings):
    edit_json(ratings / "flyto-pack.json",
              lambda doc: operation(doc, "findings.list").update(sensitive=["$.items[*].asset"]))
    report = run_pack_tests(ratings)
    assert report["passed"] is False
    assert codes(report, "findings.list") == ["SENSITIVE_PATH_UNMATCHED"]
    assert by_operation(report)["findings.list"]["failures"][0]["path"] == "$.items[*].asset"
    assert codes(report, "company.get") == []


def test_a_data_path_that_names_no_list_in_a_recorded_page_fails(ratings):
    edit_json(ratings / "flyto-pack.json",
              lambda doc: operation(doc, "findings.list")["paginate"].update(data_path="result"))
    report = run_pack_tests(ratings)
    assert "DATA_PATH_UNMATCHED" in codes(report, "findings.list")


def test_a_result_scope_that_names_no_item_fails_typed(ratings):
    edit_json(ratings / "flyto-pack.json",
              lambda doc: operation(doc, "company.get").update(result_scope="$.company_guid"))
    report = run_pack_tests(ratings)
    assert codes(report, "company.get") == ["RESULT_SCOPE_UNMATCHED"]


def test_a_probe_answer_outside_its_declared_shape_fails_typed(ratings):
    def misshapen(doc):
        doc["exchanges"][0]["response"]["body"] = {"features": "ratings", "meters": {}}
    fixtures_of(ratings, misshapen)
    report = run_pack_tests(ratings)
    assert report["passed"] is False
    assert report["probe"]["ratings_only"]["code"] == "PROBE_SHAPE_INVALID"
    assert "PROBE_SHAPE_INVALID" in codes(report, "account.entitlements")


def test_a_request_nobody_recorded_is_named(ratings):
    fixtures_of(ratings, lambda doc: doc["exchanges"].pop(4))  # the portfolio page
    report = run_pack_tests(ratings)
    failure = next(f for f in by_operation(report)["portfolio.list"]["failures"] if f["code"] == "UNRECORDED_REQUEST")
    assert failure["request"] == "GET /v1/portfolio"


def test_an_operation_no_call_exercises_fails_untested(ratings):
    fixtures_of(ratings, lambda doc: doc.update(calls=[c for c in doc["calls"] if c["operation"] != "portfolio.list"]))
    report = run_pack_tests(ratings)
    assert codes(report, "portfolio.list") == ["OPERATION_UNTESTED"]


def test_the_operations_a_customer_is_offered_are_checked(ratings):
    fixtures_of(ratings, lambda doc: doc["customers"]["ratings_only"]["offered"].append("portfolio.add"))
    report = run_pack_tests(ratings)
    assert report["passed"] is False
    listing = report["customers"]["ratings_only"]
    assert listing["code"] == "EFFECTIVE_OPERATIONS_MISMATCH"
    assert listing["missing"] == ["portfolio.add"] and listing["unexpected"] == []


def test_conformance_runs_and_its_failure_fails_the_run(tmp_path):
    target = decided_scaffold(tmp_path)
    edit_json(target / "flyto-pack.json", lambda doc: doc["pack"].pop("min_host"))
    report = run_pack_tests(target)
    assert report["passed"] is False
    assert report["conformance"]["conformant"] is False
    assert "compatibility" in report["conformance"]["failed"]


# -- fixtures that cannot be read ---------------------------------------------------------------


@pytest.mark.parametrize("change, code", [
    (lambda doc: doc.update(schema="other"), "FIXTURES_INVALID"),
    (lambda doc: doc["calls"].append({"operation": "nothing.here"}), "FIXTURES_INVALID"),
    (lambda doc: doc["calls"].append({"operation": "item.get", "customer": "nobody"}), "FIXTURES_INVALID"),
    (lambda doc: doc.update(extra=1), "FIXTURES_INVALID"),
])
def test_fixtures_that_do_not_fit_the_pack_are_refused(tmp_path, capsys, change, code):
    target = decided_scaffold(tmp_path)
    fixtures_of(target, change)
    capsys.readouterr()
    assert cli("test", target) == 1
    assert f"[{code}]" in capsys.readouterr().err


def test_a_pack_without_fixtures_is_refused(tmp_path, capsys):
    target = decided_scaffold(tmp_path)
    (target / FIXTURES_PATH).unlink()
    capsys.readouterr()
    assert cli("test", target) == 1
    assert "[FIXTURES_MISSING]" in capsys.readouterr().err


def test_a_pack_that_is_not_a_connector_is_refused(tmp_path, capsys):
    target = tmp_path / "greeter"
    shutil.copytree(ROOT / "examples" / "packs" / "node-greeter", target)
    capsys.readouterr()
    assert cli("test", target) == 1
    assert "[NOT_A_CONNECTOR_PACK]" in capsys.readouterr().err


# -- the command ---------------------------------------------------------------------------------


def test_the_cli_reports_per_operation_and_exits_by_the_verdict(tmp_path, capsys):
    target = decided_scaffold(tmp_path)
    capsys.readouterr()
    assert cli("test", target) == 0
    out = capsys.readouterr().out
    assert "item.get" in out and "account.entitlements" in out and "passed" in out
    edit_json(target / "flyto-pack.json", lambda doc: operation(doc, "item.get").update(sensitive=["$.nope"]))
    assert cli("test", target, "--json") == 1
    report = json.loads(capsys.readouterr().out)
    assert by_operation(report)["item.get"]["failures"][0]["code"] == "SENSITIVE_PATH_UNMATCHED"


def test_the_run_leaves_the_host_as_it_found_it(tmp_path):
    from core.pack import host

    before = {key: os.environ.get(key) for key in ("FLYTO_ALLOWED_HOSTS", "FLYTO_HTTP_ALLOWED_PORTS")}
    run_pack_tests(decided_scaffold(tmp_path))
    assert {key: os.environ.get(key) for key in before} == before
    assert host._INSTALLED == {}


async def test_the_async_entry_point_matches_the_sync_one(tmp_path):
    target = decided_scaffold(tmp_path)
    report = await run_pack_tests_async(target)
    assert report["passed"] is True, render(report)


def test_a_fixture_copy_is_never_written_back(tmp_path):
    target = decided_scaffold(tmp_path)
    before = copy.deepcopy(read_json(target / FIXTURES_PATH))
    run_pack_tests(target)
    assert read_json(target / FIXTURES_PATH) == before
