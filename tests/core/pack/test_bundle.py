"""``flyto.bundle.v1``: packs referenced by id, pinned version and digest, plus workflows and templates."""

import json
import shutil
import zipfile

import pytest
from portable_helpers import LOCK, ROOT, example_source

from core.pack.bundle import BUNDLE_FILENAME, build_bundle, verify_bundle
from core.pack.manifest import PackManifestError
from core.pack.portable import build_portable_pack
from core.pack.supply_chain import load_revocations, sign_revocations

EXAMPLE_BUNDLE = ROOT / "examples" / "bundles" / "rating-review"
CORE_IDS = frozenset({"string.uppercase"})


def code_of(call):
    with pytest.raises(PackManifestError) as info:
        call()
    return info.value.code


@pytest.fixture
def pack_zip(tmp_path):
    out = tmp_path / "ratings.zip"
    build_portable_pack(example_source(tmp_path), out, lockfile=LOCK)
    return out


def bundle_source(tmp_path, mutate=None, name="bundle-src"):
    target = tmp_path / name
    shutil.copytree(EXAMPLE_BUNDLE, target)
    if mutate is not None:
        doc = json.loads((target / BUNDLE_FILENAME).read_text(encoding="utf-8"))
        mutate(doc, target)
        (target / BUNDLE_FILENAME).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return target


def build(tmp_path, pack_zip, mutate=None, name="bundle"):
    out = tmp_path / f"{name}.zip"
    report = build_bundle(bundle_source(tmp_path, mutate, name=f"{name}-src"), out, packs=[pack_zip],
                          require_signature=False, core_module_ids=CORE_IDS)
    return out, report


def test_the_example_bundle_builds_and_verifies(tmp_path, pack_zip):
    out, report = build(tmp_path, pack_zip)
    with zipfile.ZipFile(out) as archive:
        names = sorted(archive.namelist())
        manifest = json.loads(archive.read(BUNDLE_FILENAME))
    # Referenced, never copied: no pack file is inside the bundle.
    assert names == [BUNDLE_FILENAME, "templates/rating-summary.md", "workflows/rating-review.json"]
    pinned = manifest["packs"][0]
    assert pinned["id"] == "com.example.ratings" and pinned["version"] == "0.1.0"
    assert pinned["digest"] == report["packs"][0]["digest"]
    assert all(item["digest"].startswith("sha256:") for item in manifest["workflows"] + manifest["templates"])
    verified = verify_bundle(out, packs=[pack_zip], require_signature=False, core_module_ids=CORE_IDS)
    assert verified["bundle_id"] == "com.example.rating-review"
    assert verified["workflows"][0]["modules"] == ["ratings.company.get", "ratings.findings.list", "string.uppercase"]


def test_core_modules_come_from_the_registry_by_default(tmp_path, pack_zip):
    out, _ = build(tmp_path, pack_zip)
    assert verify_bundle(out, packs=[pack_zip], require_signature=False)["workflows"][0]["name"] == "rating-review"


def test_a_tampered_pack_is_refused(tmp_path, pack_zip):
    out, _ = build(tmp_path, pack_zip)

    def mutate(doc):
        doc["connector"]["operations"][0]["description"] = "Changed after the bundle pinned it."
    other = tmp_path / "other.zip"
    build_portable_pack(example_source(tmp_path, mutate=mutate, name="tampered-src"), other, lockfile=LOCK)
    assert code_of(lambda: verify_bundle(out, packs=[other], require_signature=False,
                                         core_module_ids=CORE_IDS)) == "PACK_DIGEST_MISMATCH"


def test_a_pinned_digest_that_does_not_match_is_refused_at_build(tmp_path, pack_zip):
    def mutate(doc, root):
        doc["packs"][0]["digest"] = "sha256:" + "0" * 64
    assert code_of(lambda: build(tmp_path, pack_zip, mutate)) == "PACK_DIGEST_MISMATCH"


def test_a_missing_pack_is_refused(tmp_path, pack_zip):
    out, _ = build(tmp_path, pack_zip)
    assert code_of(lambda: verify_bundle(out, packs=[], require_signature=False,
                                         core_module_ids=CORE_IDS)) == "PACK_NOT_FOUND"


def test_a_workflow_using_a_module_nobody_provides_is_refused(tmp_path, pack_zip):
    def mutate(doc, root):
        path = root / "workflows" / "rating-review.json"
        workflow = json.loads(path.read_text())
        workflow["steps"].append({"id": "x", "module": "ratings.company.delete", "params": {}})
        path.write_text(json.dumps(workflow))
    with pytest.raises(PackManifestError) as info:
        build(tmp_path, pack_zip, mutate)
    assert info.value.code == "MODULE_NOT_PROVIDED"
    assert "ratings.company.delete" in str(info.value)


def test_a_module_smuggled_in_an_inline_workflow_is_found(tmp_path, pack_zip):
    def mutate(doc, root):
        path = root / "workflows" / "rating-review.json"
        workflow = json.loads(path.read_text())
        inline = json.dumps({"steps": [{"id": "y", "module": "shell.exec", "params": {}}]})
        workflow["steps"].append({"id": "x", "module": "string.uppercase",
                                  "params": {"workflow_source": inline}})
        path.write_text(json.dumps(workflow))
    assert code_of(lambda: build(tmp_path, pack_zip, mutate)) == "MODULE_NOT_PROVIDED"


@pytest.mark.parametrize("mutate", [
    lambda doc, root: doc["workflows"].append(dict(doc["workflows"][0])),
    lambda doc, root: doc["templates"].append({"name": "rating-review", "path": "templates/rating-summary.md"}),
    lambda doc, root: doc["packs"].append({"id": "com.example.ratings", "version": "0.2.0"}),
    lambda doc, root: doc["templates"].append({"name": "other", "path": "workflows/rating-review.json"}),
])
def test_duplicate_names_are_refused(tmp_path, pack_zip, mutate):
    assert code_of(lambda: build(tmp_path, pack_zip, mutate)) == "DUPLICATE_NAME"


@pytest.mark.parametrize("version", ["^0.1.0", "0.1", "latest", ">=0.1.0"])
def test_a_pack_version_must_be_pinned(tmp_path, pack_zip, version):
    def mutate(doc, root):
        doc["packs"][0]["version"] = version
    assert code_of(lambda: build(tmp_path, pack_zip, mutate)) == "VERSION_NOT_PINNED"


def _rewrite(src, dest, name, data):
    with zipfile.ZipFile(src) as archive:
        entries = [(info, archive.read(info.filename)) for info in archive.infolist()]
    with zipfile.ZipFile(dest, "w") as archive:
        for info, content in entries:
            archive.writestr(info, data if info.filename == name else content)
        if name not in {info.filename for info, _ in entries}:
            archive.writestr(name, data)


@pytest.mark.parametrize("name, code", [
    ("workflows/rating-review.json", "WORKFLOW_DIGEST_MISMATCH"),
    ("templates/rating-summary.md", "TEMPLATE_DIGEST_MISMATCH"),
    ("notes/extra.txt", "UNDECLARED_FILE"),
])
def test_a_changed_or_added_bundle_file_is_refused(tmp_path, pack_zip, name, code):
    out, _ = build(tmp_path, pack_zip)
    bad = tmp_path / "bad.zip"
    _rewrite(out, bad, name, b'{"steps": []}')
    assert code_of(lambda: verify_bundle(bad, packs=[pack_zip], require_signature=False,
                                         core_module_ids=CORE_IDS)) == code


def test_a_bundle_never_copies_a_pack(tmp_path, pack_zip):
    def mutate(doc, root):
        shutil.copy(pack_zip, root / "ratings.zip")
    assert code_of(lambda: build(tmp_path, pack_zip, mutate)) == "UNDECLARED_FILE"


def test_a_revoked_pack_in_a_bundle_is_refused(tmp_path, pack_zip, keypair):
    out, report = build(tmp_path, pack_zip)
    private, public = keypair
    doc = sign_revocations([{"digest": report["packs"][0]["digest"], "reason": "vulnerable"}], private, "r-1",
                           sequence=1, issued_at="2026-10-19T00:00:00Z")
    revocations = load_revocations(doc, {"r-1": public})
    assert code_of(lambda: verify_bundle(out, packs=[pack_zip], require_signature=False, revocations=revocations,
                                         core_module_ids=CORE_IDS)) == "PACK_REVOKED"


def test_a_signed_bundle_verifies_and_a_changed_one_does_not(tmp_path, pack_zip, keypair):
    private, public = keypair
    out = tmp_path / "signed.zip"
    build_bundle(bundle_source(tmp_path), out, packs=[pack_zip], require_signature=False,
                 core_module_ids=CORE_IDS, private_key=private, key_id="bundler-1")
    keys = {"bundler-1": public}
    report = verify_bundle(out, packs=[pack_zip], trusted_keys=keys, require_signature=False,
                           require_bundle_signature=True, core_module_ids=CORE_IDS)
    assert report["signature"]["key_id"] == "bundler-1"
    assert code_of(lambda: verify_bundle(out, packs=[pack_zip], trusted_keys={}, require_signature=False,
                                         require_bundle_signature=True, core_module_ids=CORE_IDS)) == "UNTRUSTED_KEY"
    unsigned, _ = build(tmp_path, pack_zip, name="unsigned")
    assert code_of(lambda: verify_bundle(unsigned, packs=[pack_zip], require_signature=False,
                                         require_bundle_signature=True, core_module_ids=CORE_IDS)) == "UNSIGNED"


def test_the_bundle_cli_builds_and_verifies(tmp_path, pack_zip, capsys):
    import argparse

    from cli.pack import run_bundle_command

    out = tmp_path / "cli-bundle.zip"
    build_args = argparse.Namespace(bundle_action="build", source=str(bundle_source(tmp_path)), output=str(out),
                                    pack=[str(pack_zip)], trusted_key=[], allow_unsigned=True, key=None,
                                    key_id=None)
    assert run_bundle_command(build_args) == 0
    assert json.loads(capsys.readouterr().out)["bundle_id"] == "com.example.rating-review"
    verify_args = argparse.Namespace(bundle_action="verify", source=str(out), pack=[str(pack_zip)], trusted_key=[],
                                     allow_unsigned=True, revocations=None, revocation_key=[])
    assert run_bundle_command(verify_args) == 0
    assert json.loads(capsys.readouterr().out)["packs"][0]["id"] == "com.example.ratings"
    verify_args.pack = []
    assert run_bundle_command(verify_args) == 1
    assert "PACK_NOT_FOUND" in capsys.readouterr().err
