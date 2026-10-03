"""ed25519 publisher signatures over flyto.pack.v1 manifests, verified offline."""

import base64
import copy
import json

import pytest
from cryptography.hazmat.primitives import serialization
from pack_helpers import write_pack

from core.pack.host import install_pack
from core.pack.manifest import PackManifestError, read_pack_manifest
from core.pack.signature import (
    load_public_key,
    read_signature,
    sign_manifest,
    verify_manifest_signature,
)


def raw_public(public):
    return public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def code_of(call):
    with pytest.raises(PackManifestError) as info:
        call()
    return info.value.code


def test_sign_and_verify_round_trip(tmp_path, keypair):
    private, public = keypair
    pack, manifest = write_pack(tmp_path / "p", sign_with=private, key_id="pub-2026")
    result = verify_manifest_signature(read_pack_manifest(pack), read_signature(pack), {"pub-2026": public})
    assert result["key_id"] == "pub-2026"
    assert result["algorithm"] == "ed25519"


@pytest.mark.parametrize("form", ["object", "raw", "base64", "pem"])
def test_trusted_key_forms(keypair, form):
    _, public = keypair
    value = {
        "object": public,
        "raw": raw_public(public),
        "base64": base64.b64encode(raw_public(public)).decode(),
        "pem": public.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode(),
    }[form]
    assert raw_public(load_public_key(value)) == raw_public(public)


def test_tampered_manifest_is_refused(tmp_path, keypair):
    private, public = keypair
    pack, manifest = write_pack(tmp_path / "p", sign_with=private)
    tampered = copy.deepcopy(manifest)
    tampered["modules"][0]["required_permissions"] = ["shell.execute"]
    signature = read_signature(pack)
    assert code_of(lambda: verify_manifest_signature(tampered, signature, {"test-key": public})) == "SIGNATURE_MISMATCH"
    # Even with the digest field rewritten to match, the signature bytes do not verify.
    from core.pack.manifest import manifest_sha256

    forged = dict(signature, manifest_sha256=manifest_sha256(tampered))
    assert code_of(lambda: verify_manifest_signature(tampered, forged, {"test-key": public})) == "SIGNATURE_MISMATCH"


def test_unknown_key_is_refused(tmp_path, keypair):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private, _ = keypair
    pack, manifest = write_pack(tmp_path / "p", sign_with=private)
    other = Ed25519PrivateKey.generate().public_key()
    signature = read_signature(pack)
    assert code_of(lambda: verify_manifest_signature(manifest, signature, {})) == "UNTRUSTED_KEY"
    assert code_of(lambda: verify_manifest_signature(manifest, signature, {"test-key": other})) == "SIGNATURE_MISMATCH"


def test_signature_needs_artifact_digest(tmp_path, keypair):
    private, public = keypair
    _, manifest = write_pack(tmp_path / "p", with_digest=False)
    assert code_of(lambda: sign_manifest(manifest, private, "test-key")) == "UNSIGNABLE"


def test_publisher_key_id_must_match(tmp_path, keypair):
    private, public = keypair
    _, manifest = write_pack(tmp_path / "p", publisher_key_id="pub-a")
    assert code_of(lambda: sign_manifest(manifest, private, "pub-b")) == "KEY_MISMATCH"
    signature = sign_manifest(manifest, private, "pub-a")
    assert verify_manifest_signature(manifest, signature, {"pub-a": public})["key_id"] == "pub-a"


def test_wrong_shape_signature_is_refused(tmp_path, keypair):
    _, public = keypair
    _, manifest = write_pack(tmp_path / "p")
    assert code_of(lambda: verify_manifest_signature(manifest, {"signature": "x"}, {"k": public})) == "INVALID_SIGNATURE"


def test_install_refuses_changed_files(tmp_path, keypair):
    private, public = keypair
    pack, _ = write_pack(tmp_path / "p", sign_with=private)
    (pack / "main.py").write_text("import os\n", encoding="utf-8")
    assert code_of(lambda: install_pack(pack, trusted_keys={"test-key": public})) == "DIGEST_MISMATCH"


def test_install_refuses_tampered_manifest_file(tmp_path, keypair):
    private, public = keypair
    pack, _ = write_pack(tmp_path / "p", sign_with=private)
    data = json.loads((pack / "flyto-pack.json").read_text())
    data["modules"][0]["label"] = "Something else"
    (pack / "flyto-pack.json").write_text(json.dumps(data), encoding="utf-8")
    assert code_of(lambda: install_pack(pack, trusted_keys={"test-key": public})) == "SIGNATURE_MISMATCH"


def test_reformatting_the_manifest_keeps_the_signature_valid(tmp_path, keypair):
    private, public = keypair
    pack, _ = write_pack(tmp_path / "p", sign_with=private)
    data = json.loads((pack / "flyto-pack.json").read_text())
    (pack / "flyto-pack.json").write_text(json.dumps(data, sort_keys=True, indent=7), encoding="utf-8")
    assert verify_manifest_signature(read_pack_manifest(pack), read_signature(pack), {"test-key": public})
