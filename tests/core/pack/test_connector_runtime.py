"""Connector operations run end to end against a local fake server.

The example pack is installed with its ``base_url`` pointed at a loopback
server that answers with recorded-shape responses. Nothing here reaches a
real provider, and the credential is a test value passed through the
execution context's ``secrets`` layer, by the name the pack declares.
"""

import asyncio
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from core.engine.hooks import ExecutorHooks, HookResult
from core.engine.step_executor.executor import StepExecutor
from core.engine.trace import TraceCollector
from core.engine.variable_resolver import VariableResolver
from core.modules.registry import ModuleRegistry
from core.pack.host import install_pack

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "packs" / "ratings-connector" / "flyto-pack.json"
RECORDED = json.loads((Path(__file__).parent / "fixtures" / "connector_recorded.json").read_text(encoding="utf-8"))
TOKEN = "test-token-not-real"


class Provider(BaseHTTPRequestHandler):
    seen = []
    status = 200
    retry_after = None

    def log_message(self, *args):
        return None

    def _reply(self, status, payload, headers=None):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode())
        Provider.seen.append({"path": self.path, "form": form, "auth": self.headers.get("Authorization")})
        if self.path == "/oauth/token":
            self._reply(200, {"access_token": "issued-access", "token_type": "Bearer", "expires_in": 3600})
        else:
            self._reply(404, {"detail": "no"})

    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        Provider.seen.append({"path": url.path, "query": query, "auth": self.headers.get("Authorization")})
        if Provider.status != 200:
            headers = {"Retry-After": Provider.retry_after} if Provider.retry_after else None
            self._reply(Provider.status, {"detail": "provider said no"}, headers)
            return
        if url.path == "/v1/companies/c-1":
            self._reply(200, RECORDED["company"])
        elif url.path == "/v1/companies/c-1/findings":
            offset, limit = int(query.get("offset", 0)), int(query.get("limit", 100))
            page = RECORDED["findings"][offset:offset + limit]
            self._reply(200, {"count": len(RECORDED["findings"]), "results": page})
        elif url.path == "/v1/portfolio":
            self._reply(200, RECORDED["portfolio"])
        elif url.path == "/v1/text":
            raw = b"not json"
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        else:
            self._reply(404, {"detail": "not found"})


@pytest.fixture
def provider(monkeypatch):
    Provider.seen = []
    Provider.status = 200
    Provider.retry_after = None
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    # The SSRF guard admits this loopback server only because the test says so.
    monkeypatch.setenv("FLYTO_ALLOWED_HOSTS", "127.0.0.1")
    monkeypatch.setenv("FLYTO_HTTP_ALLOWED_PORTS", str(port))
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()


def ungated(doc):
    """The example without its pre-check, so these tests exercise the transport alone.

    Entitlements, quota and data scope are covered by
    ``test_connector_entitlements.py`` against the full example.
    """
    doc.pop("entitlements", None)
    doc.pop("scopes", None)
    doc["connector"]["operations"] = [
        o for o in doc["connector"]["operations"] if not o.get("consumes") and o["consequence"] == "observe"
    ]
    for operation in doc["connector"]["operations"]:
        operation.pop("requires", None)
        operation.pop("result_scope", None)
        for spec in operation["inputs"].values():
            spec.pop("scope", None)
    return doc


def install(tmp_path, base_url, mutate=None):
    doc = ungated(json.loads(EXAMPLE.read_text(encoding="utf-8")))
    doc["connector"]["base_url"] = base_url
    if mutate:
        mutate(doc)
    pack = tmp_path / "ratings"
    pack.mkdir()
    (pack / "flyto-pack.json").write_text(json.dumps(doc), encoding="utf-8")
    return install_pack(pack, require_signature=False)


def op(doc, op_id):
    return next(o for o in doc["connector"]["operations"] if o["id"] == op_id)


async def call(module_id, params, secrets=None):
    context = {"secrets": {"ratings_api_token": TOKEN} if secrets is None else secrets}
    return await ModuleRegistry.get(module_id)(params, context).run()


# -- end to end --------------------------------------------------------------------


async def test_a_declared_operation_is_a_registered_module(tmp_path, provider, host_version_241):
    provenance = install(tmp_path, provider)
    assert provenance.binding == "connector"
    assert set(provenance.module_ids) == {
        "ratings.account.entitlements", "ratings.company.get", "ratings.findings.list", "ratings.portfolio.list",
    }
    metadata = ModuleRegistry.get_metadata("ratings.company.get")
    assert metadata["plugin"] == "com.example.ratings"
    assert metadata["contract"]["safety_class"] == "read_only"


async def test_an_operation_called_end_to_end(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    result = await call("ratings.company.get", {"company": "c-1"})
    assert result == {"ok": True, "data": RECORDED["company"]}
    request = Provider.seen[-1]
    assert request["path"] == "/v1/companies/c-1"
    # scheme Basic: the token is the user name, the password is empty.
    assert request["auth"] == "Basic " + base64.b64encode(f"{TOKEN}:".encode()).decode()


async def test_a_path_parameter_is_encoded_as_one_segment(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    result = await call("ratings.company.get", {"company": "../portfolio"})
    assert result["ok"] is False
    assert Provider.seen[-1]["path"] == "/v1/companies/..%2Fportfolio"


async def test_pagination_collects_every_page(tmp_path, provider, host_version_241):
    install(tmp_path, provider, lambda doc: op(doc, "findings.list")["paginate"].update(page_size=2))
    result = await call("ratings.findings.list", {"company": "c-1", "severity": "material"})
    assert result["ok"] is True
    assert result["data"]["items"] == RECORDED["findings"]
    assert result["data"]["pages_fetched"] == 2
    pages = [r["query"] for r in Provider.seen if r["path"].endswith("/findings")]
    assert pages == [
        {"severity": "material", "offset": "0", "limit": "2"},
        {"severity": "material", "offset": "2", "limit": "2"},
    ]


async def test_the_rate_limit_is_applied_across_operations(tmp_path, provider, host_version_241, monkeypatch):
    import core.modules.integrations.base.rate_limiter as limiter_module

    class Clock:
        Lock = asyncio.Lock
        waits = []

        @staticmethod
        async def sleep(seconds):
            Clock.waits.append(seconds)

    monkeypatch.setattr(limiter_module, "asyncio", Clock)
    install(tmp_path, provider, lambda doc: doc["connector"].update(rate_limit={"requests": 2, "per_seconds": 60}))
    for module_id, params in [
        ("ratings.company.get", {"company": "c-1"}),
        ("ratings.portfolio.list", {}),
        ("ratings.company.get", {"company": "c-1"}),
    ]:
        assert (await call(module_id, params))["ok"] is True
    assert len(Clock.waits) == 1 and 29 < Clock.waits[0] <= 30


# -- credentials ---------------------------------------------------------------------


async def test_a_missing_credential_fails_closed_before_any_request(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    result = await call("ratings.company.get", {"company": "c-1"}, secrets={})
    assert result["ok"] is False and result["error_code"] == "CREDENTIAL_MISSING"
    assert "ratings_api_token" in result["error"]
    assert Provider.seen == []


async def test_oauth2_client_credentials_exchanges_then_sends_a_bearer(tmp_path, provider, host_version_241):
    def oauth(doc):
        doc["connector"]["auth"] = [{
            "kind": "oauth2_client_credentials",
            "token_url": provider + "/oauth/token",
            "scopes": ["read"],
            "credential": "ratings_client",
        }]

    install(tmp_path, provider, oauth)
    secrets = {"ratings_client": {"client_id": "cid", "client_secret": "csecret"}}
    assert (await call("ratings.company.get", {"company": "c-1"}, secrets=secrets))["ok"] is True
    assert (await call("ratings.portfolio.list", {}, secrets=secrets))["ok"] is True
    token_calls = [r for r in Provider.seen if r["path"] == "/oauth/token"]
    assert len(token_calls) == 1  # the issued token is reused until it expires
    assert token_calls[0]["form"]["grant_type"] == ["client_credentials"]
    assert token_calls[0]["form"]["scope"] == ["read"]
    assert Provider.seen[-1]["auth"] == "Bearer issued-access"


# -- typed failures --------------------------------------------------------------------


@pytest.mark.parametrize(
    "status, code",
    [(401, "PROVIDER_UNAUTHORIZED"), (403, "PROVIDER_FORBIDDEN"), (404, "PROVIDER_NOT_FOUND"),
     (429, "PROVIDER_RATE_LIMITED"), (500, "PROVIDER_ERROR"), (503, "PROVIDER_ERROR"),
     (400, "PROVIDER_REJECTED")],
)
async def test_an_http_failure_is_a_typed_failure(tmp_path, provider, host_version_241, status, code):
    install(tmp_path, provider)
    Provider.status = status
    result = await call("ratings.company.get", {"company": "c-1"})
    assert result["ok"] is False
    assert result["error_code"] == code
    assert result["http_status"] == status
    assert "data" not in result


async def test_a_429_reports_when_to_retry(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    Provider.status, Provider.retry_after = 429, "7"
    result = await call("ratings.company.get", {"company": "c-1"})
    assert result["error_code"] == "PROVIDER_RATE_LIMITED" and result["retry_after_s"] == 7


async def test_a_failure_on_a_later_page_fails_the_whole_call(tmp_path, provider, host_version_241):
    install(tmp_path, provider, lambda doc: op(doc, "findings.list")["paginate"].update(page_size=2))

    original = Provider.do_GET

    def fail_second_page(self):
        if "offset=2" in self.path:
            Provider.status = 500
        try:
            original(self)
        finally:
            Provider.status = 200

    Provider.do_GET = fail_second_page
    try:
        result = await call("ratings.findings.list", {"company": "c-1"})
    finally:
        Provider.do_GET = original
    assert result["ok"] is False and result["error_code"] == "PROVIDER_ERROR"


async def test_a_body_that_is_not_json_is_a_typed_failure(tmp_path, provider, host_version_241):
    def text_op(doc):
        doc["connector"]["operations"].append({
            "id": "text.get", "method": "GET", "path": "/v1/text", "consequence": "observe", "inputs": {},
        })

    install(tmp_path, provider, text_op)
    result = await call("ratings.text.get", {})
    assert result["ok"] is False and result["error_code"] == "PROVIDER_INVALID_RESPONSE"


async def test_an_unreachable_provider_is_a_typed_failure(tmp_path, monkeypatch, host_version_241):
    monkeypatch.setenv("FLYTO_ALLOWED_HOSTS", "127.0.0.1")
    monkeypatch.setenv("FLYTO_HTTP_ALLOWED_PORTS", "9")
    install(tmp_path, "http://127.0.0.1:9")
    result = await call("ratings.company.get", {"company": "c-1"})
    assert result["ok"] is False and result["error_code"] == "PROVIDER_UNREACHABLE"


async def test_a_blocked_address_is_refused_before_sending(tmp_path, monkeypatch, host_version_241):
    monkeypatch.delenv("FLYTO_ALLOWED_HOSTS", raising=False)
    install(tmp_path, "http://127.0.0.1:1")
    result = await call("ratings.company.get", {"company": "c-1"})
    assert result["ok"] is False and result["error_code"] == "SSRF_BLOCKED"


# -- sensitive paths in the step log -----------------------------------------------------


class RecordingHooks(ExecutorHooks):
    def __init__(self):
        self.post = []

    def on_post_execute(self, context):
        self.post.append(context)
        return HookResult.continue_execution()


async def run_step(step, context):
    hooks = RecordingHooks()
    collector = TraceCollector("wf", "wf")
    collector.start()
    executor = StepExecutor(hooks=hooks, workflow_id="wf", workflow_name="wf", total_steps=1)
    result = await executor.execute_step(
        step_config=step, step_index=0, context=context,
        resolver=VariableResolver({}, context), trace_collector=collector,
    )
    return result, hooks.post[-1], collector.get_trace().to_dict()


async def test_a_sensitive_result_path_is_redacted_in_the_step_log_only(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    context = {"secrets": {"ratings_api_token": TOKEN}}
    step = {"id": "findings", "module": "ratings.findings.list", "params": {"company": "c-1"}}
    result, post, trace = await run_step(step, context)

    # The workflow -- the next step, the caller -- receives every value.
    assert [item["assets"] for item in result["data"]["items"]] == [f["assets"] for f in RECORDED["findings"]]
    assert context["findings"]["data"]["items"][0]["assets"] == ["10.0.0.1:22"]
    # The step log and the trace do not.
    logged = post.result["data"]["items"]
    assert all(item["assets"] == "[REDACTED]" for item in logged)
    assert logged[0]["risk_vector"] == "open_ports"  # only the declared leaves
    assert "10.0.0.1:22" not in json.dumps(trace)
    assert "host-a.example" not in json.dumps(trace)


async def test_a_secret_input_is_redacted_in_the_step_log_but_sent(tmp_path, provider, host_version_241):
    def secret_input(doc):
        op(doc, "portfolio.list")["inputs"]["access_code"] = {"type": "string", "secret": True}

    install(tmp_path, provider, secret_input)
    context = {"secrets": {"ratings_api_token": TOKEN}}
    step = {"id": "p", "module": "ratings.portfolio.list", "params": {"access_code": "code-xyz-123"}}
    result, post, trace = await run_step(step, context)
    assert result["ok"] is True
    assert Provider.seen[-1]["query"] == {"access_code": "code-xyz-123"}
    assert post.params["access_code"] == "[REDACTED]"
    assert "code-xyz-123" not in json.dumps(trace)


async def test_the_credential_never_reaches_the_step_log(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    context = {"secrets": {"ratings_api_token": TOKEN}}
    step = {"id": "c", "module": "ratings.company.get", "params": {"company": "c-1"}}
    _, post, trace = await run_step(step, context)
    assert TOKEN not in repr(post.params) + repr(post.result) + json.dumps(trace)


async def test_an_http_failure_fails_the_step(tmp_path, provider, host_version_241):
    install(tmp_path, provider)
    Provider.status = 500
    context = {"secrets": {"ratings_api_token": TOKEN}}
    step = {"id": "c", "module": "ratings.company.get", "params": {"company": "c-1"}, "on_error": "continue"}
    result, post, _ = await run_step(step, context)
    # Absorbed by on_error: continue, and still a failure: never an empty success.
    assert result["ok"] is False and "PROVIDER_ERROR" in result["error"]
    assert post.error is not None
