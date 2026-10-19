# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The ``connector`` section of ``flyto.pack.v1``: a provider's HTTP API, declared as data.

A provider pack with ``runtime.binding: connector`` ships no code. It declares
where the API is, how a call authenticates, how fast it may be called, and
each operation::

    "connector": {
      "base_url": "https://api.provider.example",
      "auth": [{"kind": "api_token", "header": "Authorization", "scheme": "Basic",
                "credential": "provider_api_token"}],
      "rate_limit": {"requests": 100, "per_seconds": 60},
      "operations": [{
        "id": "rating.get", "method": "GET", "path": "/v1/companies/{company}",
        "consequence": "observe",
        "inputs": {"company": {"type": "string", "scope": "company"}},
        "result_scope": "$.guid", "sensitive": ["$.findings[*].assets"],
        "requires": {"features": ["ratings"]}, "consumes": {"meter": "lookups", "amount": 1},
        "paginate": {"strategy": "offset", "data_path": "results"}
      }]
    }

:func:`validate_connector` normalizes the section or refuses it with a typed
:class:`PackManifestError` naming the operation. :func:`operation_rows` turns
each operation into the module row ``@register_module`` consumes, with id
``<namespace>.<operation id>`` (a connector pack has exactly one namespace,
which stands for the pack in its module ids). The one generic runtime that
executes those rows is ``core.pack.connector_runtime``.

A credential is referred to **by name** and never carried by value. The host
supplies the value at call time through the execution context's ``secrets``
layer, the same name-keyed layer core already hands modules.

``requires``, ``consumes``, ``result_scope`` and each input's ``scope`` are
validated here and bound to the pack's ``entitlements`` and ``scopes``
sections (:func:`validate_provider_sections`). ``core.pack.connector_gate``
enforces them at every call.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlsplit

from .jsonpath import JsonPathError, parse

__all__ = [
    "AUTH_KINDS",
    "CONSEQUENCES",
    "CONSEQUENCE_CONTRACTS",
    "PAGINATION_STRATEGIES",
    "validate_connector",
    "operation_rows",
    "path_parameters",
    "validate_provider_sections",
]

#: The consequence levels, mildest first: the platform's level vocabulary
#: (observe, reversible, external write, real-world effect, irreversible).
CONSEQUENCES = ("observe", "reversible", "external_write", "real_world", "irreversible")

#: How each level is stated in the module's ``flyto.capability-contract.v1``
#: contract, so a host grades a connector operation from its contract alone,
#: with no code that knows it came from a connector: the safety class, and the
#: effect class that names the level's rung.
CONSEQUENCE_CONTRACTS: Mapping[str, Mapping[str, Any]] = {
    "observe": {"safety_class": "read_only", "effects": ("read",), "idempotent": True},
    "reversible": {"safety_class": "read_only", "effects": ("reversible_change",), "idempotent": False},
    "external_write": {"safety_class": "controlled", "effects": ("external_write",), "idempotent": False},
    "real_world": {"safety_class": "movement", "effects": ("physical_actuation",), "idempotent": False},
    "irreversible": {"safety_class": "dangerous", "effects": ("irreversible",), "idempotent": False},
}

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
#: Where an input goes when it does not say: a read sends its inputs in the
#: query, a write in the JSON body.
DEFAULT_INPUT_LOCATION = {"GET": "query", "DELETE": "query", "POST": "body", "PUT": "body", "PATCH": "body"}
INPUT_LOCATIONS = ("path", "query", "body")
#: The methods that send a JSON body.
BODY_METHODS = ("POST", "PUT", "PATCH")
INPUT_TYPES = ("string", "integer", "number", "boolean", "array", "object")

#: The keys each auth kind declares. Every one of them names something; none
#: holds a secret. ``credential`` is the name the host resolves.
AUTH_KINDS: Mapping[str, Tuple[frozenset, frozenset]] = {
    "api_token": (frozenset({"kind", "header", "credential"}), frozenset({"scheme"})),
    "oauth2_client_credentials": (frozenset({"kind", "token_url", "credential"}), frozenset({"scopes"})),
    "oauth2_authorization_code": (
        frozenset({"kind", "authorize_url", "token_url", "credential"}),
        frozenset({"scopes"}),
    ),
}
_AUTH_URL_KEYS = ("token_url", "authorize_url")

#: The pagination shapes ``http.paginate`` accepts, with the keys each reads.
PAGINATION_STRATEGIES: Mapping[str, frozenset] = {
    "offset": frozenset({"offset_param", "limit_param", "page_size"}),
    "page": frozenset({"page_param", "limit_param", "page_size", "start_page"}),
    "cursor": frozenset({"cursor_param", "cursor_path", "page_size"}),
    "link_header": frozenset({"page_size"}),
}
_PAGINATE_SHARED = frozenset({"strategy", "data_path", "max_pages"})
PAGINATE_DEFAULTS: Mapping[str, Any] = {
    "data_path": "",
    "max_pages": 50,
    "offset_param": "offset",
    "limit_param": "limit",
    "page_param": "page",
    "start_page": 1,
    "cursor_param": "cursor",
    "cursor_path": "",
    "page_size": 100,
}

MAX_OPERATIONS = 256
MAX_AUTH = 4
MAX_PATHS = 32

_CONNECTOR_REQUIRED = frozenset({"base_url", "operations"})
_CONNECTOR_OPTIONAL = frozenset({"auth", "rate_limit"})
_OPERATION_REQUIRED = frozenset({"id", "method", "path"})
_OPERATION_OPTIONAL = frozenset({
    "consequence", "inputs", "result_scope", "sensitive", "requires", "consumes", "paginate",
    "label", "description", "timeout_ms",
})
_INPUT_KEYS = frozenset({
    "type", "in", "required", "description", "label", "default", "enum", "min", "max",
    "minLength", "maxLength", "pattern", "items", "format", "secret", "scope",
})

_OPERATION_ID = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)*$")
_CREDENTIAL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_PATH_PARAM = re.compile(r"\{([^{}]*)\}")
_INPUT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_HEADER_NAME = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,31}$")
_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_PATH_TEXT = re.compile(r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/{}-]*$")
_LOOPBACK_NAMES = frozenset({"localhost"})

#: Words a key would use to hold a credential's value. A declaration that has
#: one beside the keys an auth kind declares is carrying a secret inline.
_SECRET_WORDS = re.compile(
    r"(?i)(secret|password|passwd|token|api[_-]?key|apikey|bearer|private[_-]?key|access[_-]?key|value)"
)


def _fail(code: str, message: str, operation: Optional[str] = None) -> None:
    from .manifest import PackManifestError

    raise PackManifestError(code, message, operation=operation)


def _object(value: Any, where: str, required: frozenset, optional: frozenset, operation: Optional[str]) -> Dict:
    if type(value) is not dict:
        _fail("INVALID_CONNECTOR", f"{where} must be an object", operation)
    unknown = set(value) - required - optional
    if unknown:
        _fail("UNKNOWN_KEY", f"{where} contains an unknown key: {sorted(unknown)[0]}", operation)
    missing = sorted(required - set(value))
    if missing:
        _fail("MISSING_FIELD", f"{where} is missing required field: {missing[0]}", operation)
    return value


def _looks_like_secret(text: str) -> bool:
    """A value-level credential: the same patterns the trace redactor masks."""
    from ..engine.redaction import redact_text

    return redact_text(text) != text


def _url(value: Any, where: str, operation: Optional[str] = None) -> str:
    """``https`` anywhere, or ``http`` to a literal loopback host for local development."""
    if type(value) is not str or len(value) > 2048:
        _fail("INVALID_BASE_URL", f"{where} must be a URL", operation)
    parts = urlsplit(value)
    if parts.username is not None or parts.password is not None or _looks_like_secret(value):
        _fail("INLINE_SECRET", f"{where} carries a credential; name it in auth instead", operation)
    host = parts.hostname or ""
    if parts.query or parts.fragment or not host:
        _fail("INVALID_BASE_URL", f"{where} must be scheme://host[:port][/path]", operation)
    if parts.scheme == "https":
        return value.rstrip("/")
    if parts.scheme == "http" and _is_loopback(host):
        return value.rstrip("/")
    _fail("INVALID_BASE_URL", f"{where} must be https (http only to a loopback host)", operation)


def _is_loopback(host: str) -> bool:
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _auth_entry(value: Any, index: int) -> Dict[str, Any]:
    where = f"connector.auth[{index}]"
    if type(value) is not dict:
        _fail("INVALID_CONNECTOR", f"{where} must be an object")
    kind = value.get("kind")
    if kind not in AUTH_KINDS:
        _fail("UNKNOWN_AUTH_KIND", f"{where}.kind is not one of {', '.join(AUTH_KINDS)}")
    required, optional = AUTH_KINDS[kind]
    extra = sorted(set(value) - required - optional)
    if any(_SECRET_WORDS.search(key) for key in extra):
        _fail("INLINE_SECRET", f"{where} carries a secret value; name a credential instead")
    entry = dict(_object(value, where, required, optional, None))
    credential = entry["credential"]
    if type(credential) is not str or not _CREDENTIAL_NAME.fullmatch(credential):
        # A value that is not a name is either a typo or the secret itself;
        # refuse both as the latter, since that is the one that leaks.
        _fail("INLINE_SECRET", f"{where}.credential must be a credential name, not a value")
    if kind == "api_token":
        if type(entry["header"]) is not str or not _HEADER_NAME.fullmatch(entry["header"]):
            _fail("INVALID_CONNECTOR", f"{where}.header must be a header name")
        if "scheme" in entry and (type(entry["scheme"]) is not str or not _SCHEME.fullmatch(entry["scheme"])):
            _fail("INLINE_SECRET" if isinstance(entry["scheme"], str) else "INVALID_CONNECTOR",
                  f"{where}.scheme must be a scheme word such as Bearer or Basic")
    for key in _AUTH_URL_KEYS:
        if key in entry:
            entry[key] = _url(entry[key], f"{where}.{key}")
    if "scopes" in entry:
        scopes = entry["scopes"]
        if type(scopes) is not list or len(scopes) > 32 or any(
            type(s) is not str or not s or len(s) > 256 or " " in s for s in scopes
        ):
            _fail("INVALID_CONNECTOR", f"{where}.scopes must be a list of scope names")
    return entry


def _rate_limit(value: Any) -> Dict[str, int]:
    limit = _object(value, "connector.rate_limit", frozenset({"requests", "per_seconds"}), frozenset(), None)
    for key, high in (("requests", 100_000), ("per_seconds", 86_400)):
        if type(limit[key]) is not int or not 1 <= limit[key] <= high:
            _fail("INVALID_CONNECTOR", f"connector.rate_limit.{key} is outside its bound")
    return {"requests": limit["requests"], "per_seconds": limit["per_seconds"]}


def path_parameters(path: str) -> List[str]:
    """The ``{name}`` placeholders in an operation path, in order."""
    return _PATH_PARAM.findall(path)


def _jsonpath(value: Any, where: str, op_id: str) -> str:
    try:
        parse(value)
    except JsonPathError:
        _fail("INVALID_JSONPATH", f"{where} of operation {op_id} is not a supported JSONPath", op_id)
    return value


def _inputs(value: Any, op_id: str, method: str, path_params: List[str]) -> Dict[str, Dict[str, Any]]:
    where = f"operation {op_id} inputs"
    if type(value) is not dict or len(value) > 128:
        _fail("INVALID_CONNECTOR", f"{where} must be a bounded mapping", op_id)
    inputs: Dict[str, Dict[str, Any]] = {}
    for name, spec in value.items():
        if not _INPUT_NAME.fullmatch(name):
            _fail("INVALID_CONNECTOR", f"{where} has an invalid input name", op_id)
        spec = dict(_object(spec, f"{where}.{name}", frozenset({"type"}), _INPUT_KEYS - {"type"}, op_id))
        if spec["type"] not in INPUT_TYPES:
            _fail("INVALID_CONNECTOR", f"{where}.{name}.type is not a JSON-schema type", op_id)
        location = spec.get("in", "path" if name in path_params else DEFAULT_INPUT_LOCATION[method])
        if location not in INPUT_LOCATIONS:
            _fail("INVALID_CONNECTOR", f"{where}.{name}.in must be one of {', '.join(INPUT_LOCATIONS)}", op_id)
        if location == "body" and method not in BODY_METHODS:
            _fail("INVALID_CONNECTOR", f"{where}.{name} is in: body but {method} sends no body", op_id)
        if (location == "path") != (name in path_params):
            _fail("INVALID_CONNECTOR", f"{where}.{name} is in: path exactly when the path has {{{name}}}", op_id)
        if "default" in spec:
            default = spec["default"]
            from ..engine.redaction import is_sensitive_param_name

            if spec.get("secret") is True or is_sensitive_param_name(name) or (
                isinstance(default, str) and _looks_like_secret(default)
            ):
                _fail("INLINE_SECRET", f"{where}.{name} has a default that would be a secret", op_id)
        for flag in ("required", "secret"):
            if flag in spec and type(spec[flag]) is not bool:
                _fail("INVALID_CONNECTOR", f"{where}.{name}.{flag} must be a boolean", op_id)
        if "scope" in spec and (type(spec["scope"]) is not str or not _KEY.fullmatch(spec["scope"])):
            _fail("INVALID_CONNECTOR", f"{where}.{name}.scope must be a scope key", op_id)
        spec["in"] = location
        if location == "path":
            spec["required"] = True
        inputs[name] = spec
    for name in path_params:
        if name not in inputs:
            _fail("PATH_PARAM_UNDECLARED", f"operation {op_id} path parameter {{{name}}} has no declared input",
                  op_id)
    return inputs


def _result_scope(value: Any, op_id: str) -> Dict[str, Any]:
    """``{"dimension", "path"}``; the text form leaves the dimension to the pack's one ``scopes`` key."""
    if type(value) is dict:
        declared = _object(value, f"operation {op_id} result_scope", frozenset({"dimension", "path"}), frozenset(),
                           op_id)
        if type(declared["dimension"]) is not str or not _KEY.fullmatch(declared["dimension"]):
            _fail("INVALID_CONNECTOR", f"operation {op_id} result_scope.dimension must be a scope key", op_id)
        return {"dimension": declared["dimension"], "path": _jsonpath(declared["path"], "result_scope", op_id)}
    return {"dimension": None, "path": _jsonpath(value, "result_scope", op_id)}


def _features(value: Any, op_id: str) -> Any:
    def keys(items: Any) -> List[str]:
        if type(items) is not list or len(items) > 32 or any(type(k) is not str or not _KEY.fullmatch(k)
                                                              for k in items):
            _fail("INVALID_CONNECTOR", f"operation {op_id} requires.features must list feature keys", op_id)
        return list(items)

    if type(value) is dict:
        _object(value, f"operation {op_id} requires.features", frozenset({"any"}), frozenset(), op_id)
        return {"any": keys(value["any"])}
    return keys(value)


def _consumes(value: Any, op_id: str) -> Dict[str, Any]:
    consumes = _object(value, f"operation {op_id} consumes", frozenset({"meter"}), frozenset({"amount"}), op_id)
    if type(consumes["meter"]) is not str or not _KEY.fullmatch(consumes["meter"]):
        _fail("INVALID_CONNECTOR", f"operation {op_id} consumes.meter must be a meter key", op_id)
    amount = consumes.get("amount", 1)
    if type(amount) is not int or not 1 <= amount <= 1_000_000:
        _fail("INVALID_CONNECTOR", f"operation {op_id} consumes.amount is outside its bound", op_id)
    return {"meter": consumes["meter"], "amount": amount}


def _paginate(value: Any, op_id: str) -> Dict[str, Any]:
    if type(value) is not dict or value.get("strategy") not in PAGINATION_STRATEGIES:
        _fail("INVALID_PAGINATION", f"operation {op_id} paginate.strategy is not one of "
              f"{', '.join(PAGINATION_STRATEGIES)}", op_id)
    strategy = value["strategy"]
    allowed = _PAGINATE_SHARED | PAGINATION_STRATEGIES[strategy]
    if set(value) - allowed:
        _fail("INVALID_PAGINATION", f"operation {op_id} paginate has a key {strategy} does not read", op_id)
    shape = {"strategy": strategy}
    for key in sorted(allowed - {"strategy"}):
        shape[key] = value.get(key, PAGINATE_DEFAULTS[key])
    for key in ("max_pages", "page_size", "start_page"):
        if key in shape and (type(shape[key]) is not int or not 0 <= shape[key] <= 10_000):
            _fail("INVALID_PAGINATION", f"operation {op_id} paginate.{key} is outside its bound", op_id)
    for key in ("data_path", "cursor_path", "offset_param", "limit_param", "page_param", "cursor_param"):
        if key in shape and (type(shape[key]) is not str or len(shape[key]) > 128):
            _fail("INVALID_PAGINATION", f"operation {op_id} paginate.{key} must be text", op_id)
    if strategy == "cursor" and not shape["cursor_path"]:
        _fail("INVALID_PAGINATION", f"operation {op_id} cursor pagination needs cursor_path", op_id)
    return shape


def _operation(value: Any, index: int) -> Dict[str, Any]:
    if type(value) is not dict:
        _fail("INVALID_CONNECTOR", f"connector.operations[{index}] must be an object")
    op_id = value.get("id")
    if type(op_id) is not str or len(op_id) > 96 or not _OPERATION_ID.fullmatch(op_id):
        _fail("INVALID_OPERATION_ID", f"connector.operations[{index}].id must be a dotted lowercase identifier")
    op = dict(_object(value, f"operation {op_id}", _OPERATION_REQUIRED, _OPERATION_OPTIONAL, op_id))

    # The consequence first: it is the decision a person has to make, and a
    # draft imported from OpenAPI is refused here until every one is made.
    consequence = op.get("consequence")
    if consequence is None:
        _fail("CONSEQUENCE_MISSING", f"operation {op_id} has no consequence; declare one of "
              f"{', '.join(CONSEQUENCES)}", op_id)
    if consequence not in CONSEQUENCES:
        _fail("CONSEQUENCE_UNKNOWN", f"operation {op_id} consequence is not one of {', '.join(CONSEQUENCES)}", op_id)

    method = op["method"]
    if method not in METHODS:
        _fail("INVALID_CONNECTOR", f"operation {op_id} method is not one of {', '.join(METHODS)}", op_id)
    path = op["path"]
    if type(path) is not str or len(path) > 1024 or not _PATH_TEXT.fullmatch(path) or "?" in path:
        _fail("INVALID_CONNECTOR", f"operation {op_id} path must be an absolute path with no query", op_id)
    params = path_parameters(path)
    if any(not _INPUT_NAME.fullmatch(name) for name in params) or len(set(params)) != len(params):
        _fail("INVALID_CONNECTOR", f"operation {op_id} path has an invalid or repeated {{parameter}}", op_id)

    normalized: Dict[str, Any] = {
        "id": op_id,
        "method": method,
        "path": path,
        "consequence": consequence,
        "inputs": _inputs(op.get("inputs", {}), op_id, method, params),
        "result_scope": None,
        "sensitive": [],
        "requires": {"features": []},
        "consumes": None,
        "paginate": None,
    }
    if op.get("result_scope") is not None:
        normalized["result_scope"] = _result_scope(op["result_scope"], op_id)
    sensitive = op.get("sensitive", [])
    if type(sensitive) is not list or len(sensitive) > MAX_PATHS:
        _fail("INVALID_JSONPATH", f"sensitive of operation {op_id} must be a list of JSONPaths", op_id)
    normalized["sensitive"] = [_jsonpath(item, "sensitive", op_id) for item in sensitive]
    if "requires" in op:
        requires = _object(op["requires"], f"operation {op_id} requires", frozenset(), frozenset({"features"}), op_id)
        normalized["requires"] = {"features": _features(requires.get("features", []), op_id)}
    if op.get("consumes") is not None:
        normalized["consumes"] = _consumes(op["consumes"], op_id)
    if op.get("paginate") is not None:
        normalized["paginate"] = _paginate(op["paginate"], op_id)
    for key in ("label", "description"):
        if key in op:
            if type(op[key]) is not str or not op[key]:
                _fail("INVALID_CONNECTOR", f"operation {op_id} {key} must be text", op_id)
            normalized[key] = op[key]
    if "timeout_ms" in op:
        if type(op["timeout_ms"]) is not int or not 100 <= op["timeout_ms"] <= 600_000:
            _fail("INVALID_CONNECTOR", f"operation {op_id} timeout_ms is outside its bound", op_id)
        normalized["timeout_ms"] = op["timeout_ms"]
    return normalized


def validate_connector(value: Any) -> Dict[str, Any]:
    """The normalized ``connector`` section, or a typed refusal."""
    connector = _object(value, "connector", _CONNECTOR_REQUIRED, _CONNECTOR_OPTIONAL, None)
    result: Dict[str, Any] = {"base_url": _url(connector["base_url"], "connector.base_url")}
    auth = connector.get("auth", [])
    if type(auth) is not list or len(auth) > MAX_AUTH:
        _fail("INVALID_CONNECTOR", "connector.auth must be a list of at most 4 entries")
    result["auth"] = [_auth_entry(entry, index) for index, entry in enumerate(auth)]
    result["rate_limit"] = _rate_limit(connector["rate_limit"]) if connector.get("rate_limit") is not None else None
    operations = connector["operations"]
    if type(operations) is not list or not 1 <= len(operations) <= MAX_OPERATIONS:
        _fail("INVALID_COUNT", "connector.operations count is outside its bound")
    normalized = [_operation(op, index) for index, op in enumerate(operations)]
    ids = [op["id"] for op in normalized]
    if len(set(ids)) != len(ids):
        _fail("DUPLICATE_ID", "connector operation ids must be unique")
    result["operations"] = sorted(normalized, key=lambda op: op["id"])
    return result


def module_id_for(namespace: str, op_id: str) -> str:
    return f"{namespace}.{op_id}"


def _params_schema(inputs: Mapping[str, Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """The registry parameter mapping: the inputs without the connector-only keys."""
    schema: Dict[str, Dict[str, Any]] = {}
    for name, spec in inputs.items():
        schema[name] = {key: value for key, value in spec.items() if key not in ("in", "scope")}
    return schema


def _contract(consequence: str) -> Dict[str, Any]:
    level = CONSEQUENCE_CONTRACTS[consequence]
    return {
        "actuates": False,
        "safety_class": level["safety_class"],
        "requires_safe_stop": False,
        "cancellable": True,
        "idempotent": level["idempotent"],
        "effects": list(level["effects"]),
    }


def operation_rows(connector: Mapping[str, Any], namespace: str) -> List[Dict[str, Any]]:
    """One raw ``flyto.pack.v1`` module row per operation, for ``_module_row`` to normalize."""
    rows = []
    for op in connector["operations"]:
        module_id = module_id_for(namespace, op["id"])
        row: Dict[str, Any] = {
            "module_id": module_id,
            "label": op.get("label", module_id),
            "description": op.get("description", f"{op['method']} {op['path']}"),
            "tags": ["connector", op["consequence"]],
            "params_schema": _params_schema(op["inputs"]),
            "provides_capability": module_id,
            "contract": _contract(op["consequence"]),
            "requires_credentials": bool(connector["auth"]),
            "handles_sensitive_data": bool(op["sensitive"]) or any(
                spec.get("secret") is True for spec in op["inputs"].values()
            ),
            "required_permissions": ["network.access"],
        }
        if "timeout_ms" in op:
            row["timeout_ms"] = op["timeout_ms"]
        rows.append(row)
    return rows


# -- entitlements and scopes ----------------------------------------------------------------

#: The pre-check sections a connector pack may declare beside ``connector``.
PROVIDER_SECTIONS = ("entitlements", "scopes")
MAX_FEATURES = 64
MAX_METERS = 32
MAX_SCOPES = 16
#: How long a probe answer may admit a read: at least a second, at most a day.
MAX_AGE_BOUNDS = (1, 86_400)
_ENTITLEMENTS_REQUIRED = frozenset({"probe", "features"})
_ENTITLEMENTS_OPTIONAL = frozenset({"meters", "max_age_s"})


def _key_list(value: Any, where: str, high: int) -> List[str]:
    if type(value) is not list or len(value) > high or any(type(k) is not str or not _KEY.fullmatch(k) for k in value):
        _fail("INVALID_ENTITLEMENTS", f"{where} must list keys")
    if len(set(value)) != len(value):
        _fail("DUPLICATE_ID", f"{where} lists a key twice")
    return list(value)


def _entitlements(value: Any, operations: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    from .connector_gate import DEFAULT_MAX_AGE_S

    section = _object(value, "entitlements", _ENTITLEMENTS_REQUIRED, _ENTITLEMENTS_OPTIONAL, None)
    probe = section["probe"]
    op = operations.get(probe) if type(probe) is str else None
    if op is None:
        _fail("PROBE_UNKNOWN", "entitlements.probe must name an operation of this connector")
    # The probe answers what gates the others, so it is gated by nothing, and
    # reading it changes nothing at the provider.
    if op["consequence"] != "observe" or op["requires"]["features"] or op["consumes"] is not None:
        _fail("PROBE_NOT_OBSERVE", "entitlements.probe must be an ungated observe operation", probe)
    features = _object(section["features"], "entitlements.features", frozenset({"keys", "path"}), frozenset(), None)
    meters = section.get("meters", {})
    if type(meters) is not dict or len(meters) > MAX_METERS:
        _fail("INVALID_ENTITLEMENTS", "entitlements.meters must map meter keys to JSONPaths")
    for name in meters:
        if not _KEY.fullmatch(name):
            _fail("INVALID_ENTITLEMENTS", "entitlements.meters has an invalid meter key")
    max_age = section.get("max_age_s", DEFAULT_MAX_AGE_S)
    if type(max_age) is not int or not MAX_AGE_BOUNDS[0] <= max_age <= MAX_AGE_BOUNDS[1]:
        _fail("INVALID_ENTITLEMENTS", "entitlements.max_age_s is outside its bound")
    return {
        "probe": probe,
        "max_age_s": max_age,
        "features": {
            "keys": _key_list(features["keys"], "entitlements.features.keys", MAX_FEATURES),
            "path": _jsonpath(features["path"], "entitlements.features.path", probe),
        },
        "meters": {name: _jsonpath(path, f"entitlements.meters.{name}", probe) for name, path in meters.items()},
    }


def _scopes(value: Any, operations: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    if type(value) is not list or len(value) > MAX_SCOPES:
        _fail("INVALID_SCOPES", "scopes must be a list of at most 16 dimensions")
    scopes = []
    for index, entry in enumerate(value):
        entry = _object(entry, f"scopes[{index}]", frozenset({"key"}), frozenset({"resolve"}), None)
        if type(entry["key"]) is not str or not _KEY.fullmatch(entry["key"]):
            _fail("INVALID_SCOPES", f"scopes[{index}].key must be a scope key")
        if "resolve" in entry and entry["resolve"] not in operations:
            _fail("RESOLVE_UNKNOWN", f"scopes[{index}].resolve must name an operation of this connector")
        scopes.append(dict(entry))
    keys = [entry["key"] for entry in scopes]
    if len(set(keys)) != len(keys):
        _fail("DUPLICATE_ID", "scopes keys must be unique")
    return scopes


def _bind_operation(op: Dict[str, Any], features: frozenset, meters: frozenset, dimensions: List[str],
                    gated: bool) -> None:
    """Refuse an operation whose pre-check names a feature, meter or dimension the pack does not declare."""
    op_id = op["id"]
    requires = op["requires"]["features"]
    keys = requires.get("any", []) if isinstance(requires, dict) else requires
    if (keys or op["consumes"] is not None) and not gated:
        _fail("ENTITLEMENTS_REQUIRED", f"operation {op_id} is gated, so the pack must declare entitlements", op_id)
    for key in keys:
        if key not in features:
            _fail("FEATURE_UNDECLARED", f"operation {op_id} requires {key}, which entitlements does not declare",
                  op_id)
    if op["consumes"] is not None and op["consumes"]["meter"] not in meters:
        _fail("METER_UNDECLARED", f"operation {op_id} consumes a meter entitlements does not declare", op_id)
    for name, spec in op["inputs"].items():
        if spec.get("scope") and spec["scope"] not in dimensions:
            _fail("SCOPE_UNDECLARED", f"operation {op_id} input {name} names an undeclared scope", op_id)
    declared = op["result_scope"]
    if declared is None:
        return
    if declared["dimension"] is None:
        # The text form is shorthand only while there is exactly one dimension
        # it could mean; nothing guesses between two.
        if len(dimensions) != 1:
            _fail("RESULT_SCOPE_DIMENSION_REQUIRED" if dimensions else "SCOPE_UNDECLARED",
                  f"operation {op_id} result_scope must name its dimension", op_id)
        declared["dimension"] = dimensions[0]
    elif declared["dimension"] not in dimensions:
        _fail("SCOPE_UNDECLARED", f"operation {op_id} result_scope names an undeclared scope", op_id)


def validate_provider_sections(top: Mapping[str, Any], connector: Dict[str, Any]) -> Dict[str, Any]:
    """The normalized ``entitlements`` and ``scopes`` sections, bound to the operations that use them.

    Every feature, meter and scope dimension an operation names must be
    declared, so the pre-check (``core.pack.connector_gate``) can always
    enforce what the pack says. A declaration it could not enforce refuses
    the pack instead.
    """
    operations = {op["id"]: op for op in connector["operations"]}
    entitlements = _entitlements(top["entitlements"], operations) if "entitlements" in top else None
    scopes = _scopes(top.get("scopes", []), operations)
    features = frozenset(entitlements["features"]["keys"]) if entitlements else frozenset()
    meters = frozenset(entitlements["meters"]) if entitlements else frozenset()
    dimensions = [entry["key"] for entry in scopes]
    for op in connector["operations"]:
        _bind_operation(op, features, meters, dimensions, entitlements is not None)
    return {"entitlements": entitlements, "scopes": scopes}
