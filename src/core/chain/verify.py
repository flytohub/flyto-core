# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Verify one ``flyto.execution-chain.v1`` record offline: the record, the published keys, nothing else.

No network, no store, no import of the issuer's code, and no key taken from
the issuer unless the caller passes it in. Checks, in order:

1. format and links (:func:`core.chain.record.link_problems`): closed key
   sets, ``prev`` links and ``head``, ``seq``, stage order, who may write
   each stage, one attestation per section;
2. every section's signature against its signer's key document
   (:func:`core.chain.keys.verify_section`): trust through rotations,
   validity windows, revocation;
3. what can be checked without the issuer (:data:`INVARIANTS`): the host's
   claim sits on the dispatch it names, the host ran the contract the
   issuer judged, and evidence brackets the effect in the host's sequence;
4. completeness (:data:`COMPLETENESS`).

``trust="host-only"`` (:data:`TRUST_MODES`) checks host-signed sections and
every link, and needs no issuer key: it proves what a host received and did.
Issuer sections are then reported as received (``cloud_sections_as_received``),
not as verified authority.

The result is ``verified`` (exit 0), ``refused`` (1, typed codes in
``problems``) or ``incomplete`` (2: well formed and signed, but no verdict
yet, an unsigned section, an unknown effect with no reconciliation, or, under
host-only trust, no host-signed section at all).
"""

from __future__ import annotations

import operator
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence, Tuple

from .keys import KEYS_SCHEMA, ChainKeysError, documents_by_signer, verify_section
from .record import (
    SCHEMA,
    SIGNER_CLOUD,
    SIGNER_HOST,
    link_problems,
    section_digest,
    signer_kind,
    stage_section,
)

EXPORT_SCHEMA = "flyto.execution-chain-export.v1"
REPORT_SCHEMA = "flyto.execution-chain-verification.v1"

EXIT_VERIFIED, EXIT_REFUSED, EXIT_INCOMPLETE = 0, 1, 2
RESULT_EXIT = {"verified": EXIT_VERIFIED, "refused": EXIT_REFUSED, "incomplete": EXIT_INCOMPLETE}

#: Trust mode -> the signer kinds whose signatures are checked.
TRUST_MODES: Dict[str, frozenset] = {
    "all": frozenset({SIGNER_CLOUD, SIGNER_HOST}),
    "host-only": frozenset({SIGNER_HOST}),
}


# -- invariants a verifier can check without the issuer ------------------------------------


def _body(section: Any) -> Mapping[str, Any]:
    body = section.get("body") if isinstance(section, Mapping) else None
    return body if isinstance(body, Mapping) else {}


def _list(value: Any) -> List[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _claim_after_dispatch(record: Mapping[str, Any]) -> List[str]:
    """A host's S6 links to the S5 it verified, and names that head."""
    claim, dispatch = stage_section(record, "host_claim"), stage_section(record, "dispatch")
    if claim is None or signer_kind(claim.get("signer")) != SIGNER_HOST:
        return []
    problems = []
    if dispatch is None or claim.get("prev") != section_digest(dispatch):
        problems.append("CHAIN_HOST_CLAIM_NOT_AFTER_DISPATCH")
    if _body(claim).get("cloud_record_head") != claim.get("prev"):
        problems.append("CHAIN_HOST_CLAIM_HEAD_MISMATCH")
    return problems


def _ran_the_judged_contract(record: Mapping[str, Any]) -> List[str]:
    """S7's ``local_contract_digest`` equals the digest S1 judged each capability by."""
    contracts = _body(stage_section(record, "contract")).get("contracts")
    contracts = contracts if isinstance(contracts, Mapping) else {}
    calls = _list(_body(stage_section(record, "host_execute")).get("calls"))
    return [
        "CHAIN_HOST_EXECUTE_LOCAL_CONTRACT_MISMATCH"
        for call in calls
        if contracts.get(call.get("capability_id")) and call.get("local_contract_digest") != contracts[call["capability_id"]]
    ]


#: Capture kind -> how its sequence must compare with the effect's; every other kind is after it.
_CAPTURE_ORDER: Dict[str, Callable[[int, int], bool]] = {"before": operator.lt}
_AFTER_EFFECT: Callable[[int, int], bool] = operator.gt


def _evidence_brackets_effect(record: Mapping[str, Any]) -> List[str]:
    """``before.capture_seq < effect_seq < after.capture_seq`` in the host's one sequence."""
    captures = _list(_body(stage_section(record, "evidence")).get("captures"))
    problems = []
    for call in _list(_body(stage_section(record, "host_execute")).get("calls")):
        effect = call.get("effect_seq")
        if type(effect) is not int:
            continue
        for capture in captures:
            if capture.get("call_id") != call.get("call_id"):
                continue
            seq = capture.get("capture_seq")
            ordered = _CAPTURE_ORDER.get(capture.get("kind"), _AFTER_EFFECT)
            if type(seq) is not int or not ordered(seq, effect):
                problems.append("CHAIN_EVIDENCE_ORDERING_UNPROVEN")
    return problems


INVARIANTS: Tuple[Callable[[Mapping[str, Any]], List[str]], ...] = (
    _claim_after_dispatch,
    _ran_the_judged_contract,
    _evidence_brackets_effect,
)


# -- completeness --------------------------------------------------------------------------


def _no_verdict(record, checked):
    return "no verdict (S9)" if stage_section(record, "verdict") is None else ""


def _unknown_effect_unreconciled(record, checked):
    verdict = stage_section(record, "verdict")
    if verdict is not None and _body(verdict).get("effect") == "unknown" \
            and stage_section(record, "reconcile") is None:
        return "unknown effect with no reconciliation (S10)"
    return ""


def _unsigned(record, checked):
    unsigned = [section.get("seq") for section in record["sections"] if "unsigned" in section]
    return f"unsigned sections {unsigned}" if unsigned else ""


def _nothing_checked(record, checked):
    return "no section was signed by a trusted signer" if not checked else ""


COMPLETENESS: Tuple[Callable[[Mapping[str, Any], Sequence[int]], str], ...] = (
    _no_verdict,
    _unknown_effect_unreconciled,
    _unsigned,
    _nothing_checked,
)


# -- inputs ----------------------------------------------------------------------------------


def _documents_in(value: Any) -> Iterable[Mapping[str, Any]]:
    """Every key document in one key input: a document, ``{signer: document}``, an export, or a list."""
    if isinstance(value, list):
        for item in value:
            yield from _documents_in(item)
        return
    if not isinstance(value, Mapping):
        raise ChainKeysError("a key input is a key document, a {signer: document} map, an export or a list")
    if value.get("schema") == KEYS_SCHEMA:
        yield value
    elif value.get("schema") == EXPORT_SCHEMA:
        if value.get("cloud_keys") is not None:
            yield value["cloud_keys"]
        yield from _documents_in(value.get("host_keys") or {})
    elif "schema" in value:
        raise ChainKeysError(f"{value.get('schema')!r} is not a key input")
    else:
        for signer, document in value.items():
            if not isinstance(document, Mapping) or document.get("issuer") != signer:
                raise ChainKeysError(f"the key document given for {signer!r} is issued by someone else")
            yield document


def key_documents_from(inputs: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    """``{signer: loaded key document}`` from key inputs; raises :class:`ChainKeysError`."""
    return documents_by_signer(document for value in inputs for document in _documents_in(value))


def record_from(loaded: Any) -> Any:
    """The record in a record file: the record itself, or an export's ``record`` (its keys are not taken)."""
    if isinstance(loaded, Mapping) and loaded.get("schema") == EXPORT_SCHEMA:
        return loaded.get("record")
    return loaded


# -- the verifier ----------------------------------------------------------------------------


def _report(record: Any, trust: str, result: str, **fields: Any) -> Dict[str, Any]:
    known = record if isinstance(record, Mapping) else {}
    report = {
        "schema": REPORT_SCHEMA, "record_schema": SCHEMA, "call_id": known.get("call_id"),
        "head": known.get("head"), "trust": trust, "problems": [], "incomplete": [],
        "cloud_sections_as_received": [], "verified_sections": [],
    }
    report.update(fields)
    return {**report, "result": result, "exit": RESULT_EXIT[result]}


def refused(record: Any, trust: str, problems: List[str], *, detail: str = "") -> Dict[str, Any]:
    """A refusal report; ``detail`` says why an input could not be read, for a person."""
    return _report(record, trust, "refused", problems=problems, **({"detail": detail} if detail else {}))


def _crypto_available() -> bool:
    try:
        import cryptography.hazmat.primitives.asymmetric.ed25519  # noqa: F401
    except ImportError:
        return False
    return True


def _signature_problems(record: Mapping[str, Any], documents: Mapping[str, Mapping[str, Any]],
                        checked_kinds: frozenset) -> Tuple[List[str], List[int], List[int]]:
    """``(problems, verified seqs, seqs reported as received)`` for every section."""
    problems: List[str] = []
    verified: List[int] = []
    as_received: List[int] = []
    head = str(record.get("head") or "")
    for section in record["sections"]:
        if not isinstance(section, Mapping):
            continue
        seq = section.get("seq")
        if signer_kind(section.get("signer")) not in checked_kinds:
            as_received.append(seq)
            continue
        if "unsigned" in section:
            continue
        document = documents.get(str(section.get("signer")))
        problem = "CHAIN_RECORD_NO_KEYS_FOR_SIGNER" if document is None else \
            verify_section(section, document, record_head=head)
        if problem:
            problems.append(f"{problem}@{seq}")
        else:
            verified.append(seq)
    return problems, verified, as_received


def verify_record(record: Any, keys: Any = None, *, trust: str = "all") -> Dict[str, Any]:
    """The verification report of ``record`` under ``keys`` (any key input, or ``{signer: document}``)."""
    if trust not in TRUST_MODES:
        raise ValueError(f"trust must be one of {sorted(TRUST_MODES)}")
    try:
        documents = key_documents_from([keys] if keys else [])
    except ChainKeysError as error:
        return refused(record, trust, [error.code], detail=str(error))
    structure = link_problems(record)
    if structure in (["CHAIN_RECORD_INVALID"], ["CHAIN_RECORD_SCHEMA"]):
        # Not a record of this schema at all: nothing below can be read.
        return refused(record, trust, structure)
    if not _crypto_available():
        return refused(record, trust, ["CHAIN_VERIFIER_CRYPTO_MISSING"])
    signatures, verified, as_received = _signature_problems(record, documents, TRUST_MODES[trust])
    problems = structure + signatures
    if not structure:
        problems += [code for invariant in INVARIANTS for code in invariant(record)]
    if problems:
        return _report(record, trust, "refused", problems=problems, verified_sections=verified,
                       cloud_sections_as_received=as_received)
    incomplete = [line for rule in COMPLETENESS for line in (rule(record, verified),) if line]
    return _report(record, trust, "incomplete" if incomplete else "verified", incomplete=incomplete,
                   verified_sections=verified, cloud_sections_as_received=as_received)


__all__ = [
    "COMPLETENESS", "EXIT_INCOMPLETE", "EXIT_REFUSED", "EXIT_VERIFIED", "EXPORT_SCHEMA", "INVARIANTS",
    "REPORT_SCHEMA", "RESULT_EXIT", "TRUST_MODES", "key_documents_from", "record_from", "refused",
    "verify_record",
]
