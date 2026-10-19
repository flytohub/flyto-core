# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""``flyto pack test``: a connector pack's operations, run against its recorded fixtures.

A provider develops its pack offline. ``fixtures/exchanges.json``
(``flyto.pack-fixtures.v1``) holds:

* ``customers``: the accounts to test as, each with a **test** value for the
  pack's credential and, optionally, the operations it must be ``offered``;
* ``exchanges``: recorded requests (method, path relative to
  ``connector.base_url``, optional query and JSON body, optional customer)
  and the provider's answer to each (status, body, headers);
* ``calls``: the operations to call, as which customer, with which input and
  scope grants, and what each should come back as (``{"ok": true}`` by
  default, or ``{"error_code": ...}``).

:func:`recorded_install` starts a loopback fake provider built from the
exchanges alone, and installs a copy of the pack pointed at it through
``install_pack``. Every call then runs through the real connector runtime
and gate: the module registry, the credential resolved by name from
``secrets``, the entitlements probe, the scope grants and the result filter.
The fake identifies the customer by the credential the runtime actually
sent, so a credential that is not the named one is answered 401. Nothing
reaches a real provider.

:func:`run_pack_tests` reports each operation with typed failures
(:data:`TEST_FAILURES`), checks each customer's probe answer against the
declared shape and its effective listing (``effective_module_ids``), and
runs the offline conformance suite (``core.pack.conformance``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterator, List, Mapping, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlsplit

from .connector import METHODS, module_id_for
from .manifest import MANIFEST_FILENAME, PackManifestError, _read_regular_file

__all__ = [
    "FIXTURES_PATH",
    "FIXTURES_SCHEMA",
    "REPORT_SCHEMA",
    "TEST_FAILURES",
    "load_fixtures",
    "recorded_install",
    "render",
    "run_pack_tests",
    "run_pack_tests_async",
]

FIXTURES_SCHEMA = "flyto.pack-fixtures.v1"
FIXTURES_PATH = "fixtures/exchanges.json"
REPORT_SCHEMA = "flyto.pack-test-report.v1"
MAX_FIXTURES_BYTES = 8 * 1024 * 1024
MAX_ITEMS = 2_000
MAX_CUSTOMERS = 64

#: Every typed failure the report can carry, per operation or per customer.
TEST_FAILURES = (
    "UNEXPECTED_RESULT",
    "CALL_RAISED",
    "UNRECORDED_REQUEST",
    "UNKNOWN_CREDENTIAL",
    "SENSITIVE_PATH_UNMATCHED",
    "DATA_PATH_UNMATCHED",
    "RESULT_SCOPE_UNMATCHED",
    "PROBE_SHAPE_INVALID",
    "OPERATION_UNTESTED",
    "EFFECTIVE_OPERATIONS_MISMATCH",
)

#: A runtime failure that means a declaration names nothing in the recorded
#: answer, reported as the declaration's own failure; any other is ``UNEXPECTED_RESULT``.
DECLARATION_FAILURES: Mapping[str, str] = {"RESULT_SCOPE_UNREADABLE": "RESULT_SCOPE_UNMATCHED"}

_ALLOWED_HOSTS_ENV = "FLYTO_ALLOWED_HOSTS"
_ALLOWED_PORTS_ENV = "FLYTO_HTTP_ALLOWED_PORTS"
_LOOPBACK = "127.0.0.1"
_TOKEN_PREFIX = "fixture-access-"

_TOP = (frozenset({"schema", "customers", "exchanges", "calls"}), frozenset())
_CUSTOMER = (frozenset(), frozenset({"credential", "offered"}))
_EXCHANGE = (frozenset({"request", "response"}), frozenset({"customer"}))
_REQUEST = (frozenset({"method", "path"}), frozenset({"query", "body"}))
_RESPONSE = (frozenset(), frozenset({"status", "body", "headers"}))
_CALL = (frozenset({"operation"}), frozenset({"customer", "input", "grants", "expect", "secrets"}))
_EXPECT_KEYS = (frozenset({"ok"}), frozenset({"error_code"}))


def _fail(code: str, message: str) -> None:
    raise PackManifestError(code, message)


# -- the fixtures document ------------------------------------------------------------


def _shape(value: Any, where: str, keys: Tuple[frozenset, frozenset]) -> Dict[str, Any]:
    required, optional = keys
    if type(value) is not dict:
        _fail("FIXTURES_INVALID", f"{where} must be an object")
    unknown = sorted(set(value) - required - optional)
    if unknown:
        _fail("FIXTURES_INVALID", f"{where} has an unknown key: {unknown[0]}")
    missing = sorted(required - set(value))
    if missing:
        _fail("FIXTURES_INVALID", f"{where} is missing {missing[0]}")
    return value


def _bounded_list(value: Any, where: str) -> List[Any]:
    if type(value) is not list or len(value) > MAX_ITEMS:
        _fail("FIXTURES_INVALID", f"{where} must be a list of at most {MAX_ITEMS} entries")
    return value


def _query(value: Any, where: str) -> Dict[str, List[str]]:
    if type(value) is not dict:
        _fail("FIXTURES_INVALID", f"{where} must map names to text values")
    query = {}
    for name, item in value.items():
        values = item if type(item) is list else [item]
        if any(type(v) is not str for v in values):
            _fail("FIXTURES_INVALID", f"{where}.{name} must be text, as it is sent")
        query[name] = list(values)
    return query


def _customer_of(call: Mapping[str, Any], customers: Mapping[str, Any], where: str) -> str:
    name = call.get("customer")
    if name is None and len(customers) == 1:
        return next(iter(customers))
    if name not in customers:
        _fail("FIXTURES_INVALID", f"{where}.customer names no customer of the fixtures")
    return name


def _validate_customers(value: Any, manifest: Mapping[str, Any], op_ids: frozenset) -> Dict[str, Any]:
    if type(value) is not dict or not 1 <= len(value) <= MAX_CUSTOMERS:
        _fail("FIXTURES_INVALID", f"customers must name 1 to {MAX_CUSTOMERS} customers")
    has_auth = bool(manifest["connector"]["auth"])
    if not has_auth and len(value) != 1:
        _fail("FIXTURES_INVALID", "a connector without auth tells customers apart by nothing; name one customer")
    for name, customer in value.items():
        customer = _shape(customer, f"customers.{name}", _CUSTOMER)
        if has_auth and type(customer.get("credential")) not in (str, dict):
            _fail("FIXTURES_INVALID", f"customers.{name}.credential must be a test credential value")
        offered = customer.get("offered")
        if offered is not None and (type(offered) is not list or not set(offered) <= op_ids):
            _fail("FIXTURES_INVALID", f"customers.{name}.offered must list operations of the pack")
    return value


def _validate_exchanges(value: Any, customers: Mapping[str, Any]) -> List[Dict[str, Any]]:
    exchanges = []
    for index, exchange in enumerate(_bounded_list(value, "exchanges")):
        where = f"exchanges[{index}]"
        exchange = _shape(exchange, where, _EXCHANGE)
        if "customer" in exchange and exchange["customer"] not in customers:
            _fail("FIXTURES_INVALID", f"{where}.customer names no customer of the fixtures")
        request = _shape(exchange["request"], f"{where}.request", _REQUEST)
        if request["method"] not in METHODS or type(request["path"]) is not str or not request["path"].startswith("/"):
            _fail("FIXTURES_INVALID", f"{where}.request needs a method and a path relative to connector.base_url")
        response = _shape(exchange["response"], f"{where}.response", _RESPONSE)
        status = response.get("status", 200)
        if type(status) is not int or not 100 <= status <= 599:
            _fail("FIXTURES_INVALID", f"{where}.response.status must be an HTTP status")
        headers = response.get("headers", {})
        if type(headers) is not dict or any(type(k) is not str or type(v) is not str for k, v in headers.items()):
            _fail("FIXTURES_INVALID", f"{where}.response.headers must map names to text")
        exchanges.append({
            "customer": exchange.get("customer"),
            "method": request["method"],
            "path": request["path"],
            "query": _query(request.get("query", {}), f"{where}.request.query"),
            "body": request.get("body", _ANY),
            "status": status,
            "response_body": response.get("body"),
            "headers": dict(headers),
        })
    return exchanges


def _validate_calls(value: Any, customers: Mapping[str, Any], op_ids: frozenset) -> List[Dict[str, Any]]:
    calls = []
    for index, call in enumerate(_bounded_list(value, "calls")):
        where = f"calls[{index}]"
        call = _shape(call, where, _CALL)
        if call["operation"] not in op_ids:
            _fail("FIXTURES_INVALID", f"{where}.operation names no operation of the pack")
        for key in ("input", "grants", "secrets"):
            if key in call and type(call[key]) is not dict:
                _fail("FIXTURES_INVALID", f"{where}.{key} must be an object")
        expect = call.get("expect", {"ok": True})
        if type(expect) is not dict or not (expect == {"ok": True} or (
                set(expect) == {"error_code"} and type(expect["error_code"]) is str and expect["error_code"])):
            _fail("FIXTURES_INVALID", f"{where}.expect is {{\"ok\": true}} or {{\"error_code\": CODE}}")
        calls.append({
            "index": index,
            "operation": call["operation"],
            "customer": _customer_of(call, customers, where),
            "input": dict(call.get("input", {})),
            "grants": call.get("grants"),
            "secrets": call.get("secrets"),
            "expect": expect.get("error_code"),
        })
    return calls


class _Any:
    def __repr__(self) -> str:
        return "<any body>"


#: A recorded request that states no body matches any body.
_ANY = _Any()


@dataclass
class Fixtures:
    customers: Dict[str, Any]
    exchanges: List[Dict[str, Any]]
    calls: List[Dict[str, Any]]


def load_fixtures(pack_dir: os.PathLike[str] | str, manifest: Mapping[str, Any]) -> Fixtures:
    """Read and check ``fixtures/exchanges.json`` against the pack it belongs to."""
    path = Path(pack_dir) / FIXTURES_PATH
    if not path.is_file():
        _fail("FIXTURES_MISSING", f"the pack has no {FIXTURES_PATH}; flyto pack init writes one")
    try:
        document = json.loads(_read_regular_file(path, MAX_FIXTURES_BYTES).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        _fail("FIXTURES_INVALID", f"{FIXTURES_PATH} is not UTF-8 JSON")
    document = _shape(document, "fixtures", _TOP)
    if document["schema"] != FIXTURES_SCHEMA:
        _fail("FIXTURES_INVALID", f"fixtures.schema must be {FIXTURES_SCHEMA}")
    op_ids = frozenset(op["id"] for op in manifest["connector"]["operations"])
    customers = _validate_customers(document["customers"], manifest, op_ids)
    return Fixtures(customers=customers, exchanges=_validate_exchanges(document["exchanges"], customers),
                    calls=_validate_calls(document["calls"], customers, op_ids))


# -- the fake provider ------------------------------------------------------------------


@dataclass
class _Provider:
    """A loopback provider that answers only what the fixtures recorded."""

    fixtures: Fixtures
    base_path: str = ""
    token_path: Optional[str] = None
    #: ``(lowercase header name, value) -> customer``, filled in once the pack is installed.
    identities: Dict[Tuple[str, str], str] = field(default_factory=dict)
    log: List[Dict[str, Any]] = field(default_factory=list)
    base_url: str = ""
    _server: Any = None

    def start(self) -> None:
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                return None

            def do_GET(self) -> None:  # noqa: N802 - the http.server hook names
                provider.handle(self)

            def do_POST(self) -> None:  # noqa: N802
                provider.handle(self)

            def do_PUT(self) -> None:  # noqa: N802
                provider.handle(self)

            def do_PATCH(self) -> None:  # noqa: N802
                provider.handle(self)

            def do_DELETE(self) -> None:  # noqa: N802
                provider.handle(self)

        self._server = ThreadingHTTPServer((_LOOPBACK, 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self.base_url = f"http://{_LOOPBACK}:{self._server.server_address[1]}"

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    def _customer(self, headers: Any) -> Optional[str]:
        if len(self.fixtures.customers) == 1 and not self.identities:
            return next(iter(self.fixtures.customers))
        for (name, value), customer in self.identities.items():
            if headers.get(name) == value:
                return customer
        return None

    def _token(self, handler: Any, body: bytes) -> None:
        form = {k: v[0] for k, v in parse_qs(body.decode("utf-8", "replace")).items()}
        for name, customer in self.fixtures.customers.items():
            credential = customer.get("credential")
            if isinstance(credential, dict) and credential.get("client_id") == form.get("client_id"):
                return _reply(handler, 200, {"access_token": _TOKEN_PREFIX + name, "expires_in": 3600}, {})
        return _reply(handler, 401, {"error": "invalid_client"}, {})

    def handle(self, handler: Any) -> None:
        length = int(handler.headers.get("Content-Length") or 0)
        raw = handler.rfile.read(length) if length else b""
        url = urlsplit(handler.path)
        if self.token_path is not None and handler.command == "POST" and url.path == self.token_path:
            return self._token(handler, raw)
        path = unquote(url.path)
        relative = path[len(self.base_path):] if self.base_path and path.startswith(self.base_path) else path
        query = parse_qs(url.query, keep_blank_values=True)
        body: Any = None
        if raw:
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                body = raw.decode("utf-8", "replace")
        customer = self._customer(handler.headers)
        entry: Dict[str, Any] = {"method": handler.command, "path": relative, "query": query, "customer": customer,
                                 "exchange": None, "status": None, "body": None}
        self.log.append(entry)
        if customer is None:
            entry["status"] = 401
            return _reply(handler, 401, {"error": "the fixtures know no customer with this credential"}, {})
        for index, exchange in enumerate(self.fixtures.exchanges):
            if _matches(exchange, handler.command, relative, query, body, customer):
                headers = {k: v.replace("{base_url}", self.base_url + self.base_path)
                           for k, v in exchange["headers"].items()}
                entry.update(exchange=index, status=exchange["status"], body=exchange["response_body"])
                return _reply(handler, exchange["status"], exchange["response_body"], headers)
        entry["status"] = 404
        return _reply(handler, 404, {"error": "no recorded exchange answers this request"}, {})


def _matches(exchange: Mapping[str, Any], method: str, path: str, query: Mapping[str, List[str]], body: Any,
             customer: str) -> bool:
    if exchange["customer"] not in (None, customer) or exchange["method"] != method or exchange["path"] != path:
        return False
    if any(query.get(name) != values for name, values in exchange["query"].items()):
        return False
    return exchange["body"] is _ANY or exchange["body"] == body


def _reply(handler: Any, status: int, body: Any, headers: Mapping[str, str]) -> None:
    raw = b"" if body is None else json.dumps(body).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    for name, value in headers.items():
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(raw)


@contextlib.contextmanager
def _loopback_allowed(port: int) -> Iterator[None]:
    """Let the SSRF guard reach the fake provider, and only for this run: the operator's own opt-in."""
    saved = {name: os.environ.get(name) for name in (_ALLOWED_HOSTS_ENV, _ALLOWED_PORTS_ENV)}
    for name, value in ((_ALLOWED_HOSTS_ENV, _LOOPBACK), (_ALLOWED_PORTS_ENV, str(port))):
        existing = [item for item in (saved[name] or "").split(",") if item.strip()]
        os.environ[name] = ",".join([*existing, value])
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


# -- the installed pack ---------------------------------------------------------------------


def _pointed_at(raw: Dict[str, Any], provider: _Provider) -> Dict[str, Any]:
    """The pack's own manifest with its provider origin replaced by the fake's, and nothing else."""
    doc = json.loads(json.dumps(raw))
    doc.pop("artifact", None)
    connector = doc["connector"]
    provider.base_path = urlsplit(connector["base_url"]).path.rstrip("/")
    connector["base_url"] = provider.base_url + provider.base_path
    for entry in connector.get("auth", []):
        if isinstance(entry, dict) and isinstance(entry.get("token_url"), str):
            provider.token_path = urlsplit(entry["token_url"]).path or "/"
            entry["token_url"] = provider.base_url + provider.token_path
    return doc


@dataclass
class RecordedSession:
    """One installed pack, answered by its fixtures."""

    manifest: Dict[str, Any]
    fixtures: Fixtures
    provider: _Provider

    @property
    def namespace(self) -> str:
        return self.manifest["pack"]["namespaces"][0]

    def module_id(self, op_id: str) -> str:
        return module_id_for(self.namespace, op_id)

    def secrets(self, customer: str) -> Dict[str, Any]:
        auth = self.manifest["connector"]["auth"]
        if not auth:
            return {}
        return {auth[0]["credential"]: self.fixtures.customers[customer].get("credential")}

    def context(self, customer: str, grants: Optional[Mapping[str, Any]] = None,
                secrets: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """The execution context a host would make: the credential by name and the scope grant."""
        from .connector_gate import ALL_VALUES, ScopeGrants

        if grants is None:
            grants = {entry["key"]: ALL_VALUES for entry in self.manifest.get("scopes", [])}
        return {"secrets": dict(secrets) if secrets is not None else self.secrets(customer),
                "scope_grants": ScopeGrants(grants)}

    def requests(self, path: Optional[str] = None) -> List[Dict[str, Any]]:
        return [entry for entry in self.provider.log if path is None or entry["path"] == path]


async def _identities(session: RecordedSession) -> Dict[Tuple[str, str], str]:
    """Which request header value identifies each customer, as the runtime itself encodes it."""
    from .connector_runtime import _AUTH_KINDS
    from .host import _INSTALLED

    auth = session.manifest["connector"]["auth"]
    if not auth:
        return {}
    entry = auth[0]
    found: Dict[Tuple[str, str], str] = {}
    if entry["kind"] == "oauth2_client_credentials":
        for name in session.fixtures.customers:
            found[("authorization", f"Bearer {_TOKEN_PREFIX}{name}")] = name
        return found
    transport = _INSTALLED[session.manifest["pack"]["id"]].transport
    for name, customer in session.fixtures.customers.items():
        headers = await _AUTH_KINDS[entry["kind"]](transport, entry, customer.get("credential"), 1000)
        for header, value in headers.items():
            found[(header.lower(), value)] = name
    return found


@contextlib.asynccontextmanager
async def recorded_install(pack_dir: os.PathLike[str] | str) -> AsyncIterator[RecordedSession]:
    """Install a copy of the pack pointed at a fake provider built from its fixtures; remove both after."""
    from .host import install_pack, uninstall_pack
    from .manifest import read_pack_manifest
    from .portable import _read_raw_manifest

    root = Path(pack_dir)
    manifest = read_pack_manifest(root)
    if manifest["runtime"]["binding"] != "connector":
        _fail("NOT_A_CONNECTOR_PACK", "flyto pack test runs connector packs; run flyto pack conform for others")
    fixtures = load_fixtures(root, manifest)
    provider = _Provider(fixtures)
    provider.start()
    stage = Path(tempfile.mkdtemp(prefix="flyto-pack-test-"))
    installed = False
    try:
        with _loopback_allowed(provider.port):
            (stage / MANIFEST_FILENAME).write_text(json.dumps(_pointed_at(_read_raw_manifest(root), provider)),
                                                   encoding="utf-8")
            install_pack(stage, require_signature=False)
            installed = True
            session = RecordedSession(manifest=manifest, fixtures=fixtures, provider=provider)
            provider.identities = await _identities(session)
            yield session
    finally:
        try:
            if installed:
                await uninstall_pack(manifest["pack"]["id"])
        finally:
            provider.stop()
            shutil.rmtree(stage, ignore_errors=True)


# -- the run --------------------------------------------------------------------------------


@dataclass
class _Operation:
    op: Mapping[str, Any]
    calls: int = 0
    failures: List[Dict[str, Any]] = field(default_factory=list)
    results: List[Any] = field(default_factory=list)
    pages: List[Any] = field(default_factory=list)


def _request_text(entry: Mapping[str, Any]) -> str:
    return f"{entry['method']} {entry['path']}"


def _concrete_path(op: Mapping[str, Any], params: Mapping[str, Any]) -> str:
    path = op["path"]
    for name, spec in op["inputs"].items():
        if spec["in"] == "path" and params.get(name) is not None:
            path = path.replace("{" + name + "}", str(params[name]))
    return path


async def _call(session: RecordedSession, record: _Operation, customer: str, params: Mapping[str, Any],
                expect: Optional[str], *, grants: Any = None, secrets: Any = None,
                where: str = "") -> Optional[Dict[str, Any]]:
    """One call through the registry; returns the result when it succeeded as expected."""
    from ..modules.registry import ModuleRegistry

    op = record.op
    record.calls += 1
    mark = len(session.provider.log)
    try:
        module = ModuleRegistry.get(session.module_id(op["id"]))(dict(params), session.context(customer, grants, secrets))
        result = await module.run()
    except Exception as error:  # noqa: BLE001 - a call that raises is the finding
        record.failures.append({"code": "CALL_RAISED", "call": where, "detail": type(error).__name__})
        return None
    served = session.provider.log[mark:]
    for entry in served:
        if entry["customer"] is None:
            record.failures.append({"code": "UNKNOWN_CREDENTIAL", "call": where, "request": _request_text(entry)})
        elif entry["exchange"] is None:
            record.failures.append({"code": "UNRECORDED_REQUEST", "call": where, "request": _request_text(entry)})
    ok = isinstance(result, dict) and result.get("ok") is True
    actual = "ok" if ok else (result.get("error_code") if isinstance(result, dict) else "no result")
    if expect is None and ok:
        target = _concrete_path(op, params)
        record.pages += [e["body"] for e in served if e["path"] == target and e["exchange"] is not None
                         and 200 <= e["status"] <= 299]
        record.results.append(result)
        return result
    if expect is not None and actual == expect:
        return None
    code = DECLARATION_FAILURES.get(actual, "UNEXPECTED_RESULT")
    record.failures.append({"code": code, "call": where, "expected": expect or "ok", "actual": actual})
    return None


def _declaration_checks(record: _Operation) -> Dict[str, Any]:
    """Whether what the operation declares about its answers names anything in what was recorded."""
    from .connector_runtime import _dot, parse_sensitive, sensitive_result_paths

    op, checks = record.op, {}
    if not record.results:
        return checks
    if op["sensitive"]:
        checks["sensitive"] = {}
        for path in op["sensitive"]:
            parsed = parse_sensitive([path])
            hit = any(sensitive_result_paths(parsed, result) for result in record.results)
            checks["sensitive"][path] = "matched" if hit else "unmatched"
            if not hit:
                record.failures.append({"code": "SENSITIVE_PATH_UNMATCHED", "path": path,
                                        "detail": "names no value in any recorded answer, so it protects nothing"})
    if op["paginate"] is not None and record.pages:
        data_path = op["paginate"]["data_path"]
        listed = all(isinstance(_dot(page, data_path), list) for page in record.pages)
        checks["data_path"] = "matched" if listed else "unmatched"
        if not listed:
            record.failures.append({"code": "DATA_PATH_UNMATCHED", "path": data_path or "(the body)",
                                    "detail": "names no list in a recorded page"})
    if op["result_scope"] is not None:
        scopes = [((result.get("metadata") or {}).get("precheck") or {}).get("scope") for result in record.results]
        named = any(scope and scope["kept"] + scope["dropped"] for scope in scopes)
        checks["result_scope"] = "matched" if named else "unmatched"
        if not named:
            record.failures.append({"code": "RESULT_SCOPE_UNMATCHED", "path": op["result_scope"]["path"],
                                    "detail": "named no item in any recorded answer, so the filter never ran"})
    return checks


async def _probe(session: RecordedSession, records: Dict[str, _Operation]) -> Dict[str, Any]:
    from .connector_gate import PrecheckError, read_answer

    entitlements = session.manifest.get("entitlements")
    if not entitlements:
        return {}
    record = records[entitlements["probe"]]
    report = {}
    for customer in sorted(session.fixtures.customers):
        result = await _call(session, record, customer, {}, None, where=f"probe as {customer}")
        if result is None:
            report[customer] = {"verdict": "fail", "code": record.failures[-1]["code"]}
            continue
        try:
            answer = read_answer(entitlements, result["data"])
        except PrecheckError as error:
            record.failures.append({"code": "PROBE_SHAPE_INVALID", "call": f"probe as {customer}",
                                    "detail": str(error)})
            report[customer] = {"verdict": "fail", "code": "PROBE_SHAPE_INVALID", "detail": str(error)}
            continue
        report[customer] = {"verdict": "pass", "features": sorted(answer.features), "meters": dict(answer.meters)}
    return report


async def _listings(session: RecordedSession) -> Dict[str, Any]:
    from .host import effective_module_ids

    prefix = session.namespace + "."
    report = {}
    for name, customer in sorted(session.fixtures.customers.items()):
        offered = [m[len(prefix):] for m in await effective_module_ids(session.manifest["pack"]["id"],
                                                                          session.secrets(name))]
        expected = customer.get("offered")
        if expected is None:
            report[name] = {"verdict": "not_declared", "offered": offered}
            continue
        missing = sorted(set(expected) - set(offered))
        unexpected = sorted(set(offered) - set(expected))
        entry = {"verdict": "fail" if missing or unexpected else "pass", "offered": offered}
        if missing or unexpected:
            entry.update(code="EFFECTIVE_OPERATIONS_MISMATCH", missing=missing, unexpected=unexpected)
        report[name] = entry
    return report


async def run_pack_tests_async(pack_dir: os.PathLike[str] | str, *, conformance: bool = True) -> Dict[str, Any]:
    """Run every recorded call, the probe and listing checks, then conformance; returns the report."""
    from .conformance import conform_async

    root = Path(pack_dir)
    async with recorded_install(root) as session:
        records = {op["id"]: _Operation(op) for op in session.manifest["connector"]["operations"]}
        probe = await _probe(session, records)
        customers = await _listings(session)
        for call in session.fixtures.calls:
            await _call(session, records[call["operation"]], call["customer"], call["input"], call["expect"],
                        grants=call["grants"], secrets=call["secrets"], where=f"calls[{call['index']}]")
        manifest = session.manifest
    operations = []
    for op_id, record in sorted(records.items()):
        checks = _declaration_checks(record)
        if record.calls == 0:
            record.failures.append({"code": "OPERATION_UNTESTED", "detail": "no recorded call exercises it"})
        operations.append({
            "operation": op_id,
            "module_id": module_id_for(manifest["pack"]["namespaces"][0], op_id),
            "consequence": record.op["consequence"],
            "calls": record.calls,
            "verdict": "fail" if record.failures else "pass",
            "failures": record.failures,
            "checks": checks,
        })
    conformed = await conform_async(root, run=True) if conformance else None
    passed = (all(item["verdict"] == "pass" for item in operations)
              and all(item["verdict"] == "pass" for item in probe.values())
              and all(item["verdict"] != "fail" for item in customers.values())
              and (conformed is None or conformed["conformant"]))
    return {"schema": REPORT_SCHEMA, "pack": dict(manifest["pack"]), "passed": passed, "operations": operations,
            "probe": probe, "customers": customers, "conformance": conformed}


def run_pack_tests(pack_dir: os.PathLike[str] | str, *, conformance: bool = True) -> Dict[str, Any]:
    """:func:`run_pack_tests_async` from synchronous code (the CLI, a pack's own pytest file)."""
    return asyncio.run(run_pack_tests_async(pack_dir, conformance=conformance))


def _failure_line(failure: Mapping[str, Any]) -> str:
    facts = [f"{key}={failure[key]}" for key in ("call", "request", "path", "expected", "actual") if key in failure]
    detail = f" ({failure['detail']})" if failure.get("detail") else ""
    return f"      {failure['code']}: {', '.join(facts)}{detail}"


def render(report: Mapping[str, Any]) -> str:
    """The report as text, one block per operation."""
    marks = {"pass": "pass", "fail": "FAIL", "not_declared": "n/a "}
    lines = [f"{report['pack']['id']} {report['pack']['version']}", "", "operations:"]
    for item in report["operations"]:
        lines.append(f"  [{marks[item['verdict']]}] {item['operation']:<28} {item['calls']} calls")
        lines += [_failure_line(failure) for failure in item["failures"]]
    if report["probe"]:
        lines += ["", "entitlements probe, per customer:"]
        for name, item in report["probe"].items():
            said = item.get("features", item.get("code"))
            lines.append(f"  [{marks[item['verdict']]}] {name:<28} {said}")
    if report["customers"]:
        lines += ["", "operations offered, per customer:"]
        for name, item in report["customers"].items():
            extra = f" missing={item['missing']} unexpected={item['unexpected']}" if item["verdict"] == "fail" else ""
            lines.append(f"  [{marks[item['verdict']]}] {name:<28} {item['offered']}{extra}")
    if report["conformance"] is not None:
        from .conformance import render as render_conformance

        lines += ["", "conformance:", render_conformance(report["conformance"])]
    lines += ["", "passed" if report["passed"] else "failed: see FAIL above"]
    return "\n".join(lines)
