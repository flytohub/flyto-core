# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Supply chain for portable packs: the pack digest, the hashed lockfile, the revocation list.

**Pack digest.** ``sha256:<hex>`` of the normalized manifest's canonical
bytes — the value :func:`core.pack.manifest.manifest_sha256` already
computes. The manifest carries ``artifact.digest`` (every other file of the
pack), so this one value names the whole pack: what it says and what it
ships. A bundle pins it; a revocation list names it. A new version of a pack
is a new manifest and so a new digest: nothing is ever updated in place.

**Lockfile.** The runtime a standalone pack installs, in pip's hash-checking
requirements format (``name==version --hash=sha256:<hex>``, installed with
``pip install --require-hashes``). Every requirement is pinned to one
version and carries at least one SHA-256; anything pip would resolve, fetch
from a URL or edit in place is refused.

**Revocation list** (``flyto.pack-revocations.v1``)::

    {"schema": "flyto.pack-revocations.v1",
     "list": {"sequence": 3, "issued_at": "2026-10-19T00:00:00Z",
              "revoked": [{"digest": "sha256:<hex>", "reason": "key_compromise"}]},
     "signature": {"algorithm": "ed25519", "key_id": "...", "signature": "<base64>"}}

signed over ``b"flyto.pack-revocations.v1\\n" + canonical_bytes(list)`` with
the same ed25519 step as a pack signature. A loader that is given a list
verifies it first — a list that does not verify refuses the start, since it
can no longer say the pack is not revoked — then refuses a pack whose digest
it names with ``PACK_REVOKED``, before any of the pack runs.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

from .manifest import PackManifestError, _read_regular_file, manifest_sha256
from .signature import sign_detached, verify_detached

__all__ = [
    "LOCKFILE_FORMAT",
    "REVOCATIONS_SCHEMA",
    "REVOCATION_REASONS",
    "RevocationList",
    "pack_digest",
    "parse_lockfile",
    "sign_revocations",
    "load_revocations",
    "read_revocations",
]

LOCKFILE_FORMAT = "pip-require-hashes"
REVOCATIONS_SCHEMA = "flyto.pack-revocations.v1"
REVOCATIONS_DOMAIN = b"flyto.pack-revocations.v1\n"
#: Why a digest is revoked. A closed vocabulary, so a loader can say why it refused.
REVOCATION_REASONS = ("key_compromise", "malicious", "vulnerable", "withdrawn", "superseded")

MAX_LOCKFILE_BYTES = 1024 * 1024
MAX_LOCK_REQUIREMENTS = 512
MAX_REVOCATIONS = 100_000
MAX_REVOCATION_FILE = 32 * 1024 * 1024

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
#: ``name[extras]==version [; marker] --hash=sha256:<hex> ...`` and nothing else.
_REQUIREMENT = re.compile(
    r"^(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)(?:\[[A-Za-z0-9._,-]+\])?"
    r"==(?P<version>[A-Za-z0-9.+!_-]+)"
    r"(?:\s*;\s*(?P<marker>[^-][^;]*?))?"
    r"(?P<hashes>(?:\s+--hash=sha256:[0-9a-f]{64})+)\s*$"
)


def _fail(code: str, message: str) -> None:
    raise PackManifestError(code, message)


def pack_digest(manifest: Mapping[str, Any]) -> str:
    """``sha256:<hex>`` naming one normalized manifest, and through ``artifact.digest`` its files."""
    return "sha256:" + manifest_sha256(manifest)


# ---------------------------------------------------------------------------
# Lockfile
# ---------------------------------------------------------------------------


def _canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _version_key(text: str) -> Tuple[int, ...]:
    core = text.split("+", 1)[0].split("-", 1)[0]
    parts = []
    for part in core.split("."):
        digits = re.match(r"\d+", part)
        parts.append(int(digits.group(0)) if digits else 0)
    return tuple(parts)


def parse_lockfile(text: str, *, runtime_package: str, min_version: Optional[str]) -> List[Dict[str, Any]]:
    """The pinned, hashed requirements of a lockfile, or a typed refusal.

    ``runtime_package`` must be among them, at ``min_version`` or later.
    """
    if type(text) is not str or len(text.encode("utf-8")) > MAX_LOCKFILE_BYTES:
        _fail("LOCKFILE_INVALID", "the lockfile is not bounded UTF-8 text")
    logical: List[str] = []
    pending = ""
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        line = (pending + line).strip()
        pending = ""
        if line:
            logical.append(line)
    if pending.strip():
        _fail("LOCKFILE_INVALID", "the lockfile ends inside a continued line")
    if len(logical) > MAX_LOCK_REQUIREMENTS:
        _fail("LOCKFILE_INVALID", "the lockfile has too many requirements")
    requirements: List[Dict[str, Any]] = []
    seen = set()
    for line in logical:
        match = _REQUIREMENT.match(line)
        if match is None:
            # An option (-e, -r, --index-url), a URL, a range or a requirement
            # without a SHA-256 is something pip would resolve, not a pin.
            _fail("LOCKFILE_INVALID", "every lockfile line must be name==version with --hash=sha256 hashes")
        name = _canonical_name(match.group("name"))
        if name in seen:
            _fail("LOCKFILE_INVALID", "the lockfile pins one package twice")
        seen.add(name)
        hashes = sorted(set(re.findall(r"sha256:[0-9a-f]{64}", match.group("hashes"))))
        entry: Dict[str, Any] = {"name": name, "version": match.group("version"), "hashes": hashes}
        if match.group("marker"):
            entry["marker"] = match.group("marker").strip()
        requirements.append(entry)
    runtime = next((item for item in requirements if item["name"] == _canonical_name(runtime_package)), None)
    if runtime is None:
        _fail("LOCKFILE_RUNTIME_MISSING", f"the lockfile does not pin the runtime package {runtime_package}")
    if min_version and _version_key(runtime["version"]) < _version_key(min_version):
        _fail("LOCKFILE_RUNTIME_TOO_OLD", "the lockfile pins a runtime older than the pack's min_host")
    return sorted(requirements, key=lambda item: item["name"])


# ---------------------------------------------------------------------------
# Revocation list
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RevocationList:
    """A verified revocation list."""

    key_id: str
    sequence: int
    issued_at: str
    revoked: Mapping[str, str]

    @property
    def digests(self) -> FrozenSet[str]:
        return frozenset(self.revoked)

    def is_revoked(self, digest: str) -> bool:
        return digest in self.revoked

    def check(self, manifest: Mapping[str, Any]) -> None:
        """Refuse a pack this list revokes; return quietly otherwise."""
        digest = pack_digest(manifest)
        if digest in self.revoked:
            raise PackManifestError(
                "PACK_REVOKED", f"pack {manifest['pack']['id']} {manifest['pack']['version']} is revoked "
                f"({self.revoked[digest]})"
            )


def _revocation_body(sequence: Any, issued_at: Any, revoked: Any) -> Dict[str, Any]:
    if type(sequence) is not int or not 0 <= sequence <= 2**53:
        _fail("REVOCATION_INVALID", "revocation list sequence must be a non-negative integer")
    if type(issued_at) is not str or not _TIMESTAMP.fullmatch(issued_at):
        _fail("REVOCATION_INVALID", "revocation list issued_at must be a UTC timestamp")
    if type(revoked) is not list or len(revoked) > MAX_REVOCATIONS:
        _fail("REVOCATION_INVALID", "revocation list entries must be a bounded list")
    entries = []
    seen = set()
    for item in revoked:
        if type(item) is not dict or set(item) != {"digest", "reason"}:
            _fail("REVOCATION_INVALID", "a revocation entry is {digest, reason}")
        if type(item["digest"]) is not str or not _DIGEST.fullmatch(item["digest"]):
            _fail("REVOCATION_INVALID", "a revocation digest must be sha256:<hex>")
        if item["reason"] not in REVOCATION_REASONS:
            _fail("REVOCATION_INVALID", f"a revocation reason is one of {', '.join(REVOCATION_REASONS)}")
        if item["digest"] in seen:
            _fail("REVOCATION_INVALID", "a digest is revoked twice")
        seen.add(item["digest"])
        entries.append({"digest": item["digest"], "reason": item["reason"]})
    return {"sequence": sequence, "issued_at": issued_at, "revoked": sorted(entries, key=lambda e: e["digest"])}


def sign_revocations(revoked: List[Mapping[str, Any]], private_key: Any, key_id: str, *, sequence: int,
                     issued_at: str) -> Dict[str, Any]:
    """A signed ``flyto.pack-revocations.v1`` document."""
    body = _revocation_body(sequence, issued_at, [dict(item) for item in revoked])
    return {"schema": REVOCATIONS_SCHEMA, "list": body,
            "signature": sign_detached(REVOCATIONS_DOMAIN, body, private_key, key_id)}


def load_revocations(document: Any, trusted_keys: Mapping[str, Any]) -> RevocationList:
    """Verify a revocation document against ``trusted_keys``; refuse anything else."""
    if type(document) is not dict or set(document) != {"schema", "list", "signature"}:
        _fail("REVOCATION_INVALID", "revocation document has the wrong shape")
    if document["schema"] != REVOCATIONS_SCHEMA:
        _fail("REVOCATION_INVALID", f"schema must be {REVOCATIONS_SCHEMA}")
    body = document["list"]
    if type(body) is not dict or set(body) != {"sequence", "issued_at", "revoked"}:
        _fail("REVOCATION_INVALID", "revocation list has the wrong shape")
    normalized = _revocation_body(body["sequence"], body["issued_at"], body["revoked"])
    signature = document["signature"]
    if type(signature) is not dict or set(signature) != {"algorithm", "key_id", "signature"}:
        _fail("REVOCATION_INVALID", "revocation signature has the wrong shape")
    try:
        key_id = verify_detached(REVOCATIONS_DOMAIN, body, signature, trusted_keys)
    except PackManifestError as exc:
        code = {"UNTRUSTED_KEY": "REVOCATION_UNTRUSTED_KEY", "SIGNATURE_MISMATCH": "REVOCATION_SIGNATURE_MISMATCH"}
        raise PackManifestError(code.get(exc.code, "REVOCATION_INVALID"), f"revocation list: {exc}") from None
    return RevocationList(
        key_id=key_id,
        sequence=normalized["sequence"],
        issued_at=normalized["issued_at"],
        revoked={entry["digest"]: entry["reason"] for entry in normalized["revoked"]},
    )


def read_revocations(path: os.PathLike[str] | str, trusted_keys: Mapping[str, Any]) -> RevocationList:
    """Read and verify a revocation list file."""
    try:
        raw = _read_regular_file(Path(path), MAX_REVOCATION_FILE)
        document = json.loads(raw.decode("utf-8"))
    except PackManifestError:
        _fail("REVOCATION_INVALID", "the revocation list is missing or not a bounded regular file")
    except (UnicodeDecodeError, ValueError):
        _fail("REVOCATION_INVALID", "the revocation list is not valid UTF-8 JSON")
    return load_revocations(document, trusted_keys)
