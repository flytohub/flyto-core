"""Export: the language-neutral contract a Python pack's decorators produce."""

import argparse
import json

import pytest

from core.modules.registry import ModuleRegistry
from core.pack.export import export_python_pack
from core.pack.manifest import PackManifestError, validate_pack_manifest


def test_export_python_pack(python_greeter_path):
    manifest = export_python_pack(
        "_python_greeter_pack:register_all", pack_id="com.example.greeter", version="0.1.0"
    )
    assert manifest["schema"] == "flyto.pack.v1"
    assert manifest["runtime"] == {"binding": "inprocess-python", "entry_point": "_python_greeter_pack:register_all"}
    assert manifest["pack"]["namespaces"] == ["greeter"]
    assert manifest["pack"]["description"].startswith("Example pack")
    greet = next(row for row in manifest["modules"] if row["module_id"] == "greeter.greet")
    assert greet["contract"]["safety_class"] == "read_only"
    assert greet["params_schema"]["name"]["required"] is True
    # The export is itself a valid manifest, and normalizing it again changes nothing.
    assert validate_pack_manifest(manifest) == manifest
    # The temporary registration is gone afterwards.
    assert ModuleRegistry.has("greeter.greet") is False
    assert "com.example.greeter" not in ModuleRegistry.get_plugins()


def test_export_needs_a_version(python_greeter_path):
    with pytest.raises(PackManifestError) as info:
        export_python_pack("_python_greeter_pack:register_all", pack_id="com.example.greeter")
    assert info.value.code == "INVALID_SEMVER"


def test_export_unknown_target():
    with pytest.raises(PackManifestError) as info:
        export_python_pack("no-such-entry-point")
    assert info.value.code == "INVALID_TARGET"


def test_cli_manifest_command(python_greeter_path, tmp_path, capsys):
    from cli.pack import run_pack_command

    out = tmp_path / "manifest.json"
    args = argparse.Namespace(
        pack_action="manifest",
        target="_python_greeter_pack:register_all",
        pack_id="com.example.greeter",
        version="0.1.0",
        description=None,
        output=str(out),
    )
    assert run_pack_command(args) == 0
    assert json.loads(out.read_text())["pack"]["id"] == "com.example.greeter"


def test_cli_keygen_sign_verify_digest(tmp_path, capsys):
    from pack_helpers import write_pack

    from cli.pack import run_pack_command

    pack, _ = write_pack(tmp_path / "pack", with_digest=False)
    private, public = tmp_path / "k.pem", tmp_path / "k.pub"
    assert run_pack_command(argparse.Namespace(pack_action="keygen", private=str(private), public=str(public))) == 0
    assert oct(private.stat().st_mode & 0o777) == "0o600"
    assert run_pack_command(argparse.Namespace(pack_action="sign", pack_dir=str(pack), key=str(private), key_id="cli-key")) == 0
    capsys.readouterr()
    verify = argparse.Namespace(
        pack_action="verify", pack_dir=str(pack), trusted_key=[f"cli-key={public}"], allow_unsigned=False
    )
    assert run_pack_command(verify) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["signature"]["key_id"] == "cli-key"
    assert run_pack_command(argparse.Namespace(pack_action="digest", pack_dir=str(pack))) == 0
    assert capsys.readouterr().out.strip() == report["artifact_digest"]
    # An untrusted verifier refuses it.
    verify.trusted_key = []
    assert run_pack_command(verify) == 1
