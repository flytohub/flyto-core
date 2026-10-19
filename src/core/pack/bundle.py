# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Bundles — ``flyto.bundle.v1``: packs pinned by digest, plus workflows and templates.

A bundle is what a solution ships as one unit: the packs it needs, the Space
workflow documents that use them, and the report templates those workflows
fill. It **references** each pack by id, exact version and pack digest, and
never carries a copy, so a pack has one artifact however many bundles use
it::

    {
      "schema": "flyto.bundle.v1",
      "bundle": {"id": "com.example.rating-review", "version": "0.1.0", "title": "..."},
      "packs": [{"id": "com.example.ratings", "version": "0.1.0", "digest": "sha256:<pack digest>"}],
      "workflows": [{"name": "rating-review", "path": "workflows/rating-review.json", "digest": "sha256:<hex>"}],
      "templates": [{"name": "rating-summary", "path": "templates/rating-summary.md",
                     "media_type": "text/markdown", "digest": "sha256:<hex>"}]
    }

A bundle directory (or its zip) holds ``flyto-bundle.json``, the declared
workflow and template files, and optionally ``flyto-bundle.sig.json`` —
nothing else. :func:`verify_bundle` refuses, with a typed reason:

* a referenced pack that is missing, revoked, or whose digest differs from
  the pin (``PACK_NOT_FOUND``, ``PACK_REVOKED``, ``PACK_DIGEST_MISMATCH``);
* a workflow or template whose bytes differ from its digest;
* a workflow that uses a module no referenced pack and no core module
  provides (``MODULE_NOT_PROVIDED``), counting modules carried inside an
  inline sub-workflow, found by the same collector the module policy uses;
* a duplicate pack id, item name or path (``DUPLICATE_NAME``), a version
  that is not one exact release (``VERSION_NOT_PINNED``), and any file the
  manifest does not declare (``UNDECLARED_FILE``).

:func:`build_bundle` fills the pins and digests from the packs it is given
and the files on disk, validates the result the same way, and writes one
deterministic zip, signed when given a key.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple

from .manifest import (
    _IDENT,
    _SEMVER,
    PackManifestError,
    _iter_pack_files,
    _read_regular_file,
    canonical_bytes,
)

__all__ = ["BUNDLE_SCHEMA", "BUNDLE_FILENAME", "BUNDLE_SIGNATURE_FILENAME", "build_bundle", "verify_bundle",
           "validate_bundle_manifest", "core_module_ids"]

BUNDLE_SCHEMA = "flyto.bundle.v1"
BUNDLE_FILENAME = "flyto-bundle.json"
BUNDLE_SIGNATURE_FILENAME = "flyto-bundle.sig.json"
BUNDLE_SIGNATURE_SCHEMA = "flyto.bundle-signature.v1"
BUNDLE_SIGNATURE_DOMAIN = b"flyto.bundle-signature.v1\n"

#: The file items a bundle carries: how each is declared and what a changed one is called.
ITEM_KINDS: Mapping[str, Mapping[str, Any]] = {
    "workflows": {"optional": frozenset(), "mismatch": "WORKFLOW_DIGEST_MISMATCH"},
    "templates": {"optional": frozenset({"media_type"}), "mismatch": "TEMPLATE_DIGEST_MISMATCH"},
}
#: Workflow document suffix -> how it is read.
WORKFLOW_READERS = {".json": "json", ".yaml": "yaml", ".yml": "yaml"}

MAX_PACKS = 64
MAX_ITEMS = 256
MAX_BUNDLE_MANIFEST = 1024 * 1024
MAX_ITEM_BYTES = 16 * 1024 * 1024

_TOP_REQUIRED = frozenset({"schema", "bundle", "packs"})
_TOP_OPTIONAL = frozenset(ITEM_KINDS)
_HEADER_REQUIRED = frozenset({"id", "version"})
_HEADER_OPTIONAL = frozenset({"title", "description"})
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_MEDIA_TYPE = re.compile(r"^[a-z]+/[a-z0-9.+-]{1,64}$")


def _fail(code: str, message: str) -> None:
    raise PackManifestError(code, message)


def _object(value: Any, where: str, required: frozenset, optional: frozenset = frozenset()) -> Dict[str, Any]:
    if type(value) is not dict:
        _fail("INVALID_BUNDLE", f"{where} must be an object")
    unknown = set(value) - required - optional
    if unknown:
        _fail("UNKNOWN_KEY", f"{where} contains an unknown key: {sorted(unknown)[0]}")
    missing = sorted(required - set(value))
    if missing:
        _fail("MISSING_FIELD", f"{where} is missing required field: {missing[0]}")
    return dict(value)


def _digest(value: Any, where: str) -> str:
    if type(value) is not str or not _DIGEST.fullmatch(value):
        _fail("INVALID_DIGEST", f"{where} must be lowercase sha256:<hex>")
    return value


def _path(value: Any, where: str) -> str:
    if type(value) is not str or not value or len(value) > 256:
        _fail("INVALID_BUNDLE", f"{where} must be a relative path inside the bundle")
    parts = value.split("/")
    if (value.startswith("/") or "\\" in value or ":" in value or "\x00" in value
            or any(part in ("", ".", "..") for part in parts)
            or value in (BUNDLE_FILENAME, BUNDLE_SIGNATURE_FILENAME)):
        _fail("INVALID_BUNDLE", f"{where} must be a relative path inside the bundle")
    return value


def validate_bundle_manifest(data: Any, *, pinned: bool = True) -> Dict[str, Any]:
    """The normalized bundle manifest, or a typed refusal. ``pinned=False`` lets a source omit digests."""
    if type(data) is not dict or data.get("schema") != BUNDLE_SCHEMA:
        _fail("UNSUPPORTED_SCHEMA", f"schema must be {BUNDLE_SCHEMA}")
    top = _object(data, "bundle manifest", _TOP_REQUIRED, _TOP_OPTIONAL)
    header = _object(top["bundle"], "bundle", _HEADER_REQUIRED, _HEADER_OPTIONAL)
    if type(header["id"]) is not str or len(header["id"]) > 128 or not _IDENT.fullmatch(header["id"]):
        _fail("INVALID_BUNDLE", "bundle.id must be a lowercase identifier")
    if type(header["version"]) is not str or not _SEMVER.fullmatch(header["version"]):
        _fail("VERSION_NOT_PINNED", "bundle.version must be one exact semver release")
    for key in ("title", "description"):
        if key in header and (type(header[key]) is not str or not header[key]):
            _fail("INVALID_BUNDLE", f"bundle.{key} must be text")

    packs = top["packs"]
    if type(packs) is not list or not 1 <= len(packs) <= MAX_PACKS:
        _fail("INVALID_BUNDLE", f"packs must list 1 to {MAX_PACKS} pack references")
    refs = []
    for index, value in enumerate(packs):
        where = f"packs[{index}]"
        ref = _object(value, where, frozenset({"id", "version"}) | (frozenset({"digest"}) if pinned else frozenset()),
                      frozenset() if pinned else frozenset({"digest"}))
        if type(ref["id"]) is not str or not _IDENT.fullmatch(ref["id"]):
            _fail("INVALID_BUNDLE", f"{where}.id must be a pack id")
        if type(ref["version"]) is not str or not _SEMVER.fullmatch(ref["version"]):
            # A range, a prefix or "latest" would let the pack change under the bundle.
            _fail("VERSION_NOT_PINNED", f"{where}.version must be one exact semver release")
        if "digest" in ref:
            _digest(ref["digest"], f"{where}.digest")
        refs.append(ref)
    _unique([ref["id"] for ref in refs], "a pack is referenced twice")

    result: Dict[str, Any] = {"schema": BUNDLE_SCHEMA, "bundle": header,
                              "packs": sorted(refs, key=lambda ref: ref["id"])}
    names: List[str] = []
    paths: List[str] = []
    for kind, spec in ITEM_KINDS.items():
        items = top.get(kind, [])
        if type(items) is not list or len(items) > MAX_ITEMS:
            _fail("INVALID_BUNDLE", f"{kind} must be a bounded list")
        normalized = []
        for index, value in enumerate(items):
            where = f"{kind}[{index}]"
            required = frozenset({"name", "path"}) | (frozenset({"digest"}) if pinned else frozenset())
            optional = spec["optional"] | (frozenset() if pinned else frozenset({"digest"}))
            item = _object(value, where, required, optional)
            if type(item["name"]) is not str or not _NAME.fullmatch(item["name"]):
                _fail("INVALID_BUNDLE", f"{where}.name must be a lowercase name")
            item["path"] = _path(item["path"], f"{where}.path")
            if "digest" in item:
                _digest(item["digest"], f"{where}.digest")
            if "media_type" in item and (type(item["media_type"]) is not str
                                         or not _MEDIA_TYPE.fullmatch(item["media_type"])):
                _fail("INVALID_BUNDLE", f"{where}.media_type must be a media type")
            names.append(item["name"])
            paths.append(item["path"])
            normalized.append(item)
        result[kind] = sorted(normalized, key=lambda item: item["name"])
    # One namespace for every item: a workflow and a template with one name
    # would be ambiguous to whatever refers to it.
    _unique(names, "two bundle items share a name")
    _unique([path.casefold() for path in paths], "two bundle items share a path")
    return result


def _unique(values: Iterable[str], message: str) -> None:
    values = list(values)
    if len(set(values)) != len(values):
        _fail("DUPLICATE_NAME", message)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def core_module_ids() -> FrozenSet[str]:
    """Every module flyto-core itself registers (no pack or plugin module)."""
    from ..modules.registry import ModuleRegistry

    metadata = ModuleRegistry.get_all_metadata(filter_by_stability=False)
    return frozenset(module_id for module_id, meta in metadata.items() if not meta.get("plugin"))


def _workflow_modules(path: str, data: bytes) -> List[str]:
    from ..module_policy import _collect_module_ids

    reader = WORKFLOW_READERS.get(Path(path).suffix.lower())
    if reader is None:
        _fail("WORKFLOW_INVALID", f"workflow {path} must be {', '.join(WORKFLOW_READERS)}")
    try:
        text = data.decode("utf-8")
        if reader == "json":
            document = json.loads(text)
        else:
            import yaml

            document = yaml.safe_load(text)
    except Exception:  # noqa: BLE001 - a decode, JSON or YAML error: the document is unreadable
        _fail("WORKFLOW_INVALID", f"workflow {path} is not a readable document")
    if type(document) is not dict:
        _fail("WORKFLOW_INVALID", f"workflow {path} must be an object")
    return sorted(_collect_module_ids(document))


def _resolve_packs(packs: Iterable[os.PathLike[str] | str], *, trusted_keys: Optional[Mapping[str, Any]],
                   require_signature: bool, revocations: Any) -> Dict[str, Dict[str, Any]]:
    from .portable import verify_pack

    found: Dict[str, Dict[str, Any]] = {}
    for source in packs:
        report = verify_pack(source, trusted_keys=trusted_keys, require_signature=require_signature,
                             revocations=revocations)
        found.setdefault(f"{report['pack_id']}@{report['version']}", report)
    return found


def _check_packs(refs: List[Dict[str, Any]], found: Mapping[str, Mapping[str, Any]]) -> Tuple[List, FrozenSet[str]]:
    pinned = []
    modules: set = set()
    for ref in refs:
        report = found.get(f"{ref['id']}@{ref['version']}")
        if report is None:
            _fail("PACK_NOT_FOUND", f"pack {ref['id']} {ref['version']} was not supplied")
        if "digest" in ref and ref["digest"] != report["pack_digest"]:
            _fail("PACK_DIGEST_MISMATCH", f"pack {ref['id']} {ref['version']} is not the pack the bundle pins")
        pinned.append({"id": ref["id"], "version": ref["version"], "digest": report["pack_digest"]})
        modules.update(report["module_ids"])
    return pinned, frozenset(modules)


def _check_items(manifest: Mapping[str, Any], files: Mapping[str, bytes], provided: FrozenSet[str],
                 *, fill: bool) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for kind, spec in ITEM_KINDS.items():
        out[kind] = []
        for item in manifest[kind]:
            data = files.get(item["path"])
            if data is None:
                _fail("FILE_MISSING", f"{kind} item {item['name']} has no file at {item['path']}")
            digest = _sha256(data)
            if not fill and item["digest"] != digest:
                _fail(spec["mismatch"], f"{kind} item {item['name']} does not match its digest")
            entry = {**item, "digest": digest}
            if kind == "workflows":
                used = _workflow_modules(item["path"], data)
                missing = [module_id for module_id in used if module_id not in provided]
                if missing:
                    _fail("MODULE_NOT_PROVIDED", f"workflow {item['name']} uses modules no referenced pack or core "
                          f"provides: {', '.join(missing)}")
                entry["modules"] = used
            out[kind].append(entry)
    return out


def _read_tree(root: Path, manifest: Mapping[str, Any]) -> Dict[str, bytes]:
    files = {rel: data for rel, data, _ in _iter_pack_files(root, skip=(BUNDLE_FILENAME, BUNDLE_SIGNATURE_FILENAME))}
    declared = {item["path"] for kind in ITEM_KINDS for item in manifest[kind]}
    extra = sorted(set(files) - declared)
    if extra:
        # A pack copied in, or anything else the manifest does not attest.
        _fail("UNDECLARED_FILE", f"the bundle holds a file its manifest does not declare: {extra[0]}")
    return files


def _read_manifest(root: Path) -> Any:
    from .manifest import _reject_duplicates

    raw = _read_regular_file(root / BUNDLE_FILENAME, MAX_BUNDLE_MANIFEST)
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates)
    except PackManifestError:
        raise
    except (UnicodeDecodeError, ValueError):
        _fail("INVALID_JSON", f"{BUNDLE_FILENAME} is not valid UTF-8 JSON")


def _core_ids(core_ids: Optional[Iterable[str]]) -> FrozenSet[str]:
    return frozenset(core_ids) if core_ids is not None else core_module_ids()


def _report(manifest: Mapping[str, Any], pinned: List, items: Mapping[str, List], signature: Any) -> Dict[str, Any]:
    return {
        "bundle_id": manifest["bundle"]["id"],
        "version": manifest["bundle"]["version"],
        "bundle_sha256": hashlib.sha256(canonical_bytes(manifest)).hexdigest(),
        "packs": pinned,
        "workflows": [{"name": i["name"], "digest": i["digest"], "modules": i["modules"]} for i in items["workflows"]],
        "templates": [{"name": i["name"], "digest": i["digest"]} for i in items["templates"]],
        "signature": signature,
    }


def _verify_dir(root: Path, packs: Iterable, *, trusted_keys, require_signature, revocations,
                require_bundle_signature, core_module_ids) -> Dict[str, Any]:
    from .signature import verify_detached

    manifest = validate_bundle_manifest(_read_manifest(root), pinned=True)
    signature = None
    sig_path = root / BUNDLE_SIGNATURE_FILENAME
    if os.path.lexists(sig_path):
        try:
            document = json.loads(_read_regular_file(sig_path, 4096).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            _fail("INVALID_SIGNATURE", "bundle signature is not valid JSON")
        if type(document) is not dict or document.get("schema") != BUNDLE_SIGNATURE_SCHEMA:
            _fail("INVALID_SIGNATURE", "bundle signature has the wrong shape")
        key_id = verify_detached(BUNDLE_SIGNATURE_DOMAIN, manifest, document, trusted_keys or {})
        signature = {"key_id": key_id, "algorithm": "ed25519"}
    elif require_bundle_signature:
        _fail("UNSIGNED", "the bundle is not signed")
    files = _read_tree(root, manifest)
    for kind, spec in ITEM_KINDS.items():
        for item in manifest[kind]:
            data = files.get(item["path"])
            if data is None:
                _fail("FILE_MISSING", f"{kind} item {item['name']} has no file at {item['path']}")
            if _sha256(data) != item["digest"]:
                _fail(spec["mismatch"], f"{kind} item {item['name']} does not match its digest")
    found = _resolve_packs(packs, trusted_keys=trusted_keys, require_signature=require_signature,
                           revocations=revocations)
    pinned, modules = _check_packs(manifest["packs"], found)
    items = _check_items(manifest, files, modules | _core_ids(core_module_ids), fill=False)
    return _report(manifest, pinned, items, signature)


def verify_bundle(
    source: os.PathLike[str] | str,
    *,
    packs: Iterable[os.PathLike[str] | str],
    trusted_keys: Optional[Mapping[str, Any]] = None,
    require_signature: bool = True,
    revocations: Any = None,
    require_bundle_signature: bool = False,
    core_module_ids: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Verify a bundle directory or zip against the packs it pins; returns what was verified.

    ``require_signature`` and ``trusted_keys`` apply to each referenced pack
    and to the bundle's own signature; ``require_bundle_signature`` refuses
    an unsigned bundle.
    """
    from .portable import opened_pack

    with opened_pack(source, required=BUNDLE_FILENAME) as root:
        return _verify_dir(root, list(packs), trusted_keys=trusted_keys, require_signature=require_signature,
                           revocations=revocations, require_bundle_signature=require_bundle_signature,
                           core_module_ids=core_module_ids)


def build_bundle(
    source: os.PathLike[str] | str,
    output: os.PathLike[str] | str,
    *,
    packs: Iterable[os.PathLike[str] | str],
    trusted_keys: Optional[Mapping[str, Any]] = None,
    require_signature: bool = True,
    revocations: Any = None,
    private_key: Any = None,
    key_id: Optional[str] = None,
    core_module_ids: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Pin the packs, digest the files, validate, and write the bundle zip ``output``."""
    from .portable import write_deterministic_zip
    from .signature import sign_detached

    root = Path(source)
    out = Path(output)
    packs = list(packs)
    if (private_key is None) != (key_id is None):
        _fail("INVALID_KEY", "signing needs both a key and a key id")
    if os.path.lexists(out):
        _fail("OUTPUT_EXISTS", "the output file exists; a new build is a new version in a new file")
    draft = validate_bundle_manifest(_read_manifest(root), pinned=False)
    files = _read_tree(root, draft)
    found = _resolve_packs(packs, trusted_keys=trusted_keys, require_signature=require_signature,
                           revocations=revocations)
    pinned, modules = _check_packs(draft["packs"], found)
    items = _check_items(draft, files, modules | _core_ids(core_module_ids), fill=True)
    manifest = validate_bundle_manifest({
        "schema": BUNDLE_SCHEMA,
        "bundle": draft["bundle"],
        "packs": pinned,
        **{kind: [{k: v for k, v in item.items() if k != "modules"} for item in items[kind]] for kind in ITEM_KINDS},
    }, pinned=True)
    entries = [(BUNDLE_FILENAME, (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), False)]
    entries += [(item["path"], files[item["path"]], False) for kind in ITEM_KINDS for item in manifest[kind]]
    if private_key is not None:
        signature = {"schema": BUNDLE_SIGNATURE_SCHEMA,
                     **sign_detached(BUNDLE_SIGNATURE_DOMAIN, manifest, private_key, key_id)}
        entries.append((BUNDLE_SIGNATURE_FILENAME, (json.dumps(signature, indent=2) + "\n").encode("utf-8"), False))
    # What is written is verified as a host would verify it, first.
    with tempfile.TemporaryDirectory(prefix="flyto-bundle-build-") as scratch:
        stage = Path(scratch)
        for rel, data, _ in entries:
            target = stage.joinpath(*rel.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        trusted = {key_id: private_key.public_key()} if private_key is not None else None
        report = _verify_dir(stage, list(packs), trusted_keys={**(trusted_keys or {}), **(trusted or {})},
                             require_signature=require_signature, revocations=revocations,
                             require_bundle_signature=private_key is not None, core_module_ids=core_module_ids)
    write_deterministic_zip(entries, out)
    report["zip"] = str(out)
    report["zip_sha256"] = hashlib.sha256(out.read_bytes()).hexdigest()
    return report
