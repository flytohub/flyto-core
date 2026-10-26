# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The execution chain's offline verifier (``flyto chain verify``).

* :mod:`core.chain.record` -- the ``flyto.execution-chain.v1`` format, its
  canonical bytes, digests, signing message and link rules;
* :mod:`core.chain.keys` -- published ``flyto.execution-chain-keys.v1``
  documents: algorithms, rotation, validity windows, revocation;
* :mod:`core.chain.verify` -- one record checked against those keys, with
  exit codes 0 verified, 1 refused, 2 incomplete.

Nothing here reaches a network or trusts the record's issuer for anything
the caller did not pass in.
"""

from .keys import (
    ALGORITHMS,
    KEYS_SCHEMA,
    ChainKeysError,
    endorsed_keys,
    load_key_document,
    verify_section,
)
from .record import (
    GENESIS,
    SCHEMA,
    STAGES,
    canonical_bytes,
    digest_of,
    link_problems,
    section_digest,
    signing_message,
)
from .verify import (
    EXIT_INCOMPLETE,
    EXIT_REFUSED,
    EXIT_VERIFIED,
    EXPORT_SCHEMA,
    TRUST_MODES,
    key_documents_from,
    record_from,
    verify_record,
)

__all__ = [
    "ALGORITHMS", "ChainKeysError", "EXIT_INCOMPLETE", "EXIT_REFUSED", "EXIT_VERIFIED", "EXPORT_SCHEMA",
    "GENESIS", "KEYS_SCHEMA", "SCHEMA", "STAGES", "TRUST_MODES", "canonical_bytes", "digest_of",
    "endorsed_keys", "key_documents_from", "link_problems", "load_key_document", "record_from",
    "section_digest", "signing_message", "verify_record", "verify_section",
]
