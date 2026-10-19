# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Draft a ``connector`` section from an OpenAPI 3 document.

:func:`import_openapi` maps what an OpenAPI document states mechanically —
the server, the security schemes, each path and method, its parameters and
JSON body — and returns::

    {"connector": {...}, "unmapped": [{"where": "...", "reason": "..."}, ...]}

What it does not do is decide what a call does to the world. Every imported
operation comes out **without** ``consequence``, so the pack is refused by
validation (``CONSEQUENCE_MISSING``) until a person has decided each one. The
HTTP method is not that decision: a GET can start a scan and a POST can be a
search. ``unmapped`` lists everything else that could not be carried over,
one entry per thing, so nothing is dropped silently.

Credentials are imported as names only (the security scheme's name); an
OpenAPI document never holds the value.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional

__all__ = ["import_openapi"]

_METHODS = ("get", "post", "put", "patch", "delete")
_TYPES = frozenset({"string", "integer", "number", "boolean", "array", "object"})
_DECIDE = "consequence is a decision; set it by hand"


def _fail(code: str, message: str) -> None:
    from .manifest import PackManifestError

    raise PackManifestError(code, message)


class _Draft:
    def __init__(self, document: Mapping[str, Any]):
        self.document = document
        self.unmapped: List[Dict[str, str]] = []

    def skip(self, where: str, reason: str) -> None:
        self.unmapped.append({"where": where, "reason": reason})

    def resolve(self, value: Any, where: str) -> Optional[Mapping[str, Any]]:
        """Follow local ``#/...`` references; anything else is reported."""
        seen = 0
        while isinstance(value, Mapping) and "$ref" in value:
            ref = value["$ref"]
            seen += 1
            if not isinstance(ref, str) or not ref.startswith("#/") or seen > 16:
                self.skip(where, "only local #/ references are followed")
                return None
            target: Any = self.document
            for part in ref[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                target = target.get(part) if isinstance(target, Mapping) else None
            if target is None:
                self.skip(where, f"reference {ref} does not resolve")
                return None
            value = target
        return value if isinstance(value, Mapping) else None


def _credential_name(scheme_name: str) -> str:
    name = re.sub(r"[^a-z0-9_]+", "_", re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", scheme_name).lower()).strip("_")
    if not name or not name[0].isalpha():
        name = f"credential_{name}".rstrip("_")
    return name[:64]


def _http_auth(scheme: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    word = str(scheme.get("scheme") or "").lower()
    named = {"bearer": "Bearer", "basic": "Basic"}.get(word)
    return {"kind": "api_token", "header": "Authorization", "scheme": named} if named else None


def _api_key_auth(scheme: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    if scheme.get("in") != "header" or not isinstance(scheme.get("name"), str):
        return None
    return {"kind": "api_token", "header": scheme["name"]}


def _oauth2_auth(scheme: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    flows = scheme.get("flows") if isinstance(scheme.get("flows"), Mapping) else {}
    client = flows.get("clientCredentials")
    if isinstance(client, Mapping) and client.get("tokenUrl"):
        entry = {"kind": "oauth2_client_credentials", "token_url": client["tokenUrl"]}
        return _with_scopes(entry, client)
    code = flows.get("authorizationCode")
    if isinstance(code, Mapping) and code.get("tokenUrl") and code.get("authorizationUrl"):
        entry = {"kind": "oauth2_authorization_code", "authorize_url": code["authorizationUrl"],
                 "token_url": code["tokenUrl"]}
        return _with_scopes(entry, code)
    return None


def _with_scopes(entry: Dict[str, Any], flow: Mapping[str, Any]) -> Dict[str, Any]:
    scopes = flow.get("scopes")
    if isinstance(scopes, Mapping) and scopes:
        entry["scopes"] = sorted(str(name) for name in scopes)
    return entry


#: OpenAPI security scheme type -> its connector auth entry (None: not mappable).
_AUTH_MAPPERS = {"http": _http_auth, "apiKey": _api_key_auth, "oauth2": _oauth2_auth}


def _auth(draft: _Draft) -> List[Dict[str, Any]]:
    components = draft.document.get("components") if isinstance(draft.document.get("components"), Mapping) else {}
    schemes = components.get("securitySchemes") if isinstance(components.get("securitySchemes"), Mapping) else {}
    auth: List[Dict[str, Any]] = []
    for name, raw in schemes.items():
        where = f"components.securitySchemes.{name}"
        scheme = draft.resolve(raw, where)
        if scheme is None:
            continue
        kind = scheme.get("type")
        mapper = _AUTH_MAPPERS.get(kind)
        entry = mapper(scheme) if mapper else None
        if entry is None:
            detail = f"{kind} in {scheme.get('in')}" if kind == "apiKey" else str(kind)
            draft.skip(where, f"{detail} is not a supported auth kind")
            continue
        if len(auth) == 4:
            draft.skip(where, "a connector declares at most 4 auth entries")
            continue
        entry["credential"] = _credential_name(str(name))
        auth.append({key: value for key, value in entry.items() if value is not None})
    return auth


def _operation_id(method: str, path: str, operation: Mapping[str, Any]) -> str:
    raw = operation.get("operationId")
    if not isinstance(raw, str) or not raw:
        raw = method + "_" + re.sub(r"[{}]", "", path)
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", raw).lower()
    text = re.sub(r"[^a-z0-9_.]+", "_", text).strip("_.")
    text = re.sub(r"_+", "_", text)
    return text if text and text[0].isalpha() else f"op_{text}"


def _input(schema: Optional[Mapping[str, Any]], location: str, required: bool, description: Any) -> Dict:
    kind = schema.get("type") if schema else None
    spec: Dict[str, Any] = {"type": kind if kind in _TYPES else "string", "in": location}
    if required:
        spec["required"] = True
    if isinstance(description, str) and description:
        spec["description"] = description
    if schema and isinstance(schema.get("enum"), list):
        spec["enum"] = list(schema["enum"])
    return spec


def _parameters(draft: _Draft, items: Any, where: str, inputs: Dict[str, Dict[str, Any]]) -> None:
    for raw in items if isinstance(items, list) else []:
        parameter = draft.resolve(raw, f"{where}.parameters")
        if parameter is None:
            continue
        name, location = parameter.get("name"), parameter.get("in")
        if location not in ("path", "query"):
            draft.skip(f"{where}.parameters.{name}", f"{location} parameters are not mapped")
            continue
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
            draft.skip(f"{where}.parameters.{name}", "the parameter name is not an input name")
            continue
        schema = draft.resolve(parameter.get("schema"), f"{where}.parameters.{name}.schema")
        inputs[name] = _input(schema, location, location == "path" or parameter.get("required") is True,
                              parameter.get("description"))


def _body(draft: _Draft, operation: Mapping[str, Any], where: str, inputs: Dict[str, Dict[str, Any]]) -> None:
    if "requestBody" not in operation:
        return
    body = draft.resolve(operation["requestBody"], f"{where}.requestBody")
    content = body.get("content") if body else None
    media = content.get("application/json") if isinstance(content, Mapping) else None
    schema = draft.resolve(media.get("schema"), f"{where}.requestBody") if isinstance(media, Mapping) else None
    properties = schema.get("properties") if schema and schema.get("type", "object") == "object" else None
    if not isinstance(properties, Mapping):
        draft.skip(f"{where}.requestBody", "only an application/json object body is mapped")
        return
    required = set(schema.get("required") or ())
    for name, raw in properties.items():
        prop = draft.resolve(raw, f"{where}.requestBody.{name}")
        if name in inputs:
            draft.skip(f"{where}.requestBody.{name}", "the body property shares a name with a parameter")
            continue
        inputs[name] = _input(prop, "body", name in required, (prop or {}).get("description"))


def _operations(draft: _Draft) -> List[Dict[str, Any]]:
    paths = draft.document.get("paths")
    operations: List[Dict[str, Any]] = []
    seen: set = set()
    for path, item in (paths.items() if isinstance(paths, Mapping) else ()):
        item = draft.resolve(item, f"paths.{path}")
        if item is None:
            continue
        for method in _METHODS:
            if not isinstance(item.get(method), Mapping):
                continue
            operation = item[method]
            where = f"paths.{path}.{method}"
            op_id = _operation_id(method, path, operation)
            if op_id in seen:
                draft.skip(where, f"operation id {op_id} repeats; rename it")
                continue
            seen.add(op_id)
            inputs: Dict[str, Dict[str, Any]] = {}
            _parameters(draft, item.get("parameters"), where, inputs)
            _parameters(draft, operation.get("parameters"), where, inputs)
            _body(draft, operation, where, inputs)
            drafted: Dict[str, Any] = {"id": op_id, "method": method.upper(), "path": path, "inputs": inputs}
            summary = operation.get("summary") or operation.get("description")
            if isinstance(summary, str) and summary.strip():
                drafted["description"] = summary.strip()[:500]
            operations.append(drafted)
            draft.skip(f"connector.operations.{op_id}.consequence", _DECIDE)
        for name in item:
            if name not in _METHODS and name not in ("parameters", "summary", "description", "servers"):
                draft.skip(f"paths.{path}.{name}", "not an imported method")
    return operations


def _base_url(draft: _Draft) -> str:
    servers = draft.document.get("servers")
    first = servers[0] if isinstance(servers, list) and servers and isinstance(servers[0], Mapping) else {}
    url = first.get("url")
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        draft.skip("servers", "no absolute server URL; set connector.base_url by hand")
        return ""
    if "{" in url:
        draft.skip("servers[0].url", "server variables are not expanded; check connector.base_url")
    if isinstance(servers, list) and len(servers) > 1:
        draft.skip("servers", "only the first server is imported")
    return url.rstrip("/")


def import_openapi(document: Any) -> Dict[str, Any]:
    """A draft ``connector`` section and what could not be mapped. Never sets a consequence."""
    if not isinstance(document, Mapping) or not str(document.get("openapi", "")).startswith("3."):
        _fail("UNSUPPORTED_OPENAPI", "the document is not OpenAPI 3")
    draft = _Draft(document)
    connector: Dict[str, Any] = {"base_url": _base_url(draft), "auth": _auth(draft)}
    connector["operations"] = _operations(draft)
    if not connector["operations"]:
        draft.skip("paths", "no operation could be imported")
    return {"connector": connector, "unmapped": draft.unmapped}

