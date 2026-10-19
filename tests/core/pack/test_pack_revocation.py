"""The signed revocation list: a revoked pack refuses to start, standalone or in a Space."""

import copy
import json

import pytest
from portable_helpers import LOCK, example_source

from core.modules.registry import ModuleRegistry
from core.pack.host import install_pack, installed_packs
from core.pack.manifest import PackManifestError
from core.pack.portable import build_portable_pack, extract_pack_zip
from core.pack.standalone import load_standalone
from core.pack.supply_chain import (
    REVOCATION_REASONS,
    load_revocations,
    read_revocations,
    sign_revocations,
)


def code_of(call):
    with pytest.raises(PackManifestError) as info:
        call()
    return info.value.code


@pytest.fixture
def built_pack(tmp_path):
    out = tmp_path / "ratings.zip"
    report = build_portable_pack(example_source(tmp_path), out, lockfile=LOCK)
    return out, report


def revocation_doc(keypair, digests, **extra):
    private, _ = keypair
    entries = [{"digest": digest, "reason": "key_compromise"} for digest in digests]
    return sign_revocations(entries, private, "revoker-1", sequence=extra.pop("sequence", 1),
                            issued_at="2026-10-19T00:00:00Z")


def test_a_signed_list_round_trips(keypair, built_pack):
    _, report = built_pack
    doc = revocation_doc(keypair, [report["pack_digest"]])
    assert doc["schema"] == "flyto.pack-revocations.v1"
    revocations = load_revocations(doc, {"revoker-1": keypair[1]})
    assert revocations.is_revoked(report["pack_digest"])
    assert not revocations.is_revoked("sha256:" + "0" * 64)
    assert revocations.sequence == 1
    assert "key_compromise" in REVOCATION_REASONS


def test_a_changed_list_is_refused(keypair, built_pack):
    doc = revocation_doc(keypair, ["sha256:" + "1" * 64])
    tampered = copy.deepcopy(doc)
    tampered["list"]["revoked"] = []  # dropping an entry is the attack that matters
    assert code_of(lambda: load_revocations(tampered, {"revoker-1": keypair[1]})) == "REVOCATION_SIGNATURE_MISMATCH"


def test_a_list_from_an_untrusted_key_is_refused(keypair):
    doc = revocation_doc(keypair, ["sha256:" + "1" * 64])
    assert code_of(lambda: load_revocations(doc, {})) == "REVOCATION_UNTRUSTED_KEY"


@pytest.mark.parametrize("entries", [
    [{"digest": "sha256:" + "1" * 64, "reason": "key_compromise"}] * 2,
    [{"digest": "sha256:XYZ", "reason": "key_compromise"}],
    [{"digest": "sha256:" + "1" * 64, "reason": "because"}],
    [{"digest": "sha256:" + "1" * 64, "reason": "withdrawn", "note": "extra key"}],
])
def test_a_malformed_list_is_refused(keypair, entries):
    private, public = keypair
    assert code_of(lambda: sign_revocations(entries, private, "revoker-1", sequence=1,
                                            issued_at="2026-10-19T00:00:00Z")) == "REVOCATION_INVALID"


def test_a_list_read_from_disk_is_verified(tmp_path, keypair):
    path = tmp_path / "revocations.json"
    path.write_text(json.dumps(revocation_doc(keypair, ["sha256:" + "1" * 64])), encoding="utf-8")
    assert read_revocations(path, {"revoker-1": keypair[1]}).is_revoked("sha256:" + "1" * 64)
    path.write_text("not json", encoding="utf-8")
    assert code_of(lambda: read_revocations(path, {"revoker-1": keypair[1]})) == "REVOCATION_INVALID"


def test_a_revoked_pack_refuses_to_load_into_a_space(tmp_path, keypair, built_pack, host_version_241):
    out, report = built_pack
    pack_dir = tmp_path / "unpacked"
    pack_dir.mkdir()
    extract_pack_zip(out, pack_dir)
    revocations = load_revocations(revocation_doc(keypair, [report["pack_digest"]]), {"revoker-1": keypair[1]})
    assert code_of(lambda: install_pack(pack_dir, require_signature=False, revocations=revocations)) == "PACK_REVOKED"
    assert "com.example.ratings" not in installed_packs()
    assert not ModuleRegistry.has("ratings.company.get")
    # The same pack, not revoked, installs.
    other = load_revocations(revocation_doc(keypair, ["sha256:" + "2" * 64]), {"revoker-1": keypair[1]})
    assert install_pack(pack_dir, require_signature=False, revocations=other).pack_id == "com.example.ratings"


async def test_a_revoked_pack_refuses_to_start_standalone(tmp_path, keypair, built_pack, host_version_241):
    out, report = built_pack
    revocations = load_revocations(revocation_doc(keypair, [report["pack_digest"]]), {"revoker-1": keypair[1]})
    assert code_of(lambda: load_standalone(out, transport="stdio", require_signature=False,
                                           revocations=revocations)) == "PACK_REVOKED"
    assert not ModuleRegistry.has("ratings.company.get")


def test_the_cli_refuses_to_run_a_revoked_pack(tmp_path, keypair, built_pack, capsys, host_version_241):
    import argparse

    from cryptography.hazmat.primitives import serialization

    from cli.pack import run_pack_command

    out, report = built_pack
    revocations = tmp_path / "revocations.json"
    revocations.write_text(json.dumps(revocation_doc(keypair, [report["pack_digest"]])), encoding="utf-8")
    public = tmp_path / "revoker.pem"
    public.write_bytes(keypair[1].public_bytes(serialization.Encoding.PEM,
                                               serialization.PublicFormat.SubjectPublicKeyInfo))
    args = argparse.Namespace(
        pack_action="run", source=str(out), transport="stdio", host="127.0.0.1", port=0,
        trusted_key=[], allow_unsigned=True, revocations=str(revocations),
        revocation_key=[f"revoker-1={public}"],
    )
    assert run_pack_command(args) == 1
    assert "PACK_REVOKED" in capsys.readouterr().err
    # verify reports the same refusal.
    verify = argparse.Namespace(pack_action="verify", pack_dir=str(out), trusted_key=[], allow_unsigned=True,
                                revocations=str(revocations), revocation_key=[f"revoker-1={public}"])
    assert run_pack_command(verify) == 1
    assert "PACK_REVOKED" in capsys.readouterr().err


def test_a_revocation_list_without_a_trusted_key_is_refused_by_the_cli(tmp_path, keypair, built_pack, capsys):
    import argparse

    from cli.pack import run_pack_command

    out, _ = built_pack
    revocations = tmp_path / "revocations.json"
    revocations.write_text(json.dumps(revocation_doc(keypair, ["sha256:" + "1" * 64])), encoding="utf-8")
    verify = argparse.Namespace(pack_action="verify", pack_dir=str(out), trusted_key=[], allow_unsigned=True,
                                revocations=str(revocations), revocation_key=[])
    assert run_pack_command(verify) == 1
    assert "REVOCATION_UNTRUSTED_KEY" in capsys.readouterr().err
