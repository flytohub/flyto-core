# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Language-neutral module packs — ``flyto.pack.v1``.

* ``manifest`` — the manifest schema, its validator and the pack tree digest.
* ``signature`` — ed25519 publisher signatures, verified offline.
* ``host`` — install an out-of-process pack into ``ModuleRegistry``.
* ``export`` — print the manifest a Python pack's decorators produce.

See ``docs/CAPABILITY_CONTRACT.md`` ("Other languages") and
``docs/specs/PACK_MANIFEST_SPEC.md``.
"""

from .manifest import (
    MANIFEST_FILENAME,
    PACK_SCHEMA,
    SIGNATURE_FILENAME,
    PackManifestError,
    canonical_bytes,
    manifest_sha256,
    pack_tree_digest,
    read_pack_manifest,
    validate_pack_manifest,
)

__all__ = [
    "MANIFEST_FILENAME",
    "PACK_SCHEMA",
    "SIGNATURE_FILENAME",
    "PackManifestError",
    "canonical_bytes",
    "manifest_sha256",
    "pack_tree_digest",
    "read_pack_manifest",
    "validate_pack_manifest",
]
