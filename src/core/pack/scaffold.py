# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""``flyto pack init`` and ``flyto pack consequence``: a provider scaffolds its own connector pack.

:func:`init_pack` writes a whole pack in one step, from a blank template or
from an OpenAPI 3 document (through the existing draft import,
``core.pack.openapi``):

* ``flyto-pack.json`` with the ``connector``, ``entitlements``, ``scopes``
  and ``standalone`` sections;
* ``fixtures/exchanges.json``, the recorded exchanges ``flyto pack test``
  builds its fake provider from (``core.pack.recorded``);
* ``tests/test_pack.py``, which runs that test under pytest.

It never writes a consequence. Every operation starts without one, and the
pack is refused (``CONSEQUENCE_MISSING``, naming every undecided operation)
until the author has decided each with :func:`decide_consequences`. Nothing
here reads the HTTP method as that decision: a GET can start a scan and a
POST can be a search.

The scaffold depends on flyto-core alone. It imports nothing from a Flyto2
host product, and neither does the pack it writes.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .connector import CONSEQUENCE_CONTRACTS, CONSEQUENCES
from .manifest import MANIFEST_FILENAME, PACK_SCHEMA, PackManifestError, _read_regular_file
from .recorded import FIXTURES_PATH, FIXTURES_SCHEMA

__all__ = [
    "SCAFFOLD_REFUSALS",
    "TEST_FILE",
    "decide_consequences",
    "init_pack",
    "parse_decisions",
]

#: The refusals only the scaffold commands raise (the rest are the validator's own).
SCAFFOLD_REFUSALS = ("INIT_TARGET_NOT_EMPTY", "CONSEQUENCE_TARGET_UNKNOWN", "CONSEQUENCE_DECISION_INVALID")
TEST_FILE = "tests/test_pack.py"

_PACK_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_NAMESPACE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_CREDENTIAL = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FIXTURE_CUSTOMER = "example_customer"
_FIXTURE_TOKEN = "fixture-token-not-real"

#: The ``standalone`` section every scaffold starts with: both transports, the
#: Python runtime, and the hashed lockfile the build places beside the manifest.
STANDALONE_TEMPLATE: Mapping[str, Any] = {
    "transports": ["stdio", "streamable_http"],
    "runtime": {"language": "python", "version": ">=3.10"},
    "lockfile": "requirements.lock",
}

#: A recorded input value per JSON-schema type, for the calls an OpenAPI scaffold writes.
_PLACEHOLDERS: Mapping[str, Any] = {
    "string": "example", "integer": 1, "number": 1, "boolean": True, "array": [], "object": {},
}

#: What a fixture customer holds for each auth kind: a test value, never a real one.
_FIXTURE_CREDENTIALS: Mapping[str, Any] = {
    "api_token": _FIXTURE_TOKEN,
    "oauth2_authorization_code": {"access_token": _FIXTURE_TOKEN},
    "oauth2_client_credentials": {"client_id": "fixture-client", "client_secret": _FIXTURE_TOKEN},
}

_TEST_SOURCE = '''"""Run this pack's operations against its recorded fixtures: ``flyto pack test`` under pytest."""

from pathlib import Path

from core.pack.recorded import render, run_pack_tests

PACK = Path(__file__).resolve().parents[1]


def test_the_pack_passes_its_recorded_fixtures():
    report = run_pack_tests(PACK)
    assert report["passed"], render(report)
'''

_DEVICE_TEST_SOURCE = '''"""Run the offline conformance suite against this pack's runner: ``flyto pack conform`` under pytest."""

from pathlib import Path

from core.pack.conformance import conform, render

PACK = Path(__file__).resolve().parents[1]


def test_the_pack_conforms():
    report = conform(PACK)
    assert report["conformant"], render(report)
'''

DEVICE_RUNNER = "runner/main.py"
#: The device adapter's runner: standard library only, one simulated device.
#: ``__NAMESPACE__`` is replaced by the pack's namespace.
_DEVICE_RUNNER_SOURCE = r'''"""Device adapter runner: one simulated device with a bounded setpoint, served over JSON-RPC on stdio.

Standard library only. Replace ``SimulatedDevice`` with your device's own
driver (serial, fieldbus, a vendor SDK); keep the rest. A host relies on:

* every call answered, as ``{"ok": true, "data": ...}`` or
  ``{"ok": false, "error": {"code", "message"}}``;
* a value outside the bounds published in ``flyto-pack.json`` refused, never
  clamped;
* the stop answering always, as its own capability;
* ``move_to`` reporting the measured position it ended at, so the host judges
  the contract's evidence itself.

Check it offline: ``flyto pack conform PACK_DIR``.
"""

import json
import sys

PACK_VERSION = "0.1.0"
NAMESPACE = "__NAMESPACE__"
# The bounds published in flyto-pack.json (params_schema.target.min/max).
BOUNDS = (0.0, 100.0)


class RefusedError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class SimulatedDevice:
    """A simulated device. A real adapter talks to the device here."""

    def __init__(self):
        self.position = 0.0
        self.stopped = False

    def move_to(self, target):
        low, high = BOUNDS
        if not low <= target <= high:
            raise RefusedError("OUT_OF_BOUNDS", f"target {target} is outside {low}..{high}")
        self.stopped = False
        self.position = float(target)
        return self.position

    def stop(self):
        self.stopped = True


DEVICE = SimulatedDevice()


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RefusedError("INVALID_ARGUMENT", "target must be a number")
    return float(value)


def move_to(params):
    return {"device_state": {"position": DEVICE.move_to(_number(params.get("target")))}}


def read_state(_params):
    return {"device_state": {"position": DEVICE.position}, "stopped": DEVICE.stopped}


def stop(_params):
    DEVICE.stop()
    return {"stopped": True}


# module_id -> handler: the one place a call is routed.
HANDLERS = {
    NAMESPACE + ".move_to": move_to,
    NAMESPACE + ".read_state": read_state,
    NAMESPACE + ".stop": stop,
}


def _invoke(params):
    handler = HANDLERS.get(params.get("step"))
    if handler is None:
        return {"ok": False, "error": {"code": "UNKNOWN_MODULE", "message": "this pack does not serve that module"}}
    try:
        return {"ok": True, "data": handler(params.get("input") or {})}
    except RefusedError as refused:
        return {"ok": False, "error": {"code": refused.code, "message": str(refused)}}


METHODS = {
    "handshake": lambda params: {"pluginVersion": PACK_VERSION, "protocolVersion": params.get("protocolVersion")},
    "ping": lambda _params: {},
    "invoke": _invoke,
}


def _reply(message_id, result=None, error=None):
    message = {"jsonrpc": "2.0", "id": message_id}
    message.update({"error": error} if error else {"result": result})
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def serve():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except ValueError:
            continue
        method, message_id = request.get("method"), request.get("id")
        if method == "shutdown":
            _reply(message_id, {})
            return
        handler = METHODS.get(method)
        if handler is None:
            _reply(message_id, error={"code": -32601, "message": f"unknown method {method}"})
            continue
        _reply(message_id, handler(request.get("params") or {}))


if __name__ == "__main__":
    serve()
'''


def _device_modules(namespace: str) -> List[Dict[str, Any]]:
    """The device template's rows: capability contracts with every fact but the consequence (``safety_class``)."""
    return [
        {"module_id": f"{namespace}.move_to", "label": "Move to a setpoint",
         "description": "Moves the simulated device to a setpoint, refusing any target outside its bounds.",
         "provides_capability": f"{namespace}.move_to",
         "params_schema": {"target": {"type": "number", "required": True, "min": 0, "max": 100}},
         "timeout_ms": 30000,
         "contract": {"actuates": True, "requires_safe_stop": True, "cancellable": True, "idempotent": False,
                      "effects": ["position.changed"], "expected_duration_ms": 20000,
                      "evidence": [{"kind": "setpoint_reached", "observe": "device_state",
                                    "phases": ["after", "settled"],
                                    "measure": {"op": "distance_to", "fields": ["position"]},
                                    "expect": {"arguments": {"position": "target"}},
                                    "tolerance": {"absolute": 0.5}}]}},
        {"module_id": f"{namespace}.read_state", "label": "Read the device state",
         "description": "Reports the simulated device's position. Moves nothing.",
         "provides_capability": f"{namespace}.read_state",
         "contract": {"actuates": False, "requires_safe_stop": False, "cancellable": True, "idempotent": True}},
        {"module_id": f"{namespace}.stop", "label": "Stop the device",
         "description": "Stops the simulated device where it is.",
         "provides_capability": f"{namespace}.stop",
         "contract": {"actuates": True, "requires_safe_stop": False, "cancellable": False, "idempotent": True,
                      "role": "safe_stop", "effects": ["safe_stop"]}},
    ]


def _fail(code: str, message: str) -> None:
    raise PackManifestError(code, message)


def _host_version() -> str:
    from .host import _host_version as read

    return read()


def _names(target: Path, pack_id: Optional[str], namespace: Optional[str]) -> tuple:
    """The pack id and namespace: as given, or derived from the directory name."""
    if pack_id is None:
        pack_id = "com.example." + re.sub(r"[^a-z0-9]+", "-", target.name.lower()).strip("-")
    if len(pack_id) > 128 or not _PACK_ID.fullmatch(pack_id):
        _fail("INVALID_PACK_ID", "pack id must be a lowercase identifier such as com.example.items")
    if namespace is None:
        namespace = re.sub(r"[^a-z0-9_]+", "_", pack_id.rsplit(".", 1)[-1]).strip("_")
    from ..plugin.manifest import DENIED_NAMESPACES

    if not _NAMESPACE.fullmatch(namespace) or namespace in DENIED_NAMESPACES:
        _fail("INVALID_NAMESPACE", "namespace must be a lowercase identifier no flyto-core namespace uses")
    return pack_id, namespace


def _blank_connector(credential: str) -> Dict[str, Any]:
    return {
        "base_url": "https://api.provider.example",
        "auth": [{"kind": "api_token", "header": "Authorization", "scheme": "Bearer", "credential": credential}],
        "rate_limit": {"requests": 60, "per_seconds": 60},
        "operations": [
            {"id": "account.entitlements", "label": "Account entitlements",
             "description": "Read which products the account holds.",
             "method": "GET", "path": "/v1/account/entitlements", "inputs": {}},
            {"id": "item.get", "label": "Get an item", "description": "Read one item.",
             "method": "GET", "path": "/v1/items/{item}",
             "inputs": {"item": {"type": "string", "description": "Item identifier", "scope": "item"}},
             "result_scope": "$.id", "sensitive": ["$.owner"], "requires": {"features": ["items"]}},
        ],
    }


def _blank_fixtures() -> Dict[str, Any]:
    return {
        "schema": FIXTURES_SCHEMA,
        "customers": {_FIXTURE_CUSTOMER: {"credential": _FIXTURE_TOKEN,
                                          "offered": ["account.entitlements", "item.get"]}},
        "exchanges": [
            {"customer": _FIXTURE_CUSTOMER, "request": {"method": "GET", "path": "/v1/account/entitlements"},
             "response": {"status": 200, "body": {"features": ["items"]}}},
            {"customer": _FIXTURE_CUSTOMER, "request": {"method": "GET", "path": "/v1/items/item-1"},
             "response": {"status": 200, "body": {"id": "item-1", "name": "Example item",
                                                  "owner": "Example Owner"}}},
        ],
        "calls": [
            {"operation": "item.get", "customer": _FIXTURE_CUSTOMER, "input": {"item": "item-1"}},
            {"operation": "item.get", "customer": _FIXTURE_CUSTOMER, "input": {"item": "item-1"},
             "grants": {"item": ["item-2"]}, "expect": {"error_code": "OUT_OF_SCOPE"}},
        ],
    }


def _openapi_fixtures(connector: Mapping[str, Any]) -> Dict[str, Any]:
    """One call per operation, with recorded-shape inputs; no response is invented."""
    customer: Dict[str, Any] = {}
    if connector["auth"]:
        customer["credential"] = _FIXTURE_CREDENTIALS[connector["auth"][0]["kind"]]
    calls = []
    for op in connector["operations"]:
        inputs = {
            name: (spec["enum"][0] if spec.get("enum") else _PLACEHOLDERS[spec["type"]])
            for name, spec in op["inputs"].items() if spec.get("required") or spec.get("in") == "path"
        }
        calls.append({"operation": op["id"], "customer": _FIXTURE_CUSTOMER, "input": inputs})
    return {"schema": FIXTURES_SCHEMA, "customers": {_FIXTURE_CUSTOMER: customer}, "exchanges": [], "calls": calls}


def _read_openapi(path: os.PathLike[str] | str) -> Dict[str, Any]:
    import yaml

    from .openapi import import_openapi

    try:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        _fail("UNSUPPORTED_OPENAPI", "the OpenAPI document could not be read as JSON or YAML")
    return import_openapi(document)


def _empty_target(target: Path) -> None:
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        _fail("INIT_TARGET_NOT_EMPTY", "pack init writes a new pack into an empty or new directory")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _dump(document: Any) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def _connector_files(pack_id: str, namespace: str, *, openapi: Any, probe: Optional[str]) -> Dict[str, Any]:
    """The connector template: manifest, recorded fixtures and the pytest file."""
    unmapped: List[Dict[str, str]] = []
    if openapi is not None:
        draft = _read_openapi(openapi)
        connector, unmapped = draft["connector"], draft["unmapped"]
        entitlements = {"probe": probe or "", "features": {"keys": [], "path": "$.features[*]"}}
        scopes: List[Dict[str, Any]] = []
        fixtures = _openapi_fixtures(connector)
    else:
        credential = f"{namespace}_api_token"
        connector = _blank_connector(credential if _CREDENTIAL.fullmatch(credential) else "provider_api_token")
        entitlements = {"probe": probe or "account.entitlements",
                        "features": {"keys": ["items"], "path": "$.features[*]"}}
        scopes = [{"key": "item"}]
        fixtures = _blank_fixtures()
    manifest = {
        "schema": PACK_SCHEMA,
        "pack": {"id": pack_id, "version": "0.1.0", "namespaces": [namespace], "title": f"{namespace} connector",
                 "description": f"The {namespace} provider API as a connector pack.", "min_host": _host_version()},
        "runtime": {"binding": "connector", "request_timeout_ms": 20000},
        "standalone": json.loads(json.dumps(STANDALONE_TEMPLATE)),
        "connector": connector,
        "entitlements": entitlements,
        "scopes": scopes,
    }
    return {"files": {MANIFEST_FILENAME: _dump(manifest), FIXTURES_PATH: _dump(fixtures), TEST_FILE: _TEST_SOURCE},
            "undecided": sorted(op["id"] for op in connector["operations"]), "unmapped": unmapped}


def _device_files(pack_id: str, namespace: str, *, openapi: Any, probe: Optional[str]) -> Dict[str, Any]:
    """The device-adapter template: a module pack, its simulated-device runner and the pytest file."""
    if openapi is not None or probe is not None:
        _fail("INIT_TEMPLATE_CONFLICT", "--openapi and --probe describe an HTTP API; a device adapter has none")
    modules = _device_modules(namespace)
    manifest = {
        "schema": PACK_SCHEMA,
        "pack": {"id": pack_id, "version": "0.1.0", "namespaces": [namespace],
                 "title": f"{namespace} device adapter",
                 "description": f"A {namespace} device adapter, scaffolded against a simulated device.",
                 "min_host": _host_version()},
        "runtime": {"binding": "subprocess-jsonrpc", "language": "python", "entry": DEVICE_RUNNER,
                    "request_timeout_ms": 30000},
        "modules": modules,
    }
    return {"files": {MANIFEST_FILENAME: _dump(manifest),
                      DEVICE_RUNNER: _DEVICE_RUNNER_SOURCE.replace("__NAMESPACE__", namespace),
                      TEST_FILE: _DEVICE_TEST_SOURCE},
            "undecided": sorted(row["module_id"] for row in modules), "unmapped": []}


#: ``--template`` -> what it writes. Each returns ``{files, undecided, unmapped}`` and writes nothing itself.
TEMPLATES: Mapping[str, Any] = {
    "connector": _connector_files,
    "device-adapter": _device_files,
}


def init_pack(target: os.PathLike[str] | str, *, openapi: Optional[os.PathLike[str] | str] = None,
              pack_id: Optional[str] = None, namespace: Optional[str] = None,
              probe: Optional[str] = None, template: str = "connector") -> Dict[str, Any]:
    """Scaffold a pack from ``template`` in ``target``; returns what was written and what is left to decide.

    Everything is checked before the first file is written, so a refusal
    leaves nothing behind.
    """
    if template not in TEMPLATES:
        _fail("INIT_TEMPLATE_UNKNOWN", f"template is one of {', '.join(TEMPLATES)}")
    root = Path(target)
    _empty_target(root)
    pack_id, namespace = _names(root, pack_id, namespace)
    scaffold = TEMPLATES[template](pack_id, namespace, openapi=openapi, probe=probe)
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in scaffold["files"].items():
        _write(root.joinpath(*rel.split("/")), text)
    return {
        "pack_dir": str(root),
        "pack_id": pack_id,
        "namespace": namespace,
        "template": template,
        "written": list(scaffold["files"]),
        "undecided": scaffold["undecided"],
        "unmapped": scaffold["unmapped"],
    }


# -- deciding consequences ----------------------------------------------------------


def parse_decisions(pairs: Sequence[str]) -> Dict[str, str]:
    """``["op=level", ...]`` -> ``{op: level}``; a pair without ``=`` is refused."""
    decisions: Dict[str, str] = {}
    for pair in pairs:
        op_id, sep, level = pair.partition("=")
        if not sep or not op_id or not level:
            _fail("CONSEQUENCE_DECISION_INVALID", "a decision is OPERATION=LEVEL, such as item.get=observe")
        decisions[op_id] = level
    if not decisions:
        _fail("CONSEQUENCE_DECISION_INVALID", "name at least one OPERATION=LEVEL")
    return decisions


def _raw_manifest(root: Path) -> Dict[str, Any]:
    from .manifest import MAX_MANIFEST_BYTES

    raw = _read_regular_file(root / MANIFEST_FILENAME, MAX_MANIFEST_BYTES)
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        _fail("INVALID_JSON", "flyto-pack.json is not valid UTF-8 JSON")
    if type(document) is not dict:
        _fail("INVALID_JSON", "flyto-pack.json is not a JSON object")
    return document


def _decision_targets(document: Mapping[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Any]:
    """``({id: the object a decision edits}, how a level is written into it)`` for a connector or module pack."""
    connector = document.get("connector")
    operations = connector.get("operations") if isinstance(connector, dict) else None
    if isinstance(operations, list):
        return ({op.get("id"): op for op in operations if isinstance(op, dict)},
                lambda op, level: op.__setitem__("consequence", level))
    modules = document.get("modules")
    if isinstance(modules, list):
        rows = {row.get("module_id"): row for row in modules
                if isinstance(row, dict) and isinstance(row.get("contract"), dict)}
        return rows, _decide_module
    _fail("CONNECTOR_REQUIRED", "only a connector pack or a module pack with contracts has consequences to decide")


def _decide_module(row: Dict[str, Any], level: str) -> None:
    """A module's consequence is its contract's ``safety_class``, with the level's effect class added."""
    stated = CONSEQUENCE_CONTRACTS[level]
    contract = row["contract"]
    contract["safety_class"] = stated["safety_class"]
    effects = list(contract.get("effects") or [])
    contract["effects"] = effects + [effect for effect in stated["effects"] if effect not in effects]


def _decided(target: Mapping[str, Any]) -> Optional[str]:
    """What is decided for one target now: an operation's consequence, a module's safety class."""
    return target.get("consequence") if "module_id" not in target else target["contract"].get("safety_class")


def decide_consequences(pack_dir: os.PathLike[str] | str, decisions: Mapping[str, str]) -> Dict[str, Any]:
    """Record the author's consequence for each named operation or module; returns what is still undecided.

    Every decision is checked before the manifest is written: an operation or
    module the pack does not declare (``CONSEQUENCE_TARGET_UNKNOWN``) or a
    level that is not one of :data:`~core.pack.connector.CONSEQUENCES`
    (``CONSEQUENCE_UNKNOWN``) refuses all of them. A module's level is
    written as its contract's ``safety_class`` and effect class
    (:data:`~core.pack.connector.CONSEQUENCE_CONTRACTS`), the same statement
    a connector operation's level becomes.
    """
    root = Path(pack_dir)
    document = _raw_manifest(root)
    targets, write = _decision_targets(document)
    for target_id, level in decisions.items():
        if target_id not in targets:
            _fail("CONSEQUENCE_TARGET_UNKNOWN", f"the pack declares no operation or module {target_id}")
        if level not in CONSEQUENCES:
            _fail("CONSEQUENCE_UNKNOWN", f"consequence for {target_id} is not one of {', '.join(CONSEQUENCES)}")
    changed = {}
    for target_id, level in decisions.items():
        target = targets[target_id]
        changed[target_id] = {"from": _decided(target), "to": level}
        write(target, level)
    (root / MANIFEST_FILENAME).write_text(_dump(document), encoding="utf-8")
    undecided = sorted(t for t, target in targets.items() if isinstance(t, str) and _decided(target) is None)
    return {"decided": changed, "undecided": undecided}
