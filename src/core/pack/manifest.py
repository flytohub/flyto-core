# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Module pack manifest — ``flyto.pack.v1``.

``@register_module`` is the Python way to write a module. What the platform
actually consumes is the registry row the decorator produces: an id, display
fields, a ``params_schema``, connection rules, and — for a capability — a
``flyto.capability-contract.v1`` contract. This file defines that row as
language-neutral JSON, so a pack written in any language can declare the same
thing and be loaded into the same registry, and a Python pack can print the
row its decorators produced (``core.pack.export``).

The document::

    {
      "schema": "flyto.pack.v1",
      "pack": {"id": "com.example.greeter", "version": "0.1.0",
               "namespaces": ["greeter"], "description": "..."},
      "runtime": {"binding": "subprocess-jsonrpc", "language": "node",
                  "entry": "index.js", "request_timeout_ms": 30000},
      "artifact": {"digest": "sha256:<tree digest of the pack directory>"},
      "modules": [ {<module row>}, ... ]
    }

``validate_pack_manifest`` returns the *normalized* manifest: every module row
carries every key in :data:`MODULE_DEFAULTS`, with the same defaults the
decorator applies. Two packs that declare the same module therefore normalize
to identical rows whatever language wrote them, and a signature is taken over
the normalized form, not over the file's whitespace or key order.

Validation fails closed with :class:`PackManifestError`, whose message never
reflects the rejected value.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..capability_contract import validate_contract
from ..plugin.manifest import DENIED_NAMESPACES

__all__ = [
    "PACK_SCHEMA",
    "MANIFEST_FILENAME",
    "SIGNATURE_FILENAME",
    "BINDINGS",
    "LOADABLE_BINDINGS",
    "MODULE_DEFAULTS",
    "PackManifestError",
    "validate_pack_manifest",
    "canonical_bytes",
    "manifest_sha256",
    "read_pack_manifest",
    "pack_tree_digest",
]

PACK_SCHEMA = "flyto.pack.v1"
MANIFEST_FILENAME = "flyto-pack.json"
SIGNATURE_FILENAME = "flyto-pack.sig.json"

#: How a host reaches the pack's code.
BINDINGS = ("subprocess-jsonrpc", "http", "inprocess-python")
#: Bindings ``core.pack.host.install_pack`` loads. ``inprocess-python`` packs
#: arrive through the ``flyto.modules`` entry point; their manifest is an
#: export of what the decorators registered.
LOADABLE_BINDINGS = ("subprocess-jsonrpc", "http")

MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 24
MAX_JSON_NODES = 100_000
MAX_TEXT_BYTES = 16_384
MAX_MODULES = 256
MAX_NAMESPACES = 8
MAX_LIST = 64
MAX_TREE_FILES = 10_000
MAX_TREE_BYTES = 512 * 1024 * 1024

_IDENT = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_MODULE_ID = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
_NAMESPACE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_PARAM_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_SEMVER = re.compile(
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_LANGUAGE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_PATTERN_TEXT = re.compile(r"^[A-Za-z0-9_.*-]{1,96}$")

_TOP_KEYS = frozenset({"schema", "pack", "runtime", "artifact", "modules"})
_PACK_REQUIRED = frozenset({"id", "version", "namespaces"})
_PACK_OPTIONAL = frozenset({"title", "description", "license", "min_host", "publisher_key_id"})
_ARTIFACT_KEYS = frozenset({"digest"})
_RUNTIME_KEYS = {
    "subprocess-jsonrpc": (frozenset({"binding", "language", "entry"}), frozenset({"request_timeout_ms"})),
    "http": (frozenset({"binding", "locality"}), frozenset({"request_timeout_ms", "max_response_bytes"})),
    "inprocess-python": (frozenset({"binding", "entry_point"}), frozenset()),
}
_STABILITY = ("stable", "beta", "alpha", "deprecated")
_REQUEST_TIMEOUT_MAX = 600_000
_DEFAULT_REQUEST_TIMEOUT = 30_000
_RESPONSE_BYTES_MAX = 16 * 1024 * 1024
_DEFAULT_RESPONSE_BYTES = 1024 * 1024

#: Every key a normalized module row carries, with the default the
#: ``@register_module`` decorator applies when the author leaves it out.
#: ``label``, ``label_key`` and ``category`` default from the module id, so
#: they are filled in by :func:`_module_row` rather than listed here.
MODULE_DEFAULTS: Dict[str, Any] = {
    "version": "1.0.0",
    "stability": "stable",
    "description": "",
    "description_key": None,
    "subcategory": None,
    "tags": [],
    "icon": None,
    "color": None,
    "params_schema": {},
    "output_schema": {},
    "input_types": [],
    "output_types": [],
    "can_receive_from": ["*"],
    "can_connect_to": ["*"],
    "provides_capability": "",
    "contract": None,
    "required_permissions": [],
    "timeout_ms": None,
    "retryable": False,
    "max_retries": None,
    "concurrent_safe": True,
    "requires_credentials": False,
    "handles_sensitive_data": False,
}
_MODULE_KEYS = frozenset(MODULE_DEFAULTS) | {"module_id", "label", "label_key", "category"}


class PackManifestError(ValueError):
    """A stable, value-free failure of pack validation or verification."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _fail(code: str, message: str) -> None:
    raise PackManifestError(code, message)


# ---------------------------------------------------------------------------
# Bounded JSON copy
# ---------------------------------------------------------------------------

_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


def _safe_text(value: Any, code: str, message: str) -> str:
    if type(value) is not str:
        _fail(code, message)
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        _fail(code, message)
    if len(encoded) > MAX_TEXT_BYTES:
        _fail(code, message)
    for ch in value:
        # Tab and newline are ordinary in descriptions; every other control,
        # bidi override, zero-width format, surrogate or unassigned code point
        # is refused before the text can reach a catalog or a log line.
        if ch in "\t\n":
            continue
        if unicodedata.category(ch) in _UNSAFE_CATEGORIES:
            _fail(code, message)
    return value


def _plain(value: Any, depth: int, counter: List[int]) -> Any:
    counter[0] += 1
    if counter[0] > MAX_JSON_NODES:
        _fail("MANIFEST_TOO_COMPLEX", "manifest exceeds the node limit")
    if depth > MAX_JSON_DEPTH:
        _fail("MANIFEST_TOO_DEEP", "manifest exceeds the depth limit")
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        if value != value or value in (float("inf"), float("-inf")):
            _fail("INVALID_VALUE", "manifest contains a non-finite number")
        return value
    if type(value) is str:
        return _safe_text(value, "INVALID_TEXT", "manifest text is invalid or too long")
    if isinstance(value, Mapping):
        result: Dict[str, Any] = {}
        try:
            items = list(value.items())
        except Exception:  # noqa: BLE001 - hostile mapping
            _fail("INVALID_MAPPING", "manifest mapping could not be read")
        for key, item in items:
            _safe_text(key, "INVALID_KEY", "manifest key is invalid or too long")
            if key in result:
                _fail("DUPLICATE_KEY", "manifest contains a duplicate key")
            result[key] = _plain(item, depth + 1, counter)
        return result
    if isinstance(value, (list, tuple)):
        return [_plain(item, depth + 1, counter) for item in value]
    _fail("INVALID_TYPE", "manifest contains a non-JSON value")


def canonical_bytes(value: Any) -> bytes:
    """Canonical JSON: sorted keys, no whitespace, UTF-8, no NaN."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def manifest_sha256(manifest: Mapping[str, Any]) -> str:
    """Hex SHA-256 of a normalized manifest's canonical bytes."""
    return hashlib.sha256(canonical_bytes(manifest)).hexdigest()


# ---------------------------------------------------------------------------
# Field checks
# ---------------------------------------------------------------------------


def _object(value: Any, where: str, required: frozenset, optional: frozenset = frozenset()) -> Dict[str, Any]:
    if type(value) is not dict:
        _fail("INVALID_OBJECT", f"{where} must be an object")
    if set(value) - required - optional:
        _fail("UNKNOWN_KEY", f"{where} contains an unknown key")
    missing = sorted(required - set(value))
    if missing:
        _fail("MISSING_FIELD", f"{where} is missing required field: {missing[0]}")
    return value


def _text(value: Any, where: str, *, allow_none: bool = False, allow_empty: bool = True) -> Optional[str]:
    if value is None and allow_none:
        return None
    if type(value) is not str or (not allow_empty and not value):
        _fail("INVALID_FIELD", f"{where} must be text")
    return value


def _label(value: Any, where: str) -> Any:
    """A display string, or a ``{language: text}`` mapping of them."""
    if type(value) is str:
        return value
    if type(value) is dict and value and all(
        type(k) is str and re.fullmatch(r"[a-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?", k) and type(v) is str
        for k, v in value.items()
    ):
        return value
    _fail("INVALID_FIELD", f"{where} must be text or a language-to-text mapping")


def _string_list(value: Any, where: str, pattern: Optional[re.Pattern] = None) -> List[str]:
    if type(value) is not list or len(value) > MAX_LIST:
        _fail("INVALID_FIELD", f"{where} must be a bounded list")
    for item in value:
        if type(item) is not str or not item or (pattern is not None and not pattern.fullmatch(item)):
            _fail("INVALID_FIELD", f"{where} contains an invalid entry")
    if len(set(value)) != len(value):
        _fail("INVALID_FIELD", f"{where} contains duplicates")
    return list(value)


def _bool(value: Any, where: str) -> bool:
    # No absent-means-true and no truthy coercion across a language boundary:
    # a JSON boolean or nothing.
    if type(value) is not bool:
        _fail("INVALID_BOOLEAN", f"{where} must be a boolean")
    return value


def _bounded_int(value: Any, where: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        _fail("INVALID_BOUND", f"{where} is outside its bound")
    return value


def _params_schema(value: Any, where: str) -> Dict[str, Any]:
    """The registry's parameter mapping: ``{name: {"type": ..., ...}}``.

    Only the outer shape is fixed — names, and a ``type`` on every parameter.
    Everything inside a definition is bounded JSON already, and is exactly what
    ``@register_module`` accepts, so a Python export round-trips unchanged.
    """
    if type(value) is not dict or len(value) > 256:
        _fail("INVALID_PARAMS_SCHEMA", f"{where} must be a bounded parameter mapping")
    for name, definition in value.items():
        if not _PARAM_NAME.fullmatch(name) or name == "__event__":
            _fail("INVALID_PARAMS_SCHEMA", f"{where} contains an invalid parameter name")
        if type(definition) is not dict or type(definition.get("type")) is not str:
            _fail("INVALID_PARAMS_SCHEMA", f"{where} parameters must be objects with a type")
    return value


def _module_row(value: Any, index: int, namespaces: Tuple[str, ...]) -> Dict[str, Any]:
    where = f"modules[{index}]"
    item = _object(value, where, frozenset({"module_id"}), _MODULE_KEYS - {"module_id"})
    module_id = _text(item["module_id"], f"{where}.module_id", allow_empty=False)
    if len(module_id) > 128 or not _MODULE_ID.fullmatch(module_id):
        _fail("INVALID_MODULE_ID", f"{where}.module_id is invalid")
    if module_id.split(".", 1)[0] not in namespaces:
        _fail("MODULE_NAMESPACE_MISMATCH", f"{where}.module_id is outside the pack namespaces")

    row: Dict[str, Any] = copy.deepcopy(MODULE_DEFAULTS)
    row["module_id"] = module_id
    row["label"] = module_id
    row["label_key"] = f"modules.{module_id}.label"
    row["category"] = module_id.split(".", 1)[0]
    row.update({k: v for k, v in item.items() if k != "module_id"})

    if not _SEMVER.fullmatch(_text(row["version"], f"{where}.version", allow_empty=False)):
        _fail("INVALID_SEMVER", f"{where}.version must be semver")
    if row["stability"] not in _STABILITY:
        _fail("INVALID_FIELD", f"{where}.stability is not a stability level")
    row["label"] = _label(row["label"], f"{where}.label")
    row["description"] = _label(row["description"], f"{where}.description") if row["description"] != "" else ""
    for name in ("label_key", "description_key", "subcategory", "icon", "color"):
        _text(row[name], f"{where}.{name}", allow_none=True)
    if not _IDENT.fullmatch(_text(row["category"], f"{where}.category", allow_empty=False)):
        _fail("INVALID_FIELD", f"{where}.category is invalid")
    row["tags"] = _string_list(row["tags"], f"{where}.tags")
    row["input_types"] = _string_list(row["input_types"], f"{where}.input_types")
    row["output_types"] = _string_list(row["output_types"], f"{where}.output_types")
    row["can_receive_from"] = _string_list(row["can_receive_from"], f"{where}.can_receive_from", _PATTERN_TEXT)
    row["can_connect_to"] = _string_list(row["can_connect_to"], f"{where}.can_connect_to", _PATTERN_TEXT)
    row["required_permissions"] = _string_list(
        row["required_permissions"], f"{where}.required_permissions", _IDENT
    )
    row["params_schema"] = _params_schema(row["params_schema"], f"{where}.params_schema")
    if type(row["output_schema"]) is not dict:
        _fail("INVALID_FIELD", f"{where}.output_schema must be an object")
    for name in ("retryable", "concurrent_safe", "requires_credentials", "handles_sensitive_data"):
        _bool(row[name], f"{where}.{name}")
    if row["timeout_ms"] is not None:
        _bounded_int(row["timeout_ms"], f"{where}.timeout_ms", 1, 3_600_000)
    # The decorator's rule: a module that does not retry has no retries.
    if row["max_retries"] is None:
        row["max_retries"] = 3 if row["retryable"] else 0
    _bounded_int(row["max_retries"], f"{where}.max_retries", 0, 10)
    if not row["retryable"]:
        row["max_retries"] = 0

    capability = _text(row["provides_capability"], f"{where}.provides_capability")
    if capability and (len(capability) > 96 or not _IDENT.fullmatch(capability)):
        _fail("INVALID_CAPABILITY", f"{where}.provides_capability is invalid")
    if row["contract"] is not None:
        if not capability:
            _fail("INVALID_CONTRACT", f"{where}.contract requires provides_capability")
        try:
            row["contract"] = validate_contract(row["contract"], row["params_schema"])
        except ValueError:
            _fail("INVALID_CONTRACT", f"{where}.contract is not a valid flyto.capability-contract.v1")
    return row


def _runtime(value: Any) -> Dict[str, Any]:
    if type(value) is not dict or value.get("binding") not in BINDINGS:
        _fail("INVALID_RUNTIME", "runtime.binding is not supported")
    required, optional = _RUNTIME_KEYS[value["binding"]]
    runtime = dict(_object(value, "runtime", required, optional))
    binding = runtime["binding"]
    if binding == "subprocess-jsonrpc":
        language = _text(runtime["language"], "runtime.language", allow_empty=False)
        if not _LANGUAGE.fullmatch(language):
            _fail("INVALID_RUNTIME", "runtime.language is invalid")
        entry = _text(runtime["entry"], "runtime.entry", allow_empty=False)
        parts = entry.replace("\\", "/").split("/")
        if (
            len(entry) > 256
            or entry.startswith("/")
            or "\x00" in entry
            or any(part in ("", ".", "..") for part in parts)
            or os.path.isabs(entry)
        ):
            _fail("INVALID_RUNTIME", "runtime.entry must be a relative path inside the pack")
    elif binding == "http":
        if runtime["locality"] not in ("same_host", "same_network"):
            _fail("INVALID_RUNTIME", "runtime.locality is invalid")
        runtime.setdefault("max_response_bytes", _DEFAULT_RESPONSE_BYTES)
        _bounded_int(runtime["max_response_bytes"], "runtime.max_response_bytes", 1, _RESPONSE_BYTES_MAX)
    else:
        entry_point = _text(runtime["entry_point"], "runtime.entry_point", allow_empty=False)
        if len(entry_point) > 256 or not re.fullmatch(r"[A-Za-z0-9_.:-]+", entry_point):
            _fail("INVALID_RUNTIME", "runtime.entry_point is invalid")
    if binding != "inprocess-python":
        runtime.setdefault("request_timeout_ms", _DEFAULT_REQUEST_TIMEOUT)
        _bounded_int(runtime["request_timeout_ms"], "runtime.request_timeout_ms", 100, _REQUEST_TIMEOUT_MAX)
    return runtime


def validate_pack_manifest(data: Any) -> Dict[str, Any]:
    """Return the normalized ``flyto.pack.v1`` manifest, or raise ``PackManifestError``."""
    plain = _plain(data, 0, [0])
    if len(canonical_bytes(plain)) > MAX_MANIFEST_BYTES:
        _fail("MANIFEST_TOO_LARGE", "manifest exceeds the byte limit")
    # The schema is compared before any other key is read.
    if type(plain) is not dict or plain.get("schema") != PACK_SCHEMA:
        _fail("UNSUPPORTED_SCHEMA", "schema must be flyto.pack.v1")
    top = _object(plain, "manifest", frozenset({"schema", "pack", "runtime", "modules"}), _TOP_KEYS)

    pack = dict(_object(top["pack"], "pack", _PACK_REQUIRED, _PACK_OPTIONAL))
    pack_id = _text(pack["id"], "pack.id", allow_empty=False)
    if len(pack_id) > 128 or not _IDENT.fullmatch(pack_id):
        _fail("INVALID_PACK_ID", "pack.id must be a lowercase identifier")
    if not _SEMVER.fullmatch(_text(pack["version"], "pack.version", allow_empty=False)):
        _fail("INVALID_SEMVER", "pack.version must be semver")
    namespaces = _string_list(pack["namespaces"], "pack.namespaces", _NAMESPACE)
    if not 1 <= len(namespaces) <= MAX_NAMESPACES:
        _fail("INVALID_NAMESPACE", "pack.namespaces must name 1 to 8 namespaces")
    if any(ns in DENIED_NAMESPACES for ns in namespaces):
        # A pack cannot claim a namespace flyto-core ships or denies: that is
        # how an out-of-process pack would shadow shell.exec or file.read.
        _fail("INVALID_NAMESPACE", "pack.namespaces contains a reserved namespace")
    for name in ("title", "description", "license", "publisher_key_id"):
        if name in pack:
            _text(pack[name], f"pack.{name}", allow_empty=False)
    if "min_host" in pack and not _SEMVER.fullmatch(_text(pack["min_host"], "pack.min_host")):
        _fail("INVALID_SEMVER", "pack.min_host must be semver")

    runtime = _runtime(top["runtime"])

    result: Dict[str, Any] = {"schema": PACK_SCHEMA, "pack": pack, "runtime": runtime}
    if "artifact" in top:
        artifact = _object(top["artifact"], "artifact", _ARTIFACT_KEYS)
        if not _DIGEST.fullmatch(_text(artifact["digest"], "artifact.digest")):
            _fail("INVALID_DIGEST", "artifact.digest must be lowercase sha256:<hex>")
        result["artifact"] = {"digest": artifact["digest"]}

    modules = top["modules"]
    if type(modules) is not list or not 1 <= len(modules) <= MAX_MODULES:
        _fail("INVALID_COUNT", "modules count is outside its bound")
    rows = [_module_row(value, index, tuple(namespaces)) for index, value in enumerate(modules)]
    ids = [row["module_id"] for row in rows]
    if len(set(ids)) != len(ids):
        _fail("DUPLICATE_ID", "module ids must be unique")
    result["modules"] = sorted(rows, key=lambda row: row["module_id"])
    pack["namespaces"] = sorted(namespaces)
    return result


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def _read_regular_file(path: Path, limit: int) -> bytes:
    """Read one regular file without following a final symlink, bounded."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        _fail("FILE_UNREADABLE", "a pack file is missing, a symlink, or unreadable")
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            _fail("FILE_INVALID", "a pack file is not a bounded regular file")
        chunks = []
        total = 0
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > limit:
                _fail("FILE_INVALID", "a pack file is not a bounded regular file")
            chunks.append(block)
        return b"".join(chunks)
    finally:
        os.close(fd)


def read_pack_manifest(pack_dir: os.PathLike[str] | str) -> Dict[str, Any]:
    """Read and validate ``<pack_dir>/flyto-pack.json``."""
    raw = _read_regular_file(Path(pack_dir) / MANIFEST_FILENAME, MAX_MANIFEST_BYTES)
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates)
    except PackManifestError:
        raise
    except (UnicodeDecodeError, ValueError):
        _fail("INVALID_JSON", "flyto-pack.json is not valid UTF-8 JSON")
    return validate_pack_manifest(data)


def _reject_duplicates(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("DUPLICATE_KEY", "manifest contains a duplicate key")
        result[key] = value
    return result


def pack_tree_digest(pack_dir: os.PathLike[str] | str) -> str:
    """``sha256:<hex>`` over every file in the pack except its manifest and signature.

    The digest is SHA-256 over sorted lines ``<posix relative path> NUL <file
    sha256 hex> NUL <size> LF``. A symlink anywhere in the tree, a special
    file, or a tree beyond the file/byte bounds fails closed: the thing
    attested must be exactly the set of regular files that will run.
    """
    root = Path(pack_dir)
    try:
        root_info = os.lstat(root)
    except OSError:
        _fail("PACK_UNREADABLE", "pack directory is missing or unreadable")
    if not stat.S_ISDIR(root_info.st_mode):
        _fail("PACK_UNREADABLE", "pack path must be a real directory")
    entries: List[Tuple[str, str, int]] = []
    total = 0
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        for name in list(dirnames):
            if os.path.islink(os.path.join(current, name)):
                _fail("PACK_SYMLINK", "pack contains a symbolic link")
        for name in filenames:
            full = Path(current) / name
            rel = full.relative_to(root).as_posix()
            if rel in (MANIFEST_FILENAME, SIGNATURE_FILENAME):
                continue
            info = os.lstat(full)
            if stat.S_ISLNK(info.st_mode):
                _fail("PACK_SYMLINK", "pack contains a symbolic link")
            if not stat.S_ISREG(info.st_mode):
                _fail("PACK_INVALID", "pack contains a special file")
            if len(entries) >= MAX_TREE_FILES:
                _fail("PACK_TOO_LARGE", "pack exceeds the file count limit")
            data = _read_regular_file(full, MAX_TREE_BYTES - total)
            total += len(data)
            entries.append((rel, hashlib.sha256(data).hexdigest(), len(data)))
    hasher = hashlib.sha256()
    for rel, digest, size in sorted(entries):
        hasher.update(f"{rel}\x00{digest}\x00{size}\n".encode("utf-8"))
    return "sha256:" + hasher.hexdigest()
