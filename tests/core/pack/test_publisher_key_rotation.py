"""Third-party maintenance: a publisher rotates its key, and a revoked key takes its later packs with it.

A rotation statement (``flyto.publisher-key-rotation.v1``) is signed by the
old key and names the new one. A host that trusts the old key follows a
bounded chain of statements to the key a pack is signed with, and refuses a
chain that does not connect (``KEY_ROTATION_BROKEN``) or is too long
(``KEY_ROTATION_TOO_LONG``).

Revoking a key (revocation list ``flyto.pack-revocations.v2``,
``revoked_keys``) revokes every pack that key signed after the revocation
point. A signature carries no time a compromised key could not forge, so the
point is stated as what the key signed before it: the ``retained`` digests.
Every other pack, and every rotation statement, signed by that key is
refused.
"""

import copy

import pytest
from devkit_helpers import LOCK, decided_scaffold, edit_json

from core.pack.host import install_pack
from core.pack.manifest import PackManifestError
from core.pack.portable import build_portable_pack, extract_pack_zip, verify_pack
from core.pack.publisher_keys import (
    MAX_ROTATION_CHAIN,
    ROTATION_SCHEMA,
    resolve_publisher_keys,
    rotation_digest,
    sign_key_rotation,
)
from core.pack.supply_chain import REVOCATIONS_SCHEMA_V2, load_revocations, sign_revocations

ISSUED = "2026-10-19T00:00:00Z"


def code_of(call):
    with pytest.raises(PackManifestError) as info:
        call()
    return info.value.code


def new_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.generate()
    return private, private.public_key()


@pytest.fixture
def keys():
    return {name: new_key() for name in ("pub-1", "pub-2", "pub-3", "revoker")}


def rotation(keys, old, new):
    return sign_key_rotation(keys[old][0], old, keys[new][1], new, issued_at=ISSUED)


def build(tmp_path, keys, key_id, name):
    """A signed build; ``name`` goes into its description, so two builds are two digests."""
    source = decided_scaffold(tmp_path / name)

    def change(doc):
        doc["pack"]["publisher_key_id"] = key_id
        doc["pack"]["description"] = f"Build {name}."

    edit_json(source / "flyto-pack.json", change)
    out = tmp_path / f"{name}.zip"
    report = build_portable_pack(source, out, lockfile=LOCK, private_key=keys[key_id][0], key_id=key_id)
    return out, report


def revocations(keys, revoked_keys, revoked=()):
    document = sign_revocations(list(revoked), keys["revoker"][0], "revoker", sequence=2, issued_at=ISSUED,
                                revoked_keys=revoked_keys)
    assert document["schema"] == REVOCATIONS_SCHEMA_V2
    return load_revocations(document, {"revoker": keys["revoker"][1]})


# -- rotation --------------------------------------------------------------------------------


def test_a_statement_names_the_new_key_and_is_signed_by_the_old(keys):
    statement = rotation(keys, "pub-1", "pub-2")
    assert statement["schema"] == ROTATION_SCHEMA
    assert statement["rotation"]["from_key_id"] == "pub-1"
    assert statement["rotation"]["to_key_id"] == "pub-2"
    resolved = resolve_publisher_keys({"pub-1": keys["pub-1"][1]}, [statement])
    assert set(resolved) == {"pub-1", "pub-2"}


def test_a_pack_signed_by_the_rotated_key_installs_where_only_the_old_one_is_trusted(tmp_path, keys, monkeypatch):
    monkeypatch.setenv("FLYTO_PACK_NO_KEYCHAIN", "1")
    zip_path, _ = build(tmp_path, keys, "pub-3", "items-v3")
    chain = [rotation(keys, "pub-1", "pub-2"), rotation(keys, "pub-2", "pub-3")]
    trusted = {"pub-1": keys["pub-1"][1]}
    assert code_of(lambda: verify_pack(zip_path, trusted_keys=trusted)) == "UNTRUSTED_KEY"
    report = verify_pack(zip_path, trusted_keys=trusted, key_rotations=chain)
    assert report["signature"]["key_id"] == "pub-3"
    target = tmp_path / "space"
    target.mkdir()
    extract_pack_zip(zip_path, target)
    assert install_pack(target, trusted_keys=trusted, key_rotations=chain).signature_verified


def test_a_chain_with_a_missing_link_is_refused(keys):
    chain = [rotation(keys, "pub-2", "pub-3")]  # nobody trusted vouches for pub-2
    assert code_of(lambda: resolve_publisher_keys({"pub-1": keys["pub-1"][1]}, chain)) == "KEY_ROTATION_BROKEN"


def test_a_statement_not_signed_by_the_old_key_is_refused(keys):
    forged = sign_key_rotation(keys["pub-2"][0], "pub-1", keys["pub-2"][1], "pub-2", issued_at=ISSUED)
    assert code_of(lambda: resolve_publisher_keys({"pub-1": keys["pub-1"][1]}, [forged])) == "KEY_ROTATION_BROKEN"


def test_a_changed_statement_is_refused(keys):
    statement = copy.deepcopy(rotation(keys, "pub-1", "pub-2"))
    statement["rotation"]["to_public_key"] = rotation(keys, "pub-1", "pub-3")["rotation"]["to_public_key"]
    assert code_of(lambda: resolve_publisher_keys({"pub-1": keys["pub-1"][1]}, [statement])) == "KEY_ROTATION_BROKEN"


def test_a_statement_that_rebinds_a_trusted_key_id_is_refused(keys):
    rebind = sign_key_rotation(keys["pub-1"][0], "pub-1", keys["pub-3"][1], "pub-1", issued_at=ISSUED)
    assert code_of(lambda: resolve_publisher_keys({"pub-1": keys["pub-1"][1]}, [rebind])) == "KEY_ROTATION_BROKEN"


def test_the_chain_is_bounded():
    chain_keys = {f"k-{index}": new_key() for index in range(MAX_ROTATION_CHAIN + 2)}
    chain = [sign_key_rotation(chain_keys[f"k-{index}"][0], f"k-{index}", chain_keys[f"k-{index + 1}"][1],
                               f"k-{index + 1}", issued_at=ISSUED) for index in range(MAX_ROTATION_CHAIN + 1)]
    trusted = {"k-0": chain_keys["k-0"][1]}
    assert code_of(lambda: resolve_publisher_keys(trusted, chain)) == "KEY_ROTATION_TOO_LONG"
    assert len(resolve_publisher_keys(trusted, chain[:MAX_ROTATION_CHAIN])) == MAX_ROTATION_CHAIN + 1


def test_a_malformed_statement_is_refused(keys):
    statement = rotation(keys, "pub-1", "pub-2")
    statement["rotation"]["note"] = "extra"
    assert code_of(lambda: resolve_publisher_keys({"pub-1": keys["pub-1"][1]}, [statement])) == "KEY_ROTATION_INVALID"


# -- key revocation --------------------------------------------------------------------------


def test_revoking_a_key_revokes_what_it_signed_after_the_point(tmp_path, keys, monkeypatch):
    monkeypatch.setenv("FLYTO_PACK_NO_KEYCHAIN", "1")
    before, before_report = build(tmp_path, keys, "pub-1", "before")
    after, _ = build(tmp_path, keys, "pub-1", "after")
    listing = revocations(keys, [{"key_id": "pub-1", "reason": "key_compromise", "since": ISSUED,
                                  "retained": [before_report["pack_digest"]]}])
    trusted = {"pub-1": keys["pub-1"][1]}
    verify_pack(before, trusted_keys=trusted, revocations=listing)
    assert code_of(lambda: verify_pack(after, trusted_keys=trusted, revocations=listing)) == "PACK_REVOKED"
    target = tmp_path / "space"
    target.mkdir()
    extract_pack_zip(after, target)
    assert code_of(lambda: install_pack(target, trusted_keys=trusted, revocations=listing)) == "PACK_REVOKED"


def test_a_rotation_signed_by_a_revoked_key_after_the_point_is_refused(tmp_path, keys, monkeypatch):
    monkeypatch.setenv("FLYTO_PACK_NO_KEYCHAIN", "1")
    honest = rotation(keys, "pub-1", "pub-2")
    hostile = rotation(keys, "pub-1", "pub-3")
    listing = revocations(keys, [{"key_id": "pub-1", "reason": "key_compromise", "since": ISSUED,
                                  "retained": [rotation_digest(honest)]}])
    trusted = {"pub-1": keys["pub-1"][1]}
    assert set(resolve_publisher_keys(trusted, [honest], revocations=listing)) == {"pub-1", "pub-2"}
    assert code_of(lambda: resolve_publisher_keys(trusted, [hostile], revocations=listing)) == \
        "PUBLISHER_KEY_REVOKED"
    # A pack signed by the honestly rotated key is unaffected by the old key's revocation.
    zip_path, _ = build(tmp_path, keys, "pub-2", "rotated")
    verify_pack(zip_path, trusted_keys=trusted, key_rotations=[honest], revocations=listing)


def test_a_v1_list_still_loads_and_revokes_no_key(keys):
    document = sign_revocations([], keys["revoker"][0], "revoker", sequence=1, issued_at=ISSUED)
    assert document["schema"] == "flyto.pack-revocations.v1"
    listing = load_revocations(document, {"revoker": keys["revoker"][1]})
    assert listing.revoked_keys == {}


@pytest.mark.parametrize("entry", [
    {"key_id": "pub-1", "reason": "key_compromise", "since": ISSUED},
    {"key_id": "pub-1", "reason": "because", "since": ISSUED, "retained": []},
    {"key_id": "pub-1", "reason": "key_compromise", "since": "yesterday", "retained": []},
    {"key_id": "pub-1", "reason": "key_compromise", "since": ISSUED, "retained": ["sha256:XYZ"]},
])
def test_a_malformed_key_revocation_is_refused(keys, entry):
    assert code_of(lambda: sign_revocations([], keys["revoker"][0], "revoker", sequence=1, issued_at=ISSUED,
                                            revoked_keys=[entry])) == "REVOCATION_INVALID"


def test_a_v2_list_that_was_changed_is_refused(keys):
    document = sign_revocations([], keys["revoker"][0], "revoker", sequence=1, issued_at=ISSUED,
                                revoked_keys=[{"key_id": "pub-1", "reason": "key_compromise", "since": ISSUED,
                                               "retained": []}])
    document["list"]["revoked_keys"] = []
    assert code_of(lambda: load_revocations(document, {"revoker": keys["revoker"][1]})) == \
        "REVOCATION_SIGNATURE_MISMATCH"
