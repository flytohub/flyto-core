# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Publisher key rotation (``flyto.publisher-key-rotation.v1``) and the verification of a pack's publisher.

A pack is maintained by its publisher for years; the key that signs it is not
forever. A rotation statement is signed by the old key and names the new
one::

    {"schema": "flyto.publisher-key-rotation.v1",
     "rotation": {"from_key_id": "publisher-1", "to_key_id": "publisher-2",
                  "to_public_key": "<base64 of the 32 raw bytes>",
                  "issued_at": "2026-10-19T00:00:00Z"},
     "signature": {"algorithm": "ed25519", "key_id": "publisher-1", "signature": "<base64>"}}

signed over ``b"flyto.publisher-key-rotation.v1\\n" + canonical_bytes(rotation)``
with the one ed25519 step every signed document uses
(:func:`core.pack.signature.sign_detached`).

A host still trusts only the keys it was given. :func:`resolve_publisher_keys`
follows the statements from those keys, one hop at a time, to at most
:data:`MAX_ROTATION_CHAIN` hops. Every statement supplied must connect:
one whose old key is not reached, whose signature does not verify, or that
binds a key id already bound to another key refuses the whole set
(``KEY_ROTATION_BROKEN``); a longer chain is ``KEY_ROTATION_TOO_LONG``. A
statement signed by a revoked key after its revocation point (not among the
key's ``retained`` digests, ``core.pack.supply_chain``) is
``PUBLISHER_KEY_REVOKED``. The old key stays trusted for what it signed
before; retiring it is a revocation, not a rotation.

:func:`verify_publisher` is the one publisher check a host makes: the signer
against the revocation list, then the rotation chain, then the signature.
``install_pack`` and ``verify_pack_dir`` both call it.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from typing import Any, Dict, Mapping, Optional, Sequence

from .manifest import PackManifestError, canonical_bytes
from .signature import _KEY_ID, load_public_key, load_trusted_keys, sign_detached, verify_detached

__all__ = [
    "MAX_ROTATION_CHAIN",
    "ROTATION_SCHEMA",
    "resolve_publisher_keys",
    "rotation_digest",
    "sign_key_rotation",
    "verify_publisher",
]

ROTATION_SCHEMA = "flyto.publisher-key-rotation.v1"
ROTATION_DOMAIN = b"flyto.publisher-key-rotation.v1\n"
#: The most hops a host follows from a key it trusts.
MAX_ROTATION_CHAIN = 8
#: The most statements one verification reads.
MAX_ROTATIONS = 64
_ROTATION_KEYS = frozenset({"from_key_id", "to_key_id", "to_public_key", "issued_at"})
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _fail(code: str, message: str) -> None:
    raise PackManifestError(code, message)


def _raw_public(key: Any) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return load_public_key(key).public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def sign_key_rotation(old_private_key: Any, old_key_id: str, new_public_key: Any, new_key_id: str, *,
                      issued_at: str) -> Dict[str, Any]:
    """A rotation statement from ``old_key_id`` to ``new_key_id``, signed by the old key."""
    body = {"from_key_id": old_key_id, "to_key_id": new_key_id,
            "to_public_key": base64.b64encode(_raw_public(new_public_key)).decode("ascii"), "issued_at": issued_at}
    _rotation_body(body)
    return {"schema": ROTATION_SCHEMA, "rotation": body,
            "signature": sign_detached(ROTATION_DOMAIN, body, old_private_key, old_key_id)}


def rotation_digest(statement: Mapping[str, Any]) -> str:
    """``sha256:<hex>`` naming one statement, as a key revocation's ``retained`` list names it."""
    body = statement.get("rotation") if isinstance(statement, Mapping) else None
    return "sha256:" + hashlib.sha256(ROTATION_DOMAIN + canonical_bytes(body)).hexdigest()


def _rotation_body(body: Any) -> Dict[str, Any]:
    if type(body) is not dict or set(body) != _ROTATION_KEYS:
        _fail("KEY_ROTATION_INVALID", "a rotation is {from_key_id, to_key_id, to_public_key, issued_at}")
    for name in ("from_key_id", "to_key_id"):
        if type(body[name]) is not str or not _KEY_ID.fullmatch(body[name]):
            _fail("KEY_ROTATION_INVALID", f"rotation {name} is not a key id")
    if type(body["issued_at"]) is not str or not _TIMESTAMP.fullmatch(body["issued_at"]):
        _fail("KEY_ROTATION_INVALID", "rotation issued_at must be a UTC timestamp")
    try:
        raw = base64.b64decode(body["to_public_key"], validate=True)
    except (binascii.Error, ValueError, TypeError):
        _fail("KEY_ROTATION_INVALID", "rotation to_public_key is not base64")
    if len(raw) != 32:
        _fail("KEY_ROTATION_INVALID", "rotation to_public_key is not a 32-byte ed25519 key")
    return body


def _statement(document: Any) -> Dict[str, Any]:
    if type(document) is not dict or set(document) != {"schema", "rotation", "signature"}:
        _fail("KEY_ROTATION_INVALID", "a rotation statement is {schema, rotation, signature}")
    if document["schema"] != ROTATION_SCHEMA:
        _fail("KEY_ROTATION_INVALID", f"schema must be {ROTATION_SCHEMA}")
    body = _rotation_body(document["rotation"])
    signature = document["signature"]
    if type(signature) is not dict or set(signature) != {"algorithm", "key_id", "signature"}:
        _fail("KEY_ROTATION_INVALID", "rotation signature has the wrong shape")
    if signature["key_id"] != body["from_key_id"]:
        _fail("KEY_ROTATION_BROKEN", "a rotation is signed by the key it rotates from")
    return body


def resolve_publisher_keys(trusted_keys: Mapping[str, Any], rotations: Sequence[Any] = (), *,
                           revocations: Any = None) -> Dict[str, Any]:
    """The trusted keys plus every key a valid chain of rotation statements reaches from them."""
    known: Dict[str, Any] = dict(load_trusted_keys(trusted_keys)) if trusted_keys else {}
    if not rotations:
        return known
    if not isinstance(rotations, (list, tuple)) or len(rotations) > MAX_ROTATIONS:
        _fail("KEY_ROTATION_INVALID", f"at most {MAX_ROTATIONS} rotation statements")
    pending = [(document, _statement(document)) for document in rotations]
    depth = dict.fromkeys(known, 0)
    while pending:
        ready = [item for item in pending if item[1]["from_key_id"] in known]
        if not ready:
            _fail("KEY_ROTATION_BROKEN", f"no trusted key reaches {pending[0][1]['from_key_id']}")
        for document, body in ready:
            pending.remove((document, body))
            _follow(document, body, known, depth, revocations)
    return known


def _follow(document: Mapping[str, Any], body: Mapping[str, Any], known: Dict[str, Any], depth: Dict[str, int],
            revocations: Any) -> None:
    old, new = body["from_key_id"], body["to_key_id"]
    if revocations is not None and revocations.signed_after_revocation(old, rotation_digest(document)) is not None:
        _fail("PUBLISHER_KEY_REVOKED", f"key {old} is revoked; it rotated to {new} after its revocation point")
    try:
        verify_detached(ROTATION_DOMAIN, body, document["signature"], {old: known[old]})
    except PackManifestError:
        _fail("KEY_ROTATION_BROKEN", f"the rotation from {old} to {new} is not signed by {old}")
    new_key = load_public_key(body["to_public_key"])
    if new in known and _raw_public(known[new]) != _raw_public(new_key):
        _fail("KEY_ROTATION_BROKEN", f"the rotation binds {new}, a key id already bound to another key")
    hops = depth[old] + 1
    if hops > MAX_ROTATION_CHAIN:
        _fail("KEY_ROTATION_TOO_LONG", f"the chain to {new} is longer than {MAX_ROTATION_CHAIN} rotations")
    known.setdefault(new, new_key)
    depth[new] = min(depth.get(new, hops), hops)


def verify_publisher(manifest: Mapping[str, Any], signature_doc: Optional[Mapping[str, Any]], *,
                     trusted_keys: Optional[Mapping[str, Any]], require_signature: bool, revocations: Any = None,
                     key_rotations: Sequence[Any] = ()) -> Optional[Dict[str, str]]:
    """The verified signature of ``manifest`` (``None`` for an accepted unsigned pack), or a typed refusal."""
    from .signature import verify_manifest_signature

    if revocations is not None:
        signer = signature_doc.get("key_id") if isinstance(signature_doc, Mapping) else None
        revocations.check_signer(manifest, (signer, manifest["pack"].get("publisher_key_id")))
    if signature_doc is None:
        if require_signature:
            _fail("UNSIGNED", "pack is not signed and the host requires a signature")
        return None
    keys = resolve_publisher_keys(trusted_keys or {}, list(key_rotations or ()), revocations=revocations)
    verified = verify_manifest_signature(manifest, signature_doc, keys)
    if verified["key_id"] not in (trusted_keys or {}):
        verified = {**verified, "via_rotation": "true"}
    return verified

