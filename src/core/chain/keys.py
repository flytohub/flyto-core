# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Published chain keys (``flyto.execution-chain-keys.v1``) and the section signature check.

A key document is published by one issuer, the signer its sections name
(``cloud``, ``host:<device id>``)::

    {"schema": "flyto.execution-chain-keys.v1", "issuer": "cloud",
     "keys": [{"key_id", "algorithm", "public_key", "not_before", "not_after",
               "revoked_at", "retained_heads"}, ...],
     "rotations": [{"from_key_id", "to_key_id", "to_public_key", "at", "signature"}, ...]}

* **Trust.** A key no rotation names as its successor is an anchor. A key a
  trusted key rotated to, by a statement the outgoing key signed over
  ``b"flyto.execution-chain-key-rotation.v1\\n" + canonical bytes of
  {from_key_id, to_key_id, to_public_key, at}``, is trusted too. A key
  reached only by a forged or unsigned rotation is not.
* **Window.** A section signed at ``at`` verifies only when ``not_before <=
  at < not_after`` (either bound may be absent).
* **Revocation.** A key with ``revoked_at`` stands only on a record whose
  head its ``retained_heads`` lists: the records it signed before the
  revocation point.

Algorithms are a table (:data:`ALGORITHMS`): ``ed25519`` (a raw 32-byte
public key, what flyto-cloud issues) and ``ecdsa-p256-sha256`` (an X9.62
P-256 point, compressed or not, with a DER signature over SHA-256). A
signature names its algorithm, and it must be its key's.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Set

from .record import canonical_bytes, signing_message

KEYS_SCHEMA = "flyto.execution-chain-keys.v1"
ROTATION_DOMAIN = b"flyto.execution-chain-key-rotation.v1\n"
KEY_ENTRY_KEYS = frozenset({"key_id", "algorithm", "public_key", "not_before", "not_after", "revoked_at",
                            "retained_heads"})


class ChainKeysError(ValueError):
    """A key document that is not one; ``code`` is ``CHAIN_KEYS_INVALID``."""

    code = "CHAIN_KEYS_INVALID"


def _b64(text: Any) -> bytes:
    if not isinstance(text, str):
        raise ValueError("not base64")
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("not base64") from error


def _verify_ed25519(public: bytes, signature: bytes, message: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ed25519

    try:
        ed25519.Ed25519PublicKey.from_public_bytes(public).verify(signature, message)
    except (InvalidSignature, ValueError):
        return False
    return True


def _verify_ecdsa_p256(public: bytes, signature: bytes, message: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec

    try:
        key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)
        key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError):
        return False
    return True


@dataclass(frozen=True)
class Algorithm:
    name: str
    #: Accepted public key lengths, in bytes.
    public_key_lengths: frozenset
    verify: Callable[[bytes, bytes, bytes], bool]


ALGORITHMS: Dict[str, Algorithm] = {
    algorithm.name: algorithm
    for algorithm in (
        Algorithm("ed25519", frozenset({32}), _verify_ed25519),
        Algorithm("ecdsa-p256-sha256", frozenset({33, 65}), _verify_ecdsa_p256),
    )
}


def _moment(value: Any) -> Optional[datetime]:
    """An ISO instant as an aware time; None when absent; ``ValueError`` when it is not one."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("not an instant")
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _entry_problem(entry: Any) -> str:
    if not isinstance(entry, Mapping) or set(entry) != KEY_ENTRY_KEYS:
        return "a key entry has the wrong shape"
    algorithm = ALGORITHMS.get(entry.get("algorithm"))
    if algorithm is None:
        return f"key {entry.get('key_id')!r} uses an algorithm this verifier does not know"
    try:
        public = _b64(entry["public_key"])
        for bound in ("not_before", "not_after", "revoked_at"):
            _moment(entry[bound])
    except ValueError:
        return f"key {entry.get('key_id')!r} has an unreadable public key or instant"
    if len(public) not in algorithm.public_key_lengths:
        return f"key {entry.get('key_id')!r} is not a {algorithm.name} public key"
    if not isinstance(entry["retained_heads"], list):
        return f"key {entry.get('key_id')!r} retained_heads is not a list"
    return ""


def load_key_document(raw: Any) -> Dict[str, Any]:
    """A key document as published, checked for shape; raises :class:`ChainKeysError`."""
    if not isinstance(raw, Mapping) or raw.get("schema") != KEYS_SCHEMA:
        raise ChainKeysError(f"not a {KEYS_SCHEMA} document")
    keys, rotations = raw.get("keys"), raw.get("rotations", [])
    if not isinstance(keys, list) or not isinstance(rotations, list):
        raise ChainKeysError("a key document lists its keys and rotations")
    for entry in keys:
        problem = _entry_problem(entry)
        if problem:
            raise ChainKeysError(problem)
    if len({entry["key_id"] for entry in keys}) != len(keys):
        raise ChainKeysError("a key id is listed twice")
    return {"schema": KEYS_SCHEMA, "issuer": str(raw.get("issuer") or ""),
            "keys": [dict(entry) for entry in keys],
            "rotations": [dict(item) for item in rotations if isinstance(item, Mapping)]}


def _signed_by(entry: Mapping[str, Any], signature_b64: Any, message: bytes) -> bool:
    try:
        public, signature = _b64(entry["public_key"]), _b64(signature_b64)
    except ValueError:
        return False
    return ALGORITHMS[entry["algorithm"]].verify(public, signature, message)


def endorsed_keys(document: Mapping[str, Any]) -> Set[str]:
    """The key ids a verifier accepts: the anchors and every key a trusted key rotated to."""
    entries = {entry["key_id"]: entry for entry in document.get("keys") or ()}
    rotations = list(document.get("rotations") or ())
    successors = {rotation.get("to_key_id") for rotation in rotations}
    trusted = {key_id for key_id in entries if key_id not in successors}
    grew = True
    while grew:
        grew = False
        for rotation in rotations:
            source, target = rotation.get("from_key_id"), rotation.get("to_key_id")
            if source not in trusted or target in trusted or target not in entries:
                continue
            if rotation.get("to_public_key") != entries[target]["public_key"]:
                continue
            body = {"from_key_id": source, "to_key_id": target,
                    "to_public_key": entries[target]["public_key"], "at": str(rotation.get("at") or "")}
            if _signed_by(entries[source], rotation.get("signature"), ROTATION_DOMAIN + canonical_bytes(body)):
                trusted.add(target)
                grew = True
    return trusted


def _window_problem(section: Mapping[str, Any], entry: Mapping[str, Any]) -> str:
    try:
        at = _moment(section.get("at"))
        start, end = _moment(entry.get("not_before")), _moment(entry.get("not_after"))
    except ValueError:
        return "CHAIN_RECORD_KEY_OUT_OF_WINDOW"
    if at is None or (start is not None and at < start) or (end is not None and at >= end):
        return "CHAIN_RECORD_KEY_OUT_OF_WINDOW"
    return ""


def verify_section(section: Mapping[str, Any], document: Mapping[str, Any], *, record_head: str,
                   trusted: Optional[Set[str]] = None) -> str:
    """Why ``section``'s signature cannot be accepted under ``document``; ``""`` when it verifies.

    ``document`` must already be loaded (:func:`load_key_document`).
    ``trusted`` defaults to :func:`endorsed_keys` of the document.
    """
    signature = section.get("signature")
    if not isinstance(signature, Mapping):
        return "CHAIN_RECORD_UNSIGNED"
    entry = next((item for item in document.get("keys") or () if item.get("key_id") == signature.get("key_id")),
                 None)
    if entry is None or entry["key_id"] not in (endorsed_keys(document) if trusted is None else trusted):
        return "CHAIN_RECORD_UNTRUSTED_KEY"
    if signature.get("algorithm") != entry["algorithm"]:
        return "CHAIN_RECORD_SIGNATURE_INVALID"
    window = _window_problem(section, entry)
    if window:
        return window
    if entry.get("revoked_at") and record_head not in set(entry.get("retained_heads") or ()):
        return "CHAIN_RECORD_KEY_REVOKED"
    if not _signed_by(entry, signature.get("signature"), signing_message(section)):
        return "CHAIN_RECORD_SIGNATURE_INVALID"
    return ""


def documents_by_signer(documents: Iterable[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Loaded key documents keyed by issuer; raises :class:`ChainKeysError` on a clash or no issuer."""
    found: Dict[str, Dict[str, Any]] = {}
    for raw in documents:
        document = load_key_document(raw)
        issuer = document["issuer"]
        if not issuer:
            raise ChainKeysError("a key document names no issuer")
        if issuer in found and found[issuer] != document:
            raise ChainKeysError(f"two different key documents are given for {issuer!r}")
        found[issuer] = document
    return found


__all__ = [
    "ALGORITHMS", "Algorithm", "ChainKeysError", "KEYS_SCHEMA", "KEY_ENTRY_KEYS", "ROTATION_DOMAIN",
    "documents_by_signer", "endorsed_keys", "load_key_document", "verify_section",
]
