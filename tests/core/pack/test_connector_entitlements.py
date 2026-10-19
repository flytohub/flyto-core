"""The connector pre-check: entitlements read from the provider, quotas, and data scope.

The example pack is installed against a loopback fake provider with two
customers, told apart by their credential: one holds the ``ratings`` feature
only, the other ``ratings`` and ``monitoring`` with a ``monitoring_slots``
meter. Nothing here reaches a real provider; every credential is a test value
passed through the execution context's ``secrets`` layer.

The provider is the authority on its own product. The pre-check only hides
operations and stops a call early; a provider refusal is final whatever the
cached probe said.
"""

import base64
import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

from core.modules.registry import ModuleRegistry
from core.pack.host import effective_module_ids, install_pack
from core.pack.manifest import PackManifestError, validate_pack_manifest

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "packs" / "ratings-connector" / "flyto-pack.json"
RECORDED = json.loads((Path(__file__).parent / "fixtures" / "connector_recorded.json").read_text(encoding="utf-8"))
PACK_ID = "com.example.ratings"

TOKEN_A = "test-token-customer-a"
TOKEN_AB = "test-token-customer-ab"
INBOUND = "inbound-client-bearer-not-for-the-provider"
CUSTOMERS = {TOKEN_A: "ratings_only", TOKEN_AB: "ratings_and_monitoring"}
ALL = {"company": "*"}


class Provider(BaseHTTPRequestHandler):
    seen = []
    probe_status = 200
    probe_body = None  # overrides the recorded answer when set
    op_status = 200
    portfolio = None
    remaining = {}

    def log_message(self, *args):
        return None

    def _reply(self, status, payload):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _customer(self):
        header = self.headers.get("Authorization") or ""
        if not header.startswith("Basic "):
            return None
        user = base64.b64decode(header[6:]).decode().split(":", 1)[0]
        return CUSTOMERS.get(user)

    def _record(self, body=None):
        url = urlparse(self.path)
        Provider.seen.append({"method": self.command, "path": url.path, "headers": dict(self.headers),
                              "body": body})
        return url.path

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode() or "null")
        path = self._record(body)
        customer = self._customer()
        if customer is None:
            return self._reply(401, {"detail": "unknown credential"})
        if Provider.op_status != 200:
            return self._reply(Provider.op_status, {"detail": "provider said no"})
        if path == "/v1/portfolio/companies":
            Provider.remaining[customer] -= 1
            return self._reply(200, {**RECORDED["portfolio_added"], "guid": body["company"]})
        return self._reply(404, {"detail": "not found"})

    def do_GET(self):
        path = self._record()
        customer = self._customer()
        if customer is None:
            return self._reply(401, {"detail": "unknown credential"})
        if path == "/v1/account/entitlements":
            if Provider.probe_status != 200:
                return self._reply(Provider.probe_status, {"detail": "entitlements unavailable"})
            if Provider.probe_body is not None:
                return self._reply(200, Provider.probe_body)
            answer = copy.deepcopy(RECORDED["entitlements"][customer])
            answer["meters"]["monitoring_slots"]["remaining"] = Provider.remaining[customer]
            return self._reply(200, answer)
        if Provider.op_status != 200:
            return self._reply(Provider.op_status, {"detail": "provider said no"})
        if path.startswith("/v1/companies/"):
            return self._reply(200, {**RECORDED["company"], "guid": path.rsplit("/", 1)[1]})
        if path == "/v1/portfolio":
            return self._reply(200, Provider.portfolio or RECORDED["portfolio"])
        return self._reply(404, {"detail": "not found"})


@pytest.fixture
def provider(monkeypatch):
    Provider.seen = []
    Provider.probe_status = 200
    Provider.probe_body = None
    Provider.op_status = 200
    Provider.portfolio = None
    Provider.remaining = {
        name: RECORDED["entitlements"][name]["meters"]["monitoring_slots"]["remaining"]
        for name in CUSTOMERS.values()
    }
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    monkeypatch.setenv("FLYTO_ALLOWED_HOSTS", "127.0.0.1")
    monkeypatch.setenv("FLYTO_HTTP_ALLOWED_PORTS", str(port))
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()


def example():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def install(tmp_path, base_url, mutate=None):
    doc = example()
    doc["connector"]["base_url"] = base_url
    if mutate:
        mutate(doc)
    pack = tmp_path / "ratings"
    pack.mkdir()
    (pack / "flyto-pack.json").write_text(json.dumps(doc), encoding="utf-8")
    return install_pack(pack, require_signature=False)


def secrets(token):
    return {"ratings_api_token": token}


async def call(module_id, params, token=TOKEN_AB, grants=ALL, **extra):
    context = {"secrets": secrets(token), **extra}
    if grants is not None:
        context["scope_grants"] = grants
    return await ModuleRegistry.get(module_id)(params, context).run()


def requests_to(path, method=None):
    return [r for r in Provider.seen if r["path"] == path and (method is None or r["method"] == method)]


PROBE = "/v1/account/entitlements"
ADD = "/v1/portfolio/companies"


# -- the effective listing ---------------------------------------------------------


async def test_a_customer_without_a_feature_is_not_offered_its_operations(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    offered_a = await effective_module_ids(PACK_ID, secrets(TOKEN_A))
    offered_ab = await effective_module_ids(PACK_ID, secrets(TOKEN_AB))
    assert "ratings.portfolio.add" not in offered_a
    assert {"ratings.company.get", "ratings.findings.list", "ratings.portfolio.list"} <= set(offered_a)
    assert "ratings.portfolio.add" in offered_ab


async def test_an_unreadable_probe_offers_no_gated_operation(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    Provider.probe_status = 500
    offered = await effective_module_ids(PACK_ID, secrets(TOKEN_AB))
    # Only what needs no feature: the probe itself.
    assert offered == ["ratings.account.entitlements"]


# -- features ----------------------------------------------------------------------


async def test_calling_an_unentitled_operation_is_refused_before_the_call(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    result = await call("ratings.portfolio.add", {"company": "c-1"}, token=TOKEN_A)
    assert result["ok"] is False and result["error_code"] == "FEATURE_NOT_ENTITLED"
    assert result["missing_features"] == ["monitoring"]
    assert requests_to(ADD) == []


async def test_an_entitled_read_runs_and_says_it_was_pre_checked(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    result = await call("ratings.company.get", {"company": "c-1"}, token=TOKEN_A)
    assert result["ok"] is True and result["data"]["guid"] == "c-1"
    precheck = result["metadata"]["precheck"]
    assert precheck["features"] == ["ratings"]
    assert precheck["entitlements"] == "provider"


async def test_a_read_may_use_the_cached_answer(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    assert (await call("ratings.company.get", {"company": "c-1"}))["ok"] is True
    second = await call("ratings.company.get", {"company": "c-1"})
    assert second["ok"] is True and second["metadata"]["precheck"]["entitlements"] == "cache"
    assert len(requests_to(PROBE)) == 1


async def test_the_cache_is_bounded_by_the_pack(tmp_path, provider, host_version_241, monkeypatch):
    import core.pack.connector_gate as gate

    now = [1000.0]
    monkeypatch.setattr(gate, "_now", lambda: now[0])
    install(tmp_path, provider, lambda doc: doc["entitlements"].update(max_age_s=60))
    assert (await call("ratings.company.get", {"company": "c-1"}))["ok"] is True
    now[0] += 61
    assert (await call("ratings.company.get", {"company": "c-1"}))["ok"] is True
    assert len(requests_to(PROBE)) == 2


async def test_the_probe_is_read_per_credential(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    assert (await call("ratings.portfolio.add", {"company": "c-1"}, token=TOKEN_AB))["ok"] is True
    refused = await call("ratings.portfolio.add", {"company": "c-1"}, token=TOKEN_A)
    assert refused["error_code"] == "FEATURE_NOT_ENTITLED"


async def test_a_failing_probe_refuses_a_write_even_with_a_cached_answer(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    assert (await call("ratings.company.get", {"company": "c-1"}))["ok"] is True  # caches "entitled"
    Provider.probe_status = 500
    result = await call("ratings.portfolio.add", {"company": "c-1"})
    assert result["ok"] is False and result["error_code"] == "PROVIDER_ENTITLEMENT_UNREADABLE"
    assert requests_to(ADD) == []


async def test_a_failing_probe_drops_the_cached_answer(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    assert (await call("ratings.company.get", {"company": "c-1"}))["ok"] is True
    Provider.probe_status = 500
    assert (await call("ratings.portfolio.add", {"company": "c-1"}))["ok"] is False
    # The failed read shortened the grant; the next read cannot use the old answer.
    result = await call("ratings.company.get", {"company": "c-1"})
    assert result["error_code"] == "PROVIDER_ENTITLEMENT_UNREADABLE"


@pytest.mark.parametrize("body", [
    {"features": "ratings", "meters": {"monitoring_slots": {"remaining": 2}}},
    {"features": ["ratings", 7], "meters": {"monitoring_slots": {"remaining": 2}}},
    {"meters": {"monitoring_slots": {"remaining": 2}}},
    {"features": ["ratings"], "meters": {}},
    {"features": ["ratings"], "meters": {"monitoring_slots": {"remaining": -1}}},
    {"features": ["ratings"], "meters": {"monitoring_slots": {"remaining": "2"}}},
    [],
])
async def test_a_probe_answer_outside_its_shape_is_unreadable(tmp_path, provider, host_version_241, body):
    install(tmp_path, provider)
    Provider.probe_body = body
    result = await call("ratings.company.get", {"company": "c-1"})
    assert result["ok"] is False and result["error_code"] == "PROVIDER_ENTITLEMENT_UNREADABLE"
    assert requests_to("/v1/companies/c-1") == []


async def test_a_call_after_a_provider_error_re_reads(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    assert (await call("ratings.company.get", {"company": "c-1"}))["ok"] is True
    Provider.op_status = 503
    assert (await call("ratings.company.get", {"company": "c-1"}))["error_code"] == "PROVIDER_ERROR"
    Provider.op_status = 200
    result = await call("ratings.company.get", {"company": "c-1"})
    assert result["ok"] is True and result["metadata"]["precheck"]["entitlements"] == "provider"
    assert len(requests_to(PROBE)) == 2


async def test_an_ungated_operation_never_reads_the_probe(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    result = await call("ratings.account.entitlements", {}, grants=None)
    assert result["ok"] is True
    assert len(requests_to(PROBE)) == 1  # the call itself, no pre-check read


# -- the provider stays the authority ------------------------------------------------


async def test_a_provider_refusal_is_final_whatever_the_cache_said(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    assert (await call("ratings.company.get", {"company": "c-1"}))["ok"] is True
    Provider.op_status = 403
    result = await call("ratings.company.get", {"company": "c-1"})
    assert result["ok"] is False and result["error_code"] == "PROVIDER_FORBIDDEN"
    assert "data" not in result


async def test_a_refused_write_is_its_own_failure_and_is_not_retried(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    Provider.op_status = 402
    result = await call("ratings.portfolio.add", {"company": "c-1"})
    assert result["ok"] is False and result["error_code"] == "PROVIDER_QUOTA_REFUSED"
    assert len(requests_to(ADD, "POST")) == 1


async def test_an_inbound_bearer_token_never_reaches_the_provider(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    inbound = {
        "authorization": f"Bearer {INBOUND}",
        "headers": {"Authorization": f"Bearer {INBOUND}"},
        "auth": {"access_token": INBOUND, "token_type": "Bearer"},
        "mcp": {"access_token": INBOUND},
    }
    result = await call("ratings.company.get", {"company": "c-1"}, **inbound)
    assert result["ok"] is True
    stored = "Basic " + base64.b64encode(f"{TOKEN_AB}:".encode()).decode()
    assert {r["headers"].get("Authorization") for r in Provider.seen} == {stored}
    assert all(INBOUND not in json.dumps(r) for r in Provider.seen)


async def test_an_inbound_bearer_token_is_no_substitute_for_the_stored_credential(
    tmp_path, provider, host_version_241
):
    install(tmp_path, provider)
    context = {"secrets": {}, "scope_grants": ALL, "authorization": f"Bearer {INBOUND}",
               "headers": {"Authorization": f"Bearer {INBOUND}"}}
    result = await ModuleRegistry.get("ratings.company.get")({"company": "c-1"}, context).run()
    assert result["error_code"] == "CREDENTIAL_MISSING"
    assert Provider.seen == []


# -- quota -----------------------------------------------------------------------------


async def test_a_quota_consuming_call_records_the_meter_before_and_after(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    result = await call("ratings.portfolio.add", {"company": "c-1"})
    assert result["ok"] is True
    assert result["metadata"]["precheck"]["meter"] == {
        "meter": "monitoring_slots", "amount": 1, "before": 2, "after": 1, "matches": True,
    }


async def test_quota_exhaustion_refuses_before_the_call(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    Provider.remaining["ratings_and_monitoring"] = 0
    result = await call("ratings.portfolio.add", {"company": "c-1"})
    assert result["ok"] is False and result["error_code"] == "QUOTA_EXHAUSTED"
    assert result["meter"] == "monitoring_slots" and result["remaining"] == 0
    assert requests_to(ADD) == []


async def test_a_quota_consuming_call_re_reads_the_probe(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    assert (await call("ratings.company.get", {"company": "c-1"}))["ok"] is True  # cached: 2 remaining
    Provider.remaining["ratings_and_monitoring"] = 0  # spent elsewhere, directly at the provider
    result = await call("ratings.portfolio.add", {"company": "c-1"})
    assert result["error_code"] == "QUOTA_EXHAUSTED"


# -- data scope ------------------------------------------------------------------------


async def test_an_out_of_scope_input_is_refused(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    result = await call("ratings.company.get", {"company": "c-1"}, grants={"company": ["c-2"]})
    assert result["ok"] is False and result["error_code"] == "OUT_OF_SCOPE"
    assert result["dimension"] == "company"
    assert requests_to("/v1/companies/c-1") == []


@pytest.mark.parametrize("grants", [None, {}, {"business_unit": "*"}, {"company": "all"}, {"company": [1]}])
async def test_no_grant_for_a_declared_dimension_is_refused(tmp_path, provider, host_version_241, grants):
    install(tmp_path, provider)
    result = await call("ratings.company.get", {"company": "c-1"}, grants=grants)
    assert result["ok"] is False and result["error_code"] == "SCOPE_GRANT_MISSING"
    assert requests_to("/v1/companies/c-1") == []


async def test_a_result_row_for_another_company_is_dropped_and_counted(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    result = await call("ratings.portfolio.list", {}, grants={"company": ["c-1"]})
    assert result["ok"] is True
    assert [c["guid"] for c in result["data"]["companies"]] == ["c-1"]
    assert result["metadata"]["precheck"]["scope"] == {"dimension": "company", "kept": 1, "dropped": 1}


async def test_an_all_grant_keeps_every_row(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    result = await call("ratings.portfolio.list", {})
    assert [c["guid"] for c in result["data"]["companies"]] == ["c-1", "c-2"]
    assert result["metadata"]["precheck"]["scope"]["dropped"] == 0


@pytest.mark.parametrize("portfolio", [
    {"companies": [{"guid": "c-1"}, {"name": "No identifier"}]},
    {"companies": [{"guid": "c-1"}, {"guid": {"nested": "c-2"}}]},
    {"items": []},
    {"companies": {"guid": "c-1"}},
])
async def test_a_result_that_does_not_name_its_scope_value_is_refused(tmp_path, provider, host_version_241,
                                                                      portfolio):
    install(tmp_path, provider)
    Provider.portfolio = portfolio
    result = await call("ratings.portfolio.list", {}, grants={"company": ["c-1"]})
    assert result["ok"] is False and result["error_code"] == "RESULT_SCOPE_UNREADABLE"
    assert "data" not in result


async def test_a_single_result_outside_the_grant_is_refused_not_emptied(tmp_path, provider, host_version_241):
    install(tmp_path, provider, lambda doc: next(
        o for o in doc["connector"]["operations"] if o["id"] == "company.get"
    )["inputs"]["company"].pop("scope"))
    result = await call("ratings.company.get", {"company": "c-2"}, grants={"company": ["c-1"]})
    assert result["ok"] is False and result["error_code"] == "OUT_OF_SCOPE"
    assert "data" not in result


# -- validation of the declarations -----------------------------------------------------


def refused(doc):
    with pytest.raises(PackManifestError) as caught:
        validate_pack_manifest(doc)
    return caught.value


def op(doc, op_id):
    return next(o for o in doc["connector"]["operations"] if o["id"] == op_id)


def test_the_example_declares_entitlements_and_scopes():
    manifest = validate_pack_manifest(example())
    assert manifest["entitlements"] == {
        "probe": "account.entitlements",
        "max_age_s": 900,
        "features": {"keys": ["ratings", "monitoring"], "path": "$.features[*]"},
        "meters": {"monitoring_slots": "$.meters.monitoring_slots.remaining"},
    }
    assert manifest["scopes"] == [{"key": "company", "resolve": "portfolio.list"}]
    listed = next(o for o in manifest["connector"]["operations"] if o["id"] == "portfolio.list")
    assert listed["result_scope"] == {"dimension": "company", "path": "$.companies[*].guid"}


def test_the_cache_age_defaults_to_fifteen_minutes():
    doc = example()
    del doc["entitlements"]["max_age_s"]
    assert validate_pack_manifest(doc)["entitlements"]["max_age_s"] == 900


@pytest.mark.parametrize("mutate, code", [
    (lambda d: op(d, "company.get").update(requires={"features": ["unknown_product"]}), "FEATURE_UNDECLARED"),
    (lambda d: op(d, "portfolio.add").update(consumes={"meter": "unknown_meter"}), "METER_UNDECLARED"),
    (lambda d: op(d, "company.get")["inputs"]["company"].update(scope="region"), "SCOPE_UNDECLARED"),
    (lambda d: op(d, "company.get").update(result_scope={"dimension": "region", "path": "$.guid"}),
     "SCOPE_UNDECLARED"),
    (lambda d: d.pop("entitlements"), "ENTITLEMENTS_REQUIRED"),
    (lambda d: d.pop("scopes"), "SCOPE_UNDECLARED"),
    (lambda d: d["entitlements"].update(probe="missing.op"), "PROBE_UNKNOWN"),
    (lambda d: d["entitlements"].update(probe="portfolio.add"), "PROBE_NOT_OBSERVE"),
    (lambda d: d["entitlements"].update(probe="company.get"), "PROBE_NOT_OBSERVE"),
    (lambda d: d["entitlements"]["features"].update(path="$..features"), "INVALID_JSONPATH"),
    (lambda d: d["entitlements"]["meters"].update(slots="not a path"), "INVALID_JSONPATH"),
    (lambda d: d["entitlements"].update(max_age_s=0), "INVALID_ENTITLEMENTS"),
    (lambda d: d["entitlements"].update(max_age_s=86_401), "INVALID_ENTITLEMENTS"),
    (lambda d: d["entitlements"].update(extra=1), "UNKNOWN_KEY"),
    (lambda d: d["scopes"].append({"key": "company"}), "DUPLICATE_ID"),
    (lambda d: d["scopes"][0].update(resolve="missing.op"), "RESOLVE_UNKNOWN"),
    (lambda d: d["scopes"].append({"key": "business_unit"}), "RESULT_SCOPE_DIMENSION_REQUIRED"),
])
def test_a_declaration_the_gate_could_not_enforce_is_refused(mutate, code):
    doc = example()
    mutate(doc)
    assert refused(doc).code == code


def test_entitlements_need_the_connector_binding():
    doc = example()
    doc["runtime"] = {"binding": "http", "locality": "same_host"}
    doc.pop("connector")
    doc["modules"] = [{"module_id": "ratings.x", "label": "x"}]
    assert refused(doc).code == "CONNECTOR_BINDING"
