# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Publisher signatures for ``flyto.pack.v1`` — ed25519, offline.

A signature binds a publisher key to one normalized manifest. The manifest
carries ``artifact.digest`` (the tree digest of every file the pack ships), so
one signature covers both what the pack *says* and the code that *runs*; a
signed manifest without an artifact digest is refused, because it would attest
to a map rather than to a pack.

The signed message is::

    b"flyto.pack-signature.v1\\n" + canonical_bytes(normalized_manifest)

and the detached signature file ``flyto-pack.sig.json`` is::

    {"schema": "flyto.pack-signature.v1", "algorithm": "ed25519",
     "key_id": "...", "manifest_sha256": "<hex>", "signature": "<base64>"}

Verification never touches the network. The host supplies the trusted key set
(``{key_id: public key}``); an unknown key id is a refusal, not a warning.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .manifest import (
    SIGNATURE_FILENAME,
    PackManifestError,
    _read_regular_file,
    canonical_bytes,
    manifest_sha256,
)

__all__ = [
    "SIGNATURE_SCHEMA",
    "SIGNATURE_DOMAIN",
    "load_public_key",
    "load_trusted_keys",
    "sign_manifest",
    "verify_manifest_signature",
    "read_signature",
]

SIGNATURE_SCHEMA = "flyto.pack-signature.v1"
SIGNATURE_DOMAIN = b"flyto.pack-signature.v1\n"
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SIGNATURE_KEYS = frozenset({"schema", "algorithm", "key_id", "manifest_sha256", "signature"})
_MAX_SIGNATURE_FILE = 4096
_MAX_TRUSTED_KEYS = 64


def _fail(code: str, message: str) -> None:
    raise PackManifestError(code, message)


def _ed25519():
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError:  # pragma: no cover - exercised only without the extra
        _fail(
            "SIGNATURE_UNAVAILABLE",
            "ed25519 verification needs the 'cryptography' package (pip install 'flyto-core[crypto]')",
        )
    return ed25519


def _message(manifest: Mapping[str, Any]) -> bytes:
    return SIGNATURE_DOMAIN + canonical_bytes(manifest)


def load_public_key(value: Any):
    """An ``Ed25519PublicKey`` from raw 32 bytes, base64 of them, PEM, or a key object."""
    ed25519 = _ed25519()
    if isinstance(value, ed25519.Ed25519PublicKey):
        return value
    raw: Optional[bytes] = None
    if isinstance(value, (bytes, bytearray)) and len(value) == 32:
        raw = bytes(value)
    elif isinstance(value, (str, bytes, bytearray)):
        text = value.decode("ascii", "replace") if not isinstance(value, str) else value
        text = text.strip()
        if text.startswith("-----BEGIN"):
            from cryptography.hazmat.primitives import serialization

            try:
                key = serialization.load_pem_public_key(text.encode("ascii"))
            except (ValueError, TypeError):
                _fail("INVALID_KEY", "trusted key is not a readable public key")
            if not isinstance(key, ed25519.Ed25519PublicKey):
                _fail("INVALID_KEY", "trusted key is not an ed25519 public key")
            return key
        try:
            raw = base64.b64decode(text, validate=True)
        except (binascii.Error, ValueError):
            _fail("INVALID_KEY", "trusted key is not base64 or PEM")
    if raw is None or len(raw) != 32:
        _fail("INVALID_KEY", "trusted key must be a 32-byte ed25519 public key")
    return ed25519.Ed25519PublicKey.from_public_bytes(raw)


def load_trusted_keys(keys: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate a host-supplied ``{key_id: public key}`` mapping."""
    if not isinstance(keys, Mapping) or len(keys) > _MAX_TRUSTED_KEYS:
        _fail("INVALID_KEY", "trusted keys must be a bounded mapping of key id to public key")
    loaded = {}
    for key_id, value in keys.items():
        if type(key_id) is not str or not _KEY_ID.fullmatch(key_id):
            _fail("INVALID_KEY", "trusted key id is invalid")
        loaded[key_id] = load_public_key(value)
    return loaded


def sign_manifest(manifest: Mapping[str, Any], private_key: Any, key_id: str) -> Dict[str, Any]:
    """Return the signature document for a *normalized* manifest."""
    ed25519 = _ed25519()
    if not isinstance(private_key, ed25519.Ed25519PrivateKey):
        _fail("INVALID_KEY", "signing key must be an ed25519 private key")
    if type(key_id) is not str or not _KEY_ID.fullmatch(key_id):
        _fail("INVALID_KEY", "key id is invalid")
    if "artifact" not in manifest:
        _fail("UNSIGNABLE", "a signed manifest must carry artifact.digest")
    publisher = (manifest.get("pack") or {}).get("publisher_key_id")
    if publisher is not None and publisher != key_id:
        _fail("KEY_MISMATCH", "key id differs from pack.publisher_key_id")
    signature = private_key.sign(_message(manifest))
    return {
        "schema": SIGNATURE_SCHEMA,
        "algorithm": "ed25519",
        "key_id": key_id,
        "manifest_sha256": manifest_sha256(manifest),
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def read_signature(pack_dir: os.PathLike[str] | str) -> Optional[Dict[str, Any]]:
    """The pack's detached signature document, or ``None`` when it has none."""
    path = Path(pack_dir) / SIGNATURE_FILENAME
    if not os.path.lexists(path):
        return None
    raw = _read_regular_file(path, _MAX_SIGNATURE_FILE)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        _fail("INVALID_SIGNATURE", "signature file is not valid JSON")
    return data


def verify_manifest_signature(
    manifest: Mapping[str, Any],
    signature: Any,
    trusted_keys: Mapping[str, Any],
) -> Dict[str, str]:
    """Verify ``signature`` over ``manifest`` against ``trusted_keys``.

    Returns ``{"key_id", "algorithm", "manifest_sha256"}`` on success; raises
    ``PackManifestError`` on any failure. ``trusted_keys`` must already be
    loaded (see :func:`load_trusted_keys`) or be loadable by it.
    """
    _ed25519()
    from cryptography.exceptions import InvalidSignature

    if type(signature) is not dict or set(signature) != _SIGNATURE_KEYS:
        _fail("INVALID_SIGNATURE", "signature document has the wrong shape")
    if signature["schema"] != SIGNATURE_SCHEMA or signature["algorithm"] != "ed25519":
        _fail("INVALID_SIGNATURE", "signature schema or algorithm is not supported")
    key_id = signature["key_id"]
    if type(key_id) is not str or not _KEY_ID.fullmatch(key_id):
        _fail("INVALID_SIGNATURE", "signature key id is invalid")
    if "artifact" not in manifest:
        _fail("UNSIGNABLE", "a signed manifest must carry artifact.digest")
    publisher = (manifest.get("pack") or {}).get("publisher_key_id")
    if publisher is not None and publisher != key_id:
        _fail("KEY_MISMATCH", "signature key differs from pack.publisher_key_id")
    keys = load_trusted_keys(trusted_keys)
    if key_id not in keys:
        _fail("UNTRUSTED_KEY", "the signing key is not in the host's trusted key set")
    expected = manifest_sha256(manifest)
    if signature["manifest_sha256"] != expected:
        _fail("SIGNATURE_MISMATCH", "signature was made over a different manifest")
    try:
        raw = base64.b64decode(signature["signature"], validate=True)
    except (binascii.Error, ValueError, TypeError):
        _fail("INVALID_SIGNATURE", "signature is not base64")
    try:
        keys[key_id].verify(raw, _message(manifest))
    except InvalidSignature:
        _fail("SIGNATURE_MISMATCH", "signature does not verify against the trusted key")
    return {"key_id": key_id, "algorithm": "ed25519", "manifest_sha256": expected}
