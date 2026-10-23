"""``flyto pack certify``: one signed record that a pack passed every check, and a host that can require it.

The certifier runs, on one built pack: verify, conform, ``pack test``
against the pack's own recorded fixtures, standalone health against those
same fixtures, and the declared-compatibility check against the host matrix.
Only when every check passes does it sign a ``flyto.pack-certification.v1``
record naming the pack digest, the flyto-core range it passed on, each
check's result and the certifier key. A host whose policy table requires
certification refuses a pack without a valid record from a trusted certifier
(``PACK_UNCERTIFIED``) and one whose record no longer applies
(``CERTIFICATION_STALE``).
"""

import copy
import json

import pytest
from devkit_helpers import LOCK, cli, decided_scaffold, edit_json, read_json

import core.pack.host as host
from core.pack.certification import (
    CERTIFICATION_CHECKS,
    CERTIFICATION_SCHEMA,
    POLICY_SCHEMA,
    STALENESS,
    certify,
    load_certification_policy,
    verify_certification,
)
from core.pack.compatibility import MATRIX_VERSION
from core.pack.host import install_pack
from core.pack.manifest import PackManifestError
from core.pack.portable import build_portable_pack, extract_pack_zip, verify_pack

PUBLISHER = "publisher-1"
CERTIFIER = "certifier-1"


def code_of(call):
    with pytest.raises(PackManifestError) as info:
        call()
    return info.value.code


@pytest.fixture
def certifier():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.generate()
    return private, private.public_key()


@pytest.fixture
def built(tmp_path, keypair, monkeypatch):
    monkeypatch.setenv("FLYTO_PACK_NO_KEYCHAIN", "1")
    source = decided_scaffold(tmp_path)
    out = tmp_path / "items-0.1.0.zip"
    report = build_portable_pack(source, out, lockfile=LOCK, private_key=keypair[0], key_id=PUBLISHER)
    return out, report, {PUBLISHER: keypair[1]}


def certified(built, certifier):
    zip_path, _report, trusted = built
    return certify(zip_path, private_key=certifier[0], key_id=CERTIFIER, trusted_keys=trusted)


def policy(certifier, records, **rule):
    document = {"schema": POLICY_SCHEMA,
                "rules": [{"packs": "com.example.*", "require": True, "certifiers": [CERTIFIER], **rule}]}
    return load_certification_policy(document, {CERTIFIER: certifier[1]}, records=records)


def space_copy(tmp_path, zip_path):
    target = tmp_path / "space-copy"
    target.mkdir()
    extract_pack_zip(zip_path, target)
    return target


# -- the record --------------------------------------------------------------------------


def test_a_pack_that_passes_every_check_gets_a_signed_record(built, certifier):
    _zip, report, _trusted = built
    result = certified(built, certifier)
    assert result["certified"], result["results"]
    assert [item["check"] for item in result["results"]] == list(CERTIFICATION_CHECKS)
    assert {item["verdict"] for item in result["results"]} == {"pass"}
    record = result["record"]
    assert record["schema"] == CERTIFICATION_SCHEMA
    body = verify_certification(record, {CERTIFIER: certifier[1]})
    assert body["pack"] == {"id": "com.example.items", "version": "0.1.0", "digest": report["pack_digest"]}
    assert body["core"]["min"] == read_json_manifest_min_host(built)
    assert body["core"]["max"] == host._host_version()
    assert body["matrix_version"] == MATRIX_VERSION
    assert body["certifier_key_id"] == CERTIFIER
    assert [item["check"] for item in body["checks"]] == list(CERTIFICATION_CHECKS)
    assert "pack.connector" in body["features"]


def read_json_manifest_min_host(built):
    from core.pack.portable import opened_pack

    with opened_pack(built[0]) as root:
        return read_json(root / "flyto-pack.json")["pack"]["min_host"]


def test_a_changed_record_does_not_verify(built, certifier):
    record = certified(built, certifier)["record"]
    tampered = copy.deepcopy(record)
    tampered["certification"]["core"]["max"] = "9.0.0"
    assert code_of(lambda: verify_certification(tampered, {CERTIFIER: certifier[1]})) == \
        "CERTIFICATION_SIGNATURE_MISMATCH"
    assert code_of(lambda: verify_certification(record, {})) == "CERTIFICATION_UNTRUSTED_KEY"


def test_a_failing_check_signs_nothing(tmp_path, keypair, certifier, monkeypatch):
    monkeypatch.setenv("FLYTO_PACK_NO_KEYCHAIN", "1")
    source = decided_scaffold(tmp_path)
    # A recorded call that now expects the wrong answer: pack test fails.
    edit_json(source / "fixtures" / "exchanges.json",
              lambda doc: doc["calls"][0].__setitem__("expect", {"error_code": "OUT_OF_SCOPE"}))
    out = tmp_path / "broken.zip"
    build_portable_pack(source, out, lockfile=LOCK, private_key=keypair[0], key_id=PUBLISHER)
    result = certify(out, private_key=certifier[0], key_id=CERTIFIER, trusted_keys={PUBLISHER: keypair[1]})
    assert not result["certified"]
    assert result["record"] is None
    assert {item["check"]: item["verdict"] for item in result["results"]}["pack_test"] == "fail"


def test_an_unverifiable_pack_is_not_certified(built, certifier):
    zip_path, _report, _trusted = built
    result = certify(zip_path, private_key=certifier[0], key_id=CERTIFIER, trusted_keys={})
    verdicts = {item["check"]: item for item in result["results"]}
    assert verdicts["verify"]["verdict"] == "fail"
    assert verdicts["verify"]["detail"] == "UNTRUSTED_KEY"
    assert result["record"] is None


def test_min_host_older_than_the_matrix_fails_the_compatibility_check(tmp_path, keypair, certifier, monkeypatch):
    monkeypatch.setenv("FLYTO_PACK_NO_KEYCHAIN", "1")
    source = decided_scaffold(tmp_path)
    edit_json(source / "flyto-pack.json", lambda doc: doc["pack"].__setitem__("min_host", "2.40.0"))
    out = tmp_path / "old.zip"
    # The lockfile pins flyto-core 2.41.0, so the build itself is fine; min_host is the lie.
    build_portable_pack(source, out, lockfile=LOCK, private_key=keypair[0], key_id=PUBLISHER)
    result = certify(out, private_key=certifier[0], key_id=CERTIFIER, trusted_keys={PUBLISHER: keypair[1]})
    verdicts = {item["check"]: item["verdict"] for item in result["results"]}
    assert verdicts["compatibility"] == "fail"
    assert result["record"] is None


# -- the host policy ----------------------------------------------------------------------


def test_a_host_that_requires_certification_installs_a_certified_pack(built, certifier, tmp_path):
    zip_path, _report, trusted = built
    record = certified(built, certifier)["record"]
    gate = policy(certifier, [record])
    provenance = install_pack(space_copy(tmp_path, zip_path), trusted_keys=trusted, certification=gate)
    assert provenance.signature_verified


def test_a_host_that_requires_certification_refuses_an_uncertified_pack(built, certifier, tmp_path):
    zip_path, _report, trusted = built
    gate = policy(certifier, [])
    target = space_copy(tmp_path, zip_path)
    assert code_of(lambda: install_pack(target, trusted_keys=trusted, certification=gate)) == "PACK_UNCERTIFIED"
    assert code_of(lambda: verify_pack(zip_path, trusted_keys=trusted, certification=gate)) == "PACK_UNCERTIFIED"
    assert "com.example.items" not in host.installed_packs()


def test_a_record_from_a_certifier_the_rule_does_not_name_does_not_count(built, certifier, tmp_path):
    zip_path, _report, trusted = built
    record = certified(built, certifier)["record"]
    document = {"schema": POLICY_SCHEMA,
                "rules": [{"packs": "*", "require": True, "certifiers": ["someone-else"]}]}
    gate = load_certification_policy(document, {CERTIFIER: certifier[1]}, records=[record])
    assert code_of(lambda: install_pack(space_copy(tmp_path, zip_path), trusted_keys=trusted,
                                        certification=gate)) == "PACK_UNCERTIFIED"


def test_a_record_for_another_build_does_not_count(built, certifier, tmp_path, keypair):
    zip_path, _report, trusted = built
    record = certified(built, certifier)["record"]
    other = tmp_path / "other"
    source = decided_scaffold(other)
    edit_json(source / "flyto-pack.json", lambda doc: doc["pack"].__setitem__("description", "A rebuild."))
    rebuilt = tmp_path / "rebuilt.zip"
    build_portable_pack(source, rebuilt, lockfile=LOCK, private_key=keypair[0], key_id=PUBLISHER)
    gate = policy(certifier, [record])
    assert code_of(lambda: verify_pack(rebuilt, trusted_keys=trusted, certification=gate)) == "PACK_UNCERTIFIED"


def test_a_newer_host_than_the_record_covers_finds_it_stale(built, certifier, tmp_path, monkeypatch):
    zip_path, _report, trusted = built
    record = certified(built, certifier)["record"]
    gate = policy(certifier, [record])
    monkeypatch.setattr(host, "_host_version", lambda: "2.99.0")
    assert code_of(lambda: install_pack(space_copy(tmp_path, zip_path), trusted_keys=trusted,
                                        certification=gate)) == "CERTIFICATION_STALE"


def test_an_expired_record_is_stale(built, certifier):
    zip_path, _report, trusted = built
    record = certify(zip_path, private_key=certifier[0], key_id=CERTIFIER, trusted_keys=trusted,
                     certified_at="2020-01-01T00:00:00Z")["record"]
    gate = policy(certifier, [record], max_age_days=30)
    assert code_of(lambda: verify_pack(zip_path, trusted_keys=trusted, certification=gate)) == "CERTIFICATION_STALE"


def test_staleness_is_a_table():
    assert [name for name, _holds in STALENESS] == ["host_newer_than_certified", "host_older_than_certified",
                                                     "matrix_changed", "expired"]


def test_a_pack_no_rule_matches_installs_without_a_record(built, certifier, tmp_path):
    zip_path, _report, trusted = built
    document = {"schema": POLICY_SCHEMA, "rules": [{"packs": "org.other.*", "require": True,
                                                    "certifiers": [CERTIFIER]}]}
    gate = load_certification_policy(document, {CERTIFIER: certifier[1]}, records=[])
    install_pack(space_copy(tmp_path, zip_path), trusted_keys=trusted, certification=gate)


@pytest.mark.parametrize("document", [
    {"schema": "flyto.pack-certification-policy.v0", "rules": []},
    {"schema": POLICY_SCHEMA, "rules": [{"packs": "*", "require": True}]},
    {"schema": POLICY_SCHEMA, "rules": [{"packs": "*", "require": True, "certifiers": []}]},
    {"schema": POLICY_SCHEMA, "rules": [{"packs": "*", "require": "yes", "certifiers": [CERTIFIER]}]},
    {"schema": POLICY_SCHEMA, "rules": [{"packs": "*", "require": True, "certifiers": [CERTIFIER], "x": 1}]},
    {"schema": POLICY_SCHEMA, "rules": [{"packs": "*", "require": True, "certifiers": [CERTIFIER],
                                         "max_age_days": 0}]},
])
def test_a_malformed_policy_is_refused(document, certifier):
    assert code_of(lambda: load_certification_policy(document, {CERTIFIER: certifier[1]})) == \
        "CERTIFICATION_POLICY_INVALID"


def test_a_malformed_record_in_the_store_refuses_nothing_open(built, certifier, tmp_path):
    """A record that does not verify is not counted; with nothing else, the pack is uncertified."""
    zip_path, _report, trusted = built
    record = certified(built, certifier)["record"]
    broken = copy.deepcopy(record)
    broken["signature"]["signature"] = "AAAA"
    gate = policy(certifier, [broken])
    assert code_of(lambda: verify_pack(zip_path, trusted_keys=trusted, certification=gate)) == "PACK_UNCERTIFIED"


# -- the CLI ------------------------------------------------------------------------------


def test_the_cli_certifies_then_requires_it(built, certifier, tmp_path, capsys):
    from cryptography.hazmat.primitives import serialization

    zip_path, _report, trusted = built
    keys = {}
    for name, (private, public) in {"certifier": certifier}.items():
        (tmp_path / f"{name}.pem").write_bytes(private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        (tmp_path / f"{name}.pub").write_bytes(public.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        keys[name] = tmp_path / f"{name}.pub"
    (tmp_path / "publisher.pub").write_bytes(trusted[PUBLISHER].public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    out = tmp_path / "items.cert.json"
    assert cli("certify", zip_path, "--trusted-key", f"{PUBLISHER}={tmp_path / 'publisher.pub'}",
               "--key", tmp_path / "certifier.pem", "--key-id", CERTIFIER, "-o", out) == 0
    assert read_json(out)["schema"] == CERTIFICATION_SCHEMA
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps({"schema": POLICY_SCHEMA, "rules": [
        {"packs": "*", "require": True, "certifiers": [CERTIFIER]}]}), encoding="utf-8")
    common = ("--trusted-key", f"{PUBLISHER}={tmp_path / 'publisher.pub'}", "--certification-policy", policy_file,
              "--certifier-key", f"{CERTIFIER}={keys['certifier']}")
    assert cli("verify", zip_path, *common) == 1
    assert "PACK_UNCERTIFIED" in capsys.readouterr().err
    assert cli("verify", zip_path, *common, "--certification", out) == 0
    assert json.loads(capsys.readouterr().out)["certification"]["certifier_key_id"] == CERTIFIER


def test_a_pack_this_process_already_runs_is_not_certified_on_its_answers(built, certifier, tmp_path):
    zip_path, _report, trusted = built
    install_pack(space_copy(tmp_path, zip_path), trusted_keys=trusted)
    result = certified(built, certifier)
    verdicts = {item["check"]: (item["verdict"], item["detail"]) for item in result["results"]}
    assert verdicts["verify"] == ("fail", "ALREADY_INSTALLED")
    assert {verdict for verdict, _ in list(verdicts.values())[1:]} == {"not_run"}
    assert result["record"] is None
