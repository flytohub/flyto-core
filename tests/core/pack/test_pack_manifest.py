"""flyto.pack.v1 manifest validation, normalization and the pack tree digest."""

import copy
import json
import os
from pathlib import Path

import pytest

from core.pack.manifest import (
    MODULE_DEFAULTS,
    PackManifestError,
    manifest_sha256,
    pack_tree_digest,
    read_pack_manifest,
    validate_pack_manifest,
)

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "packs" / "node-greeter"


def base(**overrides):
    manifest = {
        "schema": "flyto.pack.v1",
        "pack": {"id": "com.example.fake", "version": "0.1.0", "namespaces": ["fake"]},
        "runtime": {"binding": "subprocess-jsonrpc", "language": "python", "entry": "main.py"},
        "modules": [{"module_id": "fake.echo"}],
    }
    manifest.update(overrides)
    return manifest


def refused(manifest, code):
    with pytest.raises(PackManifestError) as info:
        validate_pack_manifest(manifest)
    assert info.value.code == code, (info.value.code, str(info.value))
    return info.value


def test_example_manifest_validates_and_normalizes():
    manifest = read_pack_manifest(EXAMPLE)
    assert manifest["pack"]["id"] == "com.example.greeter"
    assert [row["module_id"] for row in manifest["modules"]] == ["greeter.greet", "greeter.repeat"]
    for row in manifest["modules"]:
        assert set(MODULE_DEFAULTS) | {"module_id", "label", "label_key", "category"} == set(row)
    greet = manifest["modules"][0]
    assert greet["contract"]["schema"] == "flyto.capability-contract.v1"
    assert greet["label_key"] == "modules.greeter.greet.label"
    assert greet["can_receive_from"] == ["*"]
    assert greet["max_retries"] == 0


def test_minimal_row_gets_decorator_defaults():
    row = validate_pack_manifest(base())["modules"][0]
    assert row["label"] == "fake.echo"
    assert row["category"] == "fake"
    assert row["version"] == "1.0.0"
    assert row["stability"] == "stable"
    assert row["params_schema"] == {}
    assert row["contract"] is None


def test_runtime_defaults():
    manifest = validate_pack_manifest(base())
    assert manifest["runtime"]["request_timeout_ms"] == 30000
    http = validate_pack_manifest(base(runtime={"binding": "http", "locality": "same_host"}))
    assert http["runtime"]["max_response_bytes"] == 1024 * 1024


def test_normalization_is_idempotent_and_order_free():
    once = validate_pack_manifest(base())
    assert validate_pack_manifest(copy.deepcopy(once)) == once
    shuffled = json.loads(json.dumps(base(), sort_keys=True))
    assert manifest_sha256(validate_pack_manifest(shuffled)) == manifest_sha256(once)


def test_schema_is_checked_first():
    refused(base(schema="flyto.plugin.v1", junk=1), "UNSUPPORTED_SCHEMA")


@pytest.mark.parametrize(
    "mutate, code",
    [
        (lambda m: m.update(extra=1), "UNKNOWN_KEY"),
        (lambda m: m["pack"].update(id="Bad Id"), "INVALID_PACK_ID"),
        (lambda m: m["pack"].update(version="1"), "INVALID_SEMVER"),
        (lambda m: m["pack"].update(namespaces=["shell"]), "INVALID_NAMESPACE"),
        (lambda m: m["pack"].update(namespaces=["browser"]), "INVALID_NAMESPACE"),
        (lambda m: m["pack"].update(namespaces=[]), "INVALID_NAMESPACE"),
        (lambda m: m["modules"][0].update(module_id="other.echo"), "MODULE_NAMESPACE_MISMATCH"),
        (lambda m: m["modules"][0].update(unknown=1), "UNKNOWN_KEY"),
        (lambda m: m["modules"][0].update(retryable="true"), "INVALID_BOOLEAN"),
        (lambda m: m["modules"][0].update(timeout_ms=0), "INVALID_BOUND"),
        (lambda m: m["modules"].append({"module_id": "fake.echo"}), "DUPLICATE_ID"),
        (lambda m: m.update(modules=[]), "INVALID_COUNT"),
        (lambda m: m["runtime"].update(entry="../escape.py"), "INVALID_RUNTIME"),
        (lambda m: m["runtime"].update(entry="/abs/main.py"), "INVALID_RUNTIME"),
        (lambda m: m["runtime"].update(binding="carrier-pigeon"), "INVALID_RUNTIME"),
        (lambda m: m["runtime"].update(request_timeout_ms=10), "INVALID_BOUND"),
        (lambda m: m.update(artifact={"digest": "md5:abc"}), "INVALID_DIGEST"),
        (lambda m: m["modules"][0].update(params_schema={"bad name": {"type": "string"}}), "INVALID_PARAMS_SCHEMA"),
        (lambda m: m["modules"][0].update(params_schema={"x": {"label": "no type"}}), "INVALID_PARAMS_SCHEMA"),
        (lambda m: m["modules"][0].update(params_schema={"__event__": {"type": "string"}}), "INVALID_PARAMS_SCHEMA"),
        (lambda m: m["modules"][0].update(description="evil‮text"), "INVALID_TEXT"),
    ],
)
def test_refusals(mutate, code):
    manifest = base()
    mutate(manifest)
    refused(manifest, code)


def test_contract_needs_capability_and_is_validated():
    contract = {
        "actuates": True,
        "safety_class": "movement",
        "requires_safe_stop": True,
        "cancellable": True,
        "idempotent": False,
    }
    manifest = base()
    manifest["modules"][0]["contract"] = contract
    refused(manifest, "INVALID_CONTRACT")

    manifest["modules"][0]["provides_capability"] = "fake.move"
    manifest["modules"][0]["params_schema"] = {"distance": {"type": "number"}}
    # An actuating contract's numeric parameter must declare finite bounds —
    # the same rule @register_module applies.
    refused(manifest, "INVALID_CONTRACT")

    manifest["modules"][0]["params_schema"] = {"distance": {"type": "number", "min": 0, "max": 1}}
    row = validate_pack_manifest(manifest)["modules"][0]
    assert row["contract"]["safety_class"] == "movement"


def test_error_messages_do_not_reflect_values():
    manifest = base()
    manifest["pack"]["id"] = "SECRET-VALUE-123"
    error = refused(manifest, "INVALID_PACK_ID")
    assert "SECRET-VALUE-123" not in str(error)


def test_localized_label_is_accepted():
    manifest = base()
    manifest["modules"][0]["label"] = {"en": "Echo", "zh-TW": "回聲"}
    assert validate_pack_manifest(manifest)["modules"][0]["label"]["zh-TW"] == "回聲"


def test_duplicate_json_keys_are_refused(tmp_path):
    (tmp_path / "flyto-pack.json").write_text(
        '{"schema": "flyto.pack.v1", "schema": "flyto.pack.v1"}', encoding="utf-8"
    )
    with pytest.raises(PackManifestError) as info:
        read_pack_manifest(tmp_path)
    assert info.value.code == "DUPLICATE_KEY"


def test_tree_digest_covers_files_but_not_manifest_or_signature(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "util.py").write_text("x = 1\n", encoding="utf-8")
    first = pack_tree_digest(tmp_path)
    (tmp_path / "flyto-pack.json").write_text("{}", encoding="utf-8")
    (tmp_path / "flyto-pack.sig.json").write_text("{}", encoding="utf-8")
    assert pack_tree_digest(tmp_path) == first
    (tmp_path / "lib" / "util.py").write_text("x = 2\n", encoding="utf-8")
    assert pack_tree_digest(tmp_path) != first
    assert first.startswith("sha256:") and len(first) == 71


def test_tree_digest_refuses_symlinks(tmp_path):
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    os.symlink("/etc/hosts", tmp_path / "linked")
    with pytest.raises(PackManifestError) as info:
        pack_tree_digest(tmp_path)
    assert info.value.code in ("PACK_SYMLINK", "FILE_UNREADABLE")


def test_manifest_symlink_is_refused(tmp_path):
    real = tmp_path / "real.json"
    real.write_text(json.dumps(base()), encoding="utf-8")
    pack = tmp_path / "pack"
    pack.mkdir()
    os.symlink(real, pack / "flyto-pack.json")
    with pytest.raises(PackManifestError) as info:
        read_pack_manifest(pack)
    assert info.value.code == "FILE_UNREADABLE"
