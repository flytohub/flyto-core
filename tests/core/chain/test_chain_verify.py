"""``core.chain``: the offline verifier of ``flyto.execution-chain.v1`` records.

The golden record under ``fixtures/golden`` was produced by flyto-cloud's own
``record.py`` and ``signing.py`` (``fixtures/golden/make_golden.py``), so these
tests hold core to Cloud's bytes, not to a copy of Cloud's rules written here.
The golden keys come from fixed seeds; the tests re-derive them to re-sign
records they change.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import socket
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

from core.chain import (
    EXIT_INCOMPLETE,
    EXIT_REFUSED,
    EXIT_VERIFIED,
    canonical_bytes,
    key_documents_from,
    section_digest,
    signing_message,
    verify_record,
)
from core.pack.manifest import canonical_bytes as pack_canonical_bytes

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
HOST = "host:dev-golden"


def _load(name):
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def _key(seed: str) -> ed25519.Ed25519PrivateKey:
    return ed25519.Ed25519PrivateKey.from_private_bytes(hashlib.sha256(seed.encode()).digest())


CLOUD_KEY = _key("flyto-core golden cloud 2")
HOST_KEY = _key("flyto-core golden host 1")


@pytest.fixture
def record():
    return _load("record.json")


@pytest.fixture
def keys():
    return {"cloud": _load("cloud-keys.json"), HOST: _load("host-keys.json")}


def _resign(record, *, from_seq=1):
    """Re-link and re-sign every section from ``from_seq`` on, with the golden keys."""
    sections = record["sections"]
    prev = section_digest(sections[from_seq - 2]) if from_seq > 1 else "sha256:" + "0" * 64
    for section in sections[from_seq - 1:]:
        section["prev"] = prev
        if "signature" in section:
            private = CLOUD_KEY if section["signer"] == "cloud" else HOST_KEY
            section["signature"]["signature"] = base64.b64encode(private.sign(signing_message(section))).decode()
        prev = section_digest(section)
    record["head"] = prev
    return record


def _codes(report):
    return {code.split("@")[0] for code in report["problems"]}


# -- Cloud's bytes -------------------------------------------------------------


def test_canonical_bytes_are_the_pack_canonical_bytes():
    assert canonical_bytes is pack_canonical_bytes


def test_golden_digests_and_signing_messages_equal_clouds(record):
    expected = _load("digests.json")
    assert [section_digest(s) for s in record["sections"]] == [row["digest"] for row in expected["sections"]]
    assert [hashlib.sha256(signing_message(s)).hexdigest() for s in record["sections"]] == [
        row["signing_message_sha256"] for row in expected["sections"]
    ]
    assert record["head"] == expected["head"]


def test_golden_record_verifies(record, keys):
    report = verify_record(record, keys)
    assert report["problems"] == [] and report["incomplete"] == []
    assert (report["result"], report["exit"]) == ("verified", EXIT_VERIFIED)


def test_verification_opens_no_socket(record, keys, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the chain verifier opened a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert verify_record(record, keys)["exit"] == EXIT_VERIFIED


# -- refusals ------------------------------------------------------------------


def test_a_tampered_section_breaks_its_signature_and_the_next_link(record, keys):
    record["sections"][2]["body"]["effective_max_level"] = 5
    report = verify_record(record, keys)
    assert report["exit"] == EXIT_REFUSED
    assert "CHAIN_RECORD_SIGNATURE_INVALID@3" in report["problems"]
    assert "CHAIN_RECORD_LINK_BROKEN@4" in report["problems"]


def test_a_tampered_last_section_breaks_the_head(record, keys):
    record["sections"][-1]["body"]["effect"] = "none"
    report = verify_record(record, keys)
    assert report["exit"] == EXIT_REFUSED
    assert {"CHAIN_RECORD_HEAD_MISMATCH", "CHAIN_RECORD_SIGNATURE_INVALID"} <= _codes(report)


def test_a_broken_prev_is_refused(record, keys):
    record["sections"][4]["prev"] = record["sections"][2]["prev"]
    report = verify_record(record, keys)
    assert report["exit"] == EXIT_REFUSED
    assert "CHAIN_RECORD_LINK_BROKEN@5" in report["problems"]


def test_a_reordered_or_repeated_stage_is_refused(record, keys):
    record["sections"][3]["stage"] = "admit"
    _resign(record)
    report = verify_record(record, keys)
    assert "CHAIN_RECORD_STAGE_ORDER@4" in report["problems"]


def test_a_host_stage_signed_by_cloud_is_refused(record, keys):
    record["sections"][7]["signer"] = "cloud"
    _resign(record)
    assert "CHAIN_RECORD_WRONG_SIGNER@8" in verify_record(record, keys)["problems"]


def test_a_revoked_key_is_refused(record, keys):
    keys["cloud"]["keys"][1]["revoked_at"] = "2026-10-26T12:00:00+00:00"
    report = verify_record(record, keys)
    assert report["exit"] == EXIT_REFUSED
    assert "CHAIN_RECORD_KEY_REVOKED@1" in report["problems"]
    assert "CHAIN_RECORD_KEY_REVOKED@10" in report["problems"]


def test_a_revoked_key_still_stands_on_a_record_its_revocation_retained(record, keys):
    keys["cloud"]["keys"][1]["revoked_at"] = "2026-10-26T12:00:00+00:00"
    keys["cloud"]["keys"][1]["retained_heads"] = [record["head"]]
    assert verify_record(record, keys)["exit"] == EXIT_VERIFIED


def test_a_signature_outside_the_key_window_is_refused(record, keys):
    keys["cloud"]["keys"][1]["not_after"] = "2026-10-26T08:00:03+00:00"
    report = verify_record(record, keys)
    assert "CHAIN_RECORD_KEY_OUT_OF_WINDOW@4" in report["problems"]
    assert "CHAIN_RECORD_KEY_OUT_OF_WINDOW@3" not in report["problems"]


def test_a_key_reached_only_by_a_forged_rotation_is_untrusted(record, keys):
    rotation = keys["cloud"]["rotations"][0]
    rotation["signature"] = base64.b64encode(CLOUD_KEY.sign(b"not the rotation")).decode()
    report = verify_record(record, keys)
    assert "CHAIN_RECORD_UNTRUSTED_KEY@1" in report["problems"]


def test_a_signer_with_no_published_keys_is_refused(record, keys):
    del keys[HOST]
    report = verify_record(record, keys)
    assert report["exit"] == EXIT_REFUSED
    assert "CHAIN_RECORD_NO_KEYS_FOR_SIGNER@7" in report["problems"]


def test_a_host_running_another_contract_is_refused(record, keys):
    record["sections"][7]["body"]["calls"][0]["local_contract_digest"] = "sha256:" + "1" * 64
    _resign(record, from_seq=8)
    report = verify_record(record, keys)
    assert report["problems"] == ["CHAIN_HOST_EXECUTE_LOCAL_CONTRACT_MISMATCH"]


def test_evidence_taken_after_the_effect_as_before_is_refused(record, keys):
    record["sections"][8]["body"]["captures"][0]["capture_seq"] = 9
    _resign(record, from_seq=9)
    assert verify_record(record, keys)["problems"] == ["CHAIN_EVIDENCE_ORDERING_UNPROVEN"]


def test_a_claim_not_on_the_dispatch_it_names_is_refused(record, keys):
    record["sections"][6]["body"]["cloud_record_head"] = "sha256:" + "2" * 64
    _resign(record, from_seq=7)
    assert verify_record(record, keys)["problems"] == ["CHAIN_HOST_CLAIM_HEAD_MISMATCH"]


def test_a_record_that_is_not_one_is_refused():
    report = verify_record({"schema": "something-else"}, {})
    assert (report["result"], report["exit"]) == ("refused", EXIT_REFUSED)


# -- incomplete ----------------------------------------------------------------


def test_a_record_with_no_verdict_is_incomplete(record, keys):
    record["sections"] = record["sections"][:-1]
    record["head"] = section_digest(record["sections"][-1])
    report = verify_record(record, keys)
    assert (report["result"], report["exit"]) == ("incomplete", EXIT_INCOMPLETE)


def test_an_unknown_effect_with_no_reconciliation_is_incomplete(record, keys):
    record["sections"][-1]["body"]["effect"] = "unknown"
    _resign(record, from_seq=10)
    assert verify_record(record, keys)["exit"] == EXIT_INCOMPLETE


def test_an_unsigned_section_is_incomplete_never_verified(record, keys):
    section = record["sections"][3]
    del section["signature"]
    section["unsigned"] = "no_signer"
    _resign(record, from_seq=4)
    report = verify_record(record, keys)
    assert report["exit"] == EXIT_INCOMPLETE
    assert any("4" in line for line in report["incomplete"])


# -- host-only trust -----------------------------------------------------------


def test_host_only_trust_needs_no_cloud_key(record, keys):
    report = verify_record(record, {HOST: keys[HOST]}, trust="host-only")
    assert report["exit"] == EXIT_VERIFIED
    assert report["cloud_sections_as_received"] == [1, 2, 3, 4, 5, 6, 10]


def test_host_only_trust_still_refuses_a_tampered_host_section(record, keys):
    record["sections"][8]["body"]["host_seq"] = 99
    report = verify_record(record, {HOST: keys[HOST]}, trust="host-only")
    assert report["exit"] == EXIT_REFUSED
    assert "CHAIN_RECORD_SIGNATURE_INVALID@9" in report["problems"]


def test_host_only_trust_still_checks_cloud_links(record, keys):
    record["sections"][1]["body"]["max_level"] = 1
    report = verify_record(record, {HOST: keys[HOST]}, trust="host-only")
    assert report["exit"] == EXIT_REFUSED
    assert "CHAIN_RECORD_LINK_BROKEN@3" in report["problems"]


def test_host_only_trust_with_no_host_section_proves_nothing(record, keys):
    record["sections"] = record["sections"][:6]
    record["head"] = section_digest(record["sections"][-1])
    report = verify_record(record, {}, trust="host-only")
    assert report["exit"] == EXIT_INCOMPLETE


def test_an_unknown_trust_mode_is_refused(record, keys):
    with pytest.raises(ValueError):
        verify_record(record, keys, trust="cloud-only")


# -- algorithms ----------------------------------------------------------------


def _ecdsa_entry(private, key_id):
    point = private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint)
    return {"key_id": key_id, "algorithm": "ecdsa-p256-sha256", "public_key": base64.b64encode(point).decode(),
            "not_before": None, "not_after": None, "revoked_at": None, "retained_heads": []}


def test_an_ecdsa_p256_host_key_verifies(record, keys):
    private = ec.generate_private_key(ec.SECP256R1())
    keys[HOST]["keys"].append(_ecdsa_entry(private, "host-ecdsa-1"))
    for section in record["sections"][6:9]:
        signature = private.sign(signing_message(section), ec.ECDSA(hashes.SHA256()))
        section["signature"] = {"algorithm": "ecdsa-p256-sha256", "key_id": "host-ecdsa-1",
                                "signature": base64.b64encode(signature).decode()}
    assert verify_record(record, keys)["exit"] == EXIT_VERIFIED
    record["sections"][7]["signature"]["signature"] = record["sections"][8]["signature"]["signature"]
    assert "CHAIN_RECORD_SIGNATURE_INVALID@8" in verify_record(record, keys)["problems"]


def test_a_signature_naming_another_algorithm_than_its_key_is_refused(record, keys):
    record["sections"][0]["signature"]["algorithm"] = "ecdsa-p256-sha256"
    assert "CHAIN_RECORD_SIGNATURE_INVALID@1" in verify_record(record, keys)["problems"]


def test_an_unknown_algorithm_key_entry_is_refused(record, keys):
    keys[HOST]["keys"][0]["algorithm"] = "rsa-pkcs1"
    report = verify_record(record, keys)
    assert report["exit"] == EXIT_REFUSED
    assert "CHAIN_KEYS_INVALID" in _codes(report)


# -- key inputs ----------------------------------------------------------------


def test_key_inputs_are_documents_signer_maps_or_exports(record, keys):
    export = {"schema": "flyto.execution-chain-export.v1", "record": record,
              "cloud_keys": keys["cloud"], "host_keys": {HOST: keys[HOST]}}
    as_documents = key_documents_from([keys["cloud"], keys[HOST]])
    as_map = key_documents_from([{HOST: keys[HOST]}, keys["cloud"]])
    as_export = key_documents_from([export])
    assert as_documents == as_map == as_export == keys
    assert verify_record(record, as_documents)["exit"] == EXIT_VERIFIED


def test_two_inputs_publishing_different_keys_for_one_signer_are_refused(keys):
    other = copy.deepcopy(keys["cloud"])
    other["keys"] = other["keys"][:1]
    with pytest.raises(ValueError):
        key_documents_from([keys["cloud"], other])
