"""``flyto pack init --template device-adapter``: a non-HTTP device adapter, scaffolded beside the connector one.

The device template writes a module pack: ``modules`` rows that the host
registers through ``@register_module``, each with a
``flyto.capability-contract.v1`` contract, served by a standard-library
runner over JSON-RPC on stdio against a simulated device. As with the
connector template, the consequence of each capability is the author's
decision: no row has a ``safety_class`` until ``flyto pack consequence``
sets it, and until then the pack is refused with ``CONSEQUENCE_MISSING``
naming every undecided module.
"""

import runpy

import pytest
from devkit_helpers import cli, read_json

from core.pack.conformance import conform
from core.pack.manifest import PackManifestError, read_pack_manifest
from core.pack.scaffold import TEMPLATES, init_pack

DECISIONS = ("device.move_to=real_world", "device.read_state=observe", "device.stop=real_world")


def refusal(pack_dir):
    with pytest.raises(PackManifestError) as caught:
        read_pack_manifest(pack_dir)
    return caught.value


def scaffold(tmp_path, name="device-pack"):
    target = tmp_path / name
    assert cli("init", target, "--template", "device-adapter", "--pack-id", "com.example.device") == 0
    return target


def test_the_templates_are_a_table():
    assert set(TEMPLATES) == {"connector", "device-adapter"}


def test_the_device_template_writes_a_module_pack_with_contracts_and_no_consequence(tmp_path):
    target = scaffold(tmp_path)
    document = read_json(target / "flyto-pack.json")
    assert document["runtime"]["binding"] == "subprocess-jsonrpc"
    assert "connector" not in document and "standalone" not in document
    rows = {row["module_id"]: row for row in document["modules"]}
    assert set(rows) == {"device.move_to", "device.read_state", "device.stop"}
    for row in rows.values():
        assert row["provides_capability"] == row["module_id"]
        assert "safety_class" not in row["contract"]
    assert rows["device.stop"]["contract"]["role"] == "safe_stop"
    assert rows["device.move_to"]["contract"]["evidence"]
    assert (target / "runner" / "main.py").is_file()
    assert (target / "tests" / "test_pack.py").is_file()


def test_the_undecided_device_pack_is_refused_naming_every_module(tmp_path):
    error = refusal(scaffold(tmp_path))
    assert error.code == "CONSEQUENCE_MISSING"
    assert set(error.operations) == {"device.move_to", "device.read_state", "device.stop"}


def test_doctor_explains_it(tmp_path, capsys):
    target = scaffold(tmp_path)
    assert cli("doctor", target) == 1
    assert "CONSEQUENCE_MISSING" in capsys.readouterr().out


def test_deciding_every_consequence_makes_it_conformant(tmp_path):
    target = scaffold(tmp_path)
    assert cli("consequence", target, *DECISIONS) == 0
    manifest = read_pack_manifest(target)
    classes = {row["module_id"]: row["contract"]["safety_class"] for row in manifest["modules"]}
    assert classes == {"device.move_to": "movement", "device.read_state": "read_only", "device.stop": "movement"}
    report = conform(target)
    assert report["conformant"], report["results"]
    verdicts = {item["check"]: item["verdict"] for item in report["results"]}
    assert verdicts["refuses_out_of_bounds"] == "pass"
    assert verdicts["safe_stop_answers"] == "pass"


def test_the_scaffolded_test_file_runs_conformance(tmp_path):
    target = scaffold(tmp_path)
    assert cli("consequence", target, *DECISIONS) == 0
    namespace = runpy.run_path(str(target / "tests" / "test_pack.py"))
    namespace["test_the_pack_conforms"]()


def test_a_decision_for_a_module_the_pack_does_not_declare_is_refused(tmp_path, capsys):
    target = scaffold(tmp_path)
    assert cli("consequence", target, "device.fly=observe") == 1
    assert "CONSEQUENCE_TARGET_UNKNOWN" in capsys.readouterr().err


def test_the_device_template_takes_no_openapi_document(tmp_path):
    with pytest.raises(PackManifestError) as caught:
        init_pack(tmp_path / "x", template="device-adapter", openapi=tmp_path / "openapi.yaml")
    assert caught.value.code == "INIT_TEMPLATE_CONFLICT"


def test_an_unknown_template_is_refused(tmp_path):
    with pytest.raises(PackManifestError) as caught:
        init_pack(tmp_path / "x", template="robot")
    assert caught.value.code == "INIT_TEMPLATE_UNKNOWN"


def test_the_scaffold_names_no_vendor(tmp_path):
    target = scaffold(tmp_path)
    text = (target / "flyto-pack.json").read_text(encoding="utf-8") + (target / "runner" / "main.py").read_text(
        encoding="utf-8")
    assert "simulated" in text.lower()


def test_a_decided_and_signed_device_pack_certifies_with_its_runner_as_its_test(tmp_path, keypair):
    """A module pack has no recorded fixtures: conform runs its runner, and pack test does not apply."""
    from cryptography.hazmat.primitives import serialization

    from core.pack.certification import certify, verify_certification

    target = scaffold(tmp_path)
    assert cli("consequence", target, *DECISIONS) == 0
    private, public = keypair
    (tmp_path / "vendor.pem").write_bytes(private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    assert cli("sign", target, "--key", tmp_path / "vendor.pem", "--key-id", "vendor-1") == 0
    report = certify(target, private_key=private, key_id="certifier-1", trusted_keys={"vendor-1": public})
    verdicts = {item["check"]: item["verdict"] for item in report["results"]}
    assert verdicts == {"verify": "pass", "compatibility": "pass", "conform": "pass",
                        "pack_test": "not_applicable", "standalone_health": "not_applicable"}
    assert verify_certification(report["record"], {"certifier-1": public})["pack"]["id"] == "com.example.device"
