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
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .connector import CONSEQUENCES
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


def init_pack(target: os.PathLike[str] | str, *, openapi: Optional[os.PathLike[str] | str] = None,
              pack_id: Optional[str] = None, namespace: Optional[str] = None,
              probe: Optional[str] = None) -> Dict[str, Any]:
    """Scaffold a connector pack in ``target``; returns what was written and what is left to decide.

    Everything is checked before the first file is written, so a refusal
    leaves nothing behind.
    """
    root = Path(target)
    _empty_target(root)
    pack_id, namespace = _names(root, pack_id, namespace)
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
    root.mkdir(parents=True, exist_ok=True)
    _write(root / MANIFEST_FILENAME, _dump(manifest))
    _write(root / FIXTURES_PATH, _dump(fixtures))
    _write(root / TEST_FILE, _TEST_SOURCE)
    return {
        "pack_dir": str(root),
        "pack_id": pack_id,
        "namespace": namespace,
        "written": [MANIFEST_FILENAME, FIXTURES_PATH, TEST_FILE],
        "undecided": sorted(op["id"] for op in connector["operations"]),
        "unmapped": unmapped,
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


def decide_consequences(pack_dir: os.PathLike[str] | str, decisions: Mapping[str, str]) -> Dict[str, Any]:
    """Record the author's consequence for each named operation; returns what is still undecided.

    Every decision is checked before the manifest is written: an operation the
    connector does not declare (``CONSEQUENCE_TARGET_UNKNOWN``) or a level
    that is not one of :data:`~core.pack.connector.CONSEQUENCES`
    (``CONSEQUENCE_UNKNOWN``) refuses all of them.
    """
    root = Path(pack_dir)
    document = _raw_manifest(root)
    connector = document.get("connector")
    operations = connector.get("operations") if isinstance(connector, dict) else None
    if not isinstance(operations, list):
        _fail("CONNECTOR_REQUIRED", "only a connector pack declares operations to decide")
    by_id = {op.get("id"): op for op in operations if isinstance(op, dict)}
    for op_id, level in decisions.items():
        if op_id not in by_id:
            _fail("CONSEQUENCE_TARGET_UNKNOWN", f"the connector declares no operation {op_id}")
        if level not in CONSEQUENCES:
            _fail("CONSEQUENCE_UNKNOWN", f"consequence for {op_id} is not one of {', '.join(CONSEQUENCES)}")
    changed = {}
    for op_id, level in decisions.items():
        changed[op_id] = {"from": by_id[op_id].get("consequence"), "to": level}
        by_id[op_id]["consequence"] = level
    (root / MANIFEST_FILENAME).write_text(_dump(document), encoding="utf-8")
    undecided = sorted(op_id for op_id, op in by_id.items() if isinstance(op_id, str) and op.get("consequence") is None)
    return {"decided": changed, "undecided": undecided}
