# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""``flyto.execution-chain.v1``: the record format, its canonical bytes and its links.

One call leaves one record. Each stage of the chain appends one *section*,
and every section names the digest of the section before it in ``prev``,
so a change to any section breaks every later link. The record's ``head``
is the digest of its last section::

    {"schema": "flyto.execution-chain.v1", "call_id": "c_<id>",
     "sections": [<section>, ...], "head": "sha256:<digest of the last section>"}

A section has a closed key set (``schema, call_id, stage, seq, prev, at,
signer, body``) plus its attestation: ``signature`` (``{algorithm, key_id,
signature}``) or the typed marker ``"unsigned": "no_signer"``.

* Canonical bytes are :func:`core.pack.manifest.canonical_bytes` (sorted
  keys, no whitespace, UTF-8, no NaN). This module re-exports that one
  function; it never has a second implementation.
* A section's digest is ``"sha256:" + sha256(canonical bytes of the section
  without its attestation)``.
* A signature is made over ``b"flyto.execution-chain.v1\\n" + stage + b"\\n"
  + the same canonical bytes``, so one stage's signature can never be
  replayed as another's.
* ``seq`` is the 1-based position. Stages only move forward: a stage may be
  skipped, never repeated or reordered.

These rules are flyto-cloud's ``services/execution_chain/record.py``, the
issuer's side of the same format; the golden record in this package's tests
is produced by that code.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..pack.manifest import canonical_bytes

SCHEMA = "flyto.execution-chain.v1"
DIGEST_PREFIX = "sha256:"
#: The ``prev`` of a record's first section.
GENESIS = DIGEST_PREFIX + "0" * 64
#: What every section signature's message starts with, before the stage name.
SIGNATURE_DOMAIN = SCHEMA.encode("utf-8") + b"\n"
#: The typed marker a section carries instead of a signature nobody made.
UNSIGNED_NO_SIGNER = "no_signer"

SIGNER_CLOUD = "cloud"
SIGNER_HOST = "host"
HOST_SIGNER_PREFIX = "host:"

#: Where a section's attestation lives; neither is part of its digest.
ATTESTATION_KEYS = ("signature", "unsigned")
SECTION_KEYS = frozenset({"schema", "call_id", "stage", "seq", "prev", "at", "signer", "body"})
RECORD_KEYS = frozenset({"schema", "call_id", "sections", "head"})
SIGNATURE_KEYS = frozenset({"algorithm", "key_id", "signature"})


@dataclass(frozen=True)
class Stage:
    index: int
    name: str
    #: Signer kinds allowed to write it.
    signers: frozenset
    #: A body field that must hold exactly this value when the stage is written by
    #: this signer kind: ``{kind: (field, value)}``.
    only_when: Tuple[Tuple[str, str, Any], ...] = ()


_CLOUD = frozenset({SIGNER_CLOUD})
_HOST = frozenset({SIGNER_HOST})
_EITHER = frozenset({SIGNER_CLOUD, SIGNER_HOST})

#: S0..S10 in order. Cloud may write S6 only to say the host did not verify.
STAGES: Tuple[Stage, ...] = (
    Stage(0, "admit", _CLOUD),
    Stage(1, "contract", _CLOUD),
    Stage(2, "authority", _CLOUD),
    Stage(3, "approval", _CLOUD),
    Stage(4, "lease", _CLOUD),
    Stage(5, "dispatch", _CLOUD),
    Stage(6, "host_claim", _EITHER, only_when=((SIGNER_CLOUD, "host_verified", False),)),
    Stage(7, "host_execute", _HOST),
    Stage(8, "evidence", _HOST),
    Stage(9, "verdict", _CLOUD),
    Stage(10, "reconcile", _EITHER),
)
STAGE_BY_NAME: Dict[str, Stage] = {stage.name: stage for stage in STAGES}


def digest_of(value: Any) -> str:
    """``sha256:<hex>`` of ``value``'s canonical bytes."""
    return DIGEST_PREFIX + hashlib.sha256(canonical_bytes(value)).hexdigest()


def unsigned_view(section: Mapping[str, Any]) -> Dict[str, Any]:
    """The section without its attestation: what its digest and signature cover."""
    return {key: value for key, value in section.items() if key not in ATTESTATION_KEYS}


def section_digest(section: Mapping[str, Any]) -> str:
    return digest_of(unsigned_view(section))


def signing_message(section: Mapping[str, Any]) -> bytes:
    """The exact bytes a section's signature is made over (per-stage domain)."""
    stage = str(section.get("stage") or "")
    return SIGNATURE_DOMAIN + stage.encode("utf-8") + b"\n" + canonical_bytes(unsigned_view(section))


def signer_kind(signer: Any) -> str:
    """``cloud``, ``host`` (``host:<device id>``), or ``""`` for anything else."""
    if signer == SIGNER_CLOUD:
        return SIGNER_CLOUD
    if isinstance(signer, str) and signer.startswith(HOST_SIGNER_PREFIX) and len(signer) > len(HOST_SIGNER_PREFIX):
        return SIGNER_HOST
    return ""


def signer_problem(section: Mapping[str, Any]) -> str:
    """Why this signer may not write this stage; ``""`` when it may."""
    stage = STAGE_BY_NAME.get(str(section.get("stage") or ""))
    if stage is None:
        return "CHAIN_RECORD_UNKNOWN_STAGE"
    kind = signer_kind(section.get("signer"))
    if kind not in stage.signers:
        return "CHAIN_RECORD_WRONG_SIGNER"
    body = section.get("body") if isinstance(section.get("body"), Mapping) else {}
    for limited_kind, field, value in stage.only_when:
        if kind == limited_kind and body.get(field) is not value:
            return "CHAIN_RECORD_WRONG_SIGNER"
    return ""


def attestation_problem(section: Mapping[str, Any]) -> str:
    """Exactly one well-formed attestation: a signature or the ``no_signer`` marker."""
    has_signature, has_marker = "signature" in section, "unsigned" in section
    if has_signature == has_marker:
        return "CHAIN_RECORD_ATTESTATION_INVALID"
    if has_marker and section["unsigned"] != UNSIGNED_NO_SIGNER:
        return "CHAIN_RECORD_ATTESTATION_INVALID"
    if has_signature:
        signature = section["signature"]
        if not isinstance(signature, Mapping) or set(signature) != SIGNATURE_KEYS:
            return "CHAIN_RECORD_ATTESTATION_INVALID"
    return ""


def section_problems(section: Any, *, expected_prev: str, expected_seq: int, call_id: str,
                     after_stage: int) -> List[str]:
    """Every format problem of one section in its place; empty when it is well formed."""
    if not isinstance(section, Mapping):
        return ["CHAIN_RECORD_SECTION_INVALID"]
    checks = (
        (set(unsigned_view(section)) == SECTION_KEYS, "CHAIN_RECORD_SECTION_INVALID"),
        (section.get("schema") == SCHEMA, "CHAIN_RECORD_SCHEMA"),
        (section.get("call_id") == call_id, "CHAIN_RECORD_WRONG_CALL"),
        (section.get("prev") == expected_prev, "CHAIN_RECORD_LINK_BROKEN"),
        (type(section.get("seq")) is int and section.get("seq") == expected_seq, "CHAIN_RECORD_SEQ"),
        (isinstance(section.get("body"), Mapping) and isinstance(section.get("at"), str),
         "CHAIN_RECORD_SECTION_INVALID"),
    )
    problems = list(dict.fromkeys(code for ok, code in checks if not ok))
    stage = STAGE_BY_NAME.get(str(section.get("stage") or ""))
    if stage is not None and stage.index <= after_stage:
        problems.append("CHAIN_RECORD_STAGE_ORDER")
    problems.extend(code for code in (signer_problem(section), attestation_problem(section)) if code)
    return problems


def link_problems(record: Any) -> List[str]:
    """Every format and link problem of a whole record (no signature check), as ``CODE@seq``."""
    if not isinstance(record, Mapping) or set(record) != RECORD_KEYS:
        return ["CHAIN_RECORD_INVALID"]
    if record.get("schema") != SCHEMA:
        return ["CHAIN_RECORD_SCHEMA"]
    call_id, sections = record.get("call_id"), record.get("sections")
    if not isinstance(call_id, str) or not call_id or not isinstance(sections, list):
        return ["CHAIN_RECORD_INVALID"]
    problems: List[str] = []
    prev, last = GENESIS, -1
    for position, section in enumerate(sections, start=1):
        found = section_problems(section, expected_prev=prev, expected_seq=position, call_id=call_id,
                                 after_stage=last)
        problems.extend(f"{code}@{position}" for code in found)
        if not isinstance(section, Mapping):
            return problems
        prev = section_digest(section)
        stage = STAGE_BY_NAME.get(str(section.get("stage") or ""))
        last = stage.index if stage is not None else last
    if record.get("head") != prev:
        problems.append("CHAIN_RECORD_HEAD_MISMATCH")
    return problems


def stage_section(record: Mapping[str, Any], stage: str) -> Optional[Mapping[str, Any]]:
    """The record's section of ``stage``, if it has one."""
    for section in record.get("sections") or ():
        if isinstance(section, Mapping) and section.get("stage") == stage:
            return section
    return None


__all__ = [
    "ATTESTATION_KEYS", "DIGEST_PREFIX", "GENESIS", "HOST_SIGNER_PREFIX", "RECORD_KEYS", "SCHEMA",
    "SECTION_KEYS", "SIGNATURE_DOMAIN", "SIGNER_CLOUD", "SIGNER_HOST", "STAGES", "STAGE_BY_NAME", "Stage",
    "UNSIGNED_NO_SIGNER", "attestation_problem", "canonical_bytes", "digest_of", "link_problems",
    "section_digest", "section_problems", "signer_kind", "signer_problem", "signing_message",
    "stage_section", "unsigned_view",
]
