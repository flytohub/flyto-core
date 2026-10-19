"""J17 adapter developer kit: the template pack conforms, and each check catches the break it names.

A conformance suite that has only ever passed is not evidence that it checks
anything, so every check is also run against a copy of the template broken in
exactly the way that check exists to catch.
"""

import json
import re
import shutil
from pathlib import Path

import pytest

from core.pack import compatibility
from core.pack.conformance import conform_async, probe_arguments
from core.pack.manifest import (
    MANIFEST_FILENAME,
    SIGNATURE_FILENAME,
    pack_tree_digest,
    validate_pack_manifest,
)
from core.pack.signature import sign_manifest

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "examples" / "packs" / "adapter-template"
MATRIX_DOC = ROOT / "docs" / "specs" / "ADAPTER_COMPATIBILITY_MATRIX.md"
needs_python3 = pytest.mark.skipif(shutil.which("python3") is None, reason="python3 is not on PATH")


@pytest.fixture(autouse=True)
def host_2_40(monkeypatch):
    import core.pack.host as host

    monkeypatch.setattr(host, "_host_version", lambda: "2.40.0")


def copy(tmp_path):
    pack = tmp_path / "pack"
    shutil.copytree(TEMPLATE, pack, ignore=shutil.ignore_patterns("__pycache__"))
    return pack


def edit_manifest(pack, change):
    raw = json.loads((pack / MANIFEST_FILENAME).read_text())
    change(raw)
    (pack / MANIFEST_FILENAME).write_text(json.dumps(raw), encoding="utf-8")


def edit_runner(pack, old, new):
    path = pack / "runner" / "main.py"
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def verdicts(report):
    return {item["check"]: item["verdict"] for item in report["results"]}


@needs_python3
async def test_the_template_conforms_and_never_claims_hardware():
    report = await conform_async(TEMPLATE)
    assert report["conformant"], report
    assert report["evidence_level"] == "D2"
    assert report["hardware_acceptance"] == "NOT_VERIFIED"
    assert verdicts(report)["refuses_out_of_bounds"] == "pass"
    assert verdicts(report)["tree_digest"] == "not_applicable"


@needs_python3
async def test_a_runner_that_clamps_instead_of_refusing_fails(tmp_path):
    pack = copy(tmp_path)
    edit_runner(pack, 'raise RefusedError("OUT_OF_BOUNDS"', 'target = max(low, min(high, target))  # clamped\n            raise_ = ("OUT_OF_BOUNDS"')
    report = await conform_async(pack)
    assert verdicts(report)["refuses_out_of_bounds"] == "fail"
    assert not report["conformant"]


@needs_python3
async def test_a_runner_that_refuses_everything_fails_in_bounds(tmp_path):
    pack = copy(tmp_path)
    edit_runner(pack, "if not low <= target <= high:", "if True:")
    report = await conform_async(pack)
    assert verdicts(report)["completes_in_bounds"] == "fail"


@needs_python3
async def test_a_stop_that_does_not_answer_ok_fails(tmp_path):
    pack = copy(tmp_path)
    edit_runner(pack, "    AXIS.halt()\n", "    raise RefusedError('BUSY', 'cannot stop now')\n")
    assert verdicts(await conform_async(pack))["safe_stop_answers"] == "fail"


@needs_python3
async def test_a_runner_that_dies_instead_of_answering_fails(tmp_path):
    pack = copy(tmp_path)
    edit_runner(pack, 'def read_position(_params: dict) -> dict:\n', 'def read_position(_params: dict) -> dict:\n    raise SystemExit(3)\n')
    assert verdicts(await conform_async(pack))["answers"] == "fail"


async def test_a_pack_that_needs_a_stop_but_declares_none_fails(tmp_path):
    pack = copy(tmp_path)
    edit_manifest(pack, lambda raw: raw.update(modules=[m for m in raw["modules"] if m["module_id"] != "positioner.halt"]))
    assert verdicts(await conform_async(pack, run=False))["safe_stop_declared"] == "fail"


async def test_an_actuation_with_no_evidence_fails(tmp_path):
    pack = copy(tmp_path)
    edit_manifest(pack, lambda raw: raw["modules"][0]["contract"].pop("evidence"))
    assert verdicts(await conform_async(pack, run=False))["evidence_declared"] == "fail"


@pytest.mark.parametrize("min_host,needle", [("2.37.0", "older than 2.40.0"), (None, "no min_host")])
async def test_a_min_host_older_than_the_features_used_fails(tmp_path, min_host, needle):
    pack = copy(tmp_path)
    edit_manifest(pack, lambda raw: raw["pack"].update(min_host=min_host) if min_host else raw["pack"].pop("min_host"))
    report = await conform_async(pack, run=False)
    result = next(item for item in report["results"] if item["check"] == "compatibility")
    assert result["verdict"] == "fail" and needle in result["detail"]


@pytest.mark.parametrize("key,value", [("establishes", ["axis.positioned"]), ("occupies", ["axis"])])
async def test_a_pack_using_resource_states_needs_the_host_that_admits_them(tmp_path, key, value):
    # A 2.40 host refuses `establishes` / `occupies` with a closed-schema error,
    # so a pack that declares either and promises 2.40.0 breaks every 2.40 host.
    pack = copy(tmp_path)
    edit_manifest(pack, lambda raw: raw["modules"][0]["contract"].update({key: value}))
    manifest = validate_pack_manifest(json.loads((pack / MANIFEST_FILENAME).read_text()))
    assert compatibility.required_host(manifest) == ("2.41.0", ["contract.resource_states"])
    report = await conform_async(pack, run=False)
    result = next(item for item in report["results"] if item["check"] == "compatibility")
    assert result["verdict"] == "fail" and "older than 2.41.0" in result["detail"]


async def test_changed_files_fail_the_digest_and_a_valid_signature_passes(tmp_path, keypair):
    private, public = keypair
    pack = copy(tmp_path)
    raw = json.loads((pack / MANIFEST_FILENAME).read_text())
    raw["artifact"] = {"digest": pack_tree_digest(pack)}
    (pack / MANIFEST_FILENAME).write_text(json.dumps(raw), encoding="utf-8")
    signature = sign_manifest(validate_pack_manifest(raw), private, "vendor")
    (pack / SIGNATURE_FILENAME).write_text(json.dumps(signature), encoding="utf-8")
    signed = verdicts(await conform_async(pack, trusted_keys={"vendor": public}, run=False))
    assert signed["tree_digest"] == "pass" and signed["signature"] == "pass"
    (pack / "README.md").write_text("changed after signing", encoding="utf-8")
    assert verdicts(await conform_async(pack, run=False))["tree_digest"] == "fail"


async def test_an_invalid_manifest_stops_at_the_first_check(tmp_path):
    pack = copy(tmp_path)
    edit_manifest(pack, lambda raw: raw.update(schema="flyto.pack.v0"))
    report = await conform_async(pack)
    assert [item["check"] for item in report["results"]] == ["manifest"]
    assert not report["conformant"]


def test_probe_arguments_stay_inside_and_step_outside_the_published_bounds():
    row = validate_pack_manifest(json.loads((TEMPLATE / MANIFEST_FILENAME).read_text()))["modules"][1]
    assert row["module_id"] == "positioner.move_to"
    assert probe_arguments(row) == {"target_mm": 150.0}
    assert probe_arguments(row, outside="target_mm")["target_mm"] > 300


def test_the_template_needs_exactly_what_its_min_host_says():
    manifest = validate_pack_manifest(json.loads((TEMPLATE / MANIFEST_FILENAME).read_text()))
    assert compatibility.required_host(manifest) == ("2.40.0", ["evidence.display_keys"])
    assert manifest["pack"]["min_host"] == "2.40.0"


def test_the_matrix_page_writes_no_matrix_by_hand():
    """The feature table is generated (docs/reference/pack-compatibility-matrix.*); the spec page links it."""
    text = MATRIX_DOC.read_text(encoding="utf-8")
    assert f"Matrix version: **{compatibility.MATRIX_VERSION}**" in text
    assert re.findall(r"^\| `([a-z0-9_.]+)` \| ([0-9.]+) \|", text, re.M) == []
    assert "../reference/pack-compatibility-matrix.md" in text


def test_the_cli_exit_code_follows_the_verdict(tmp_path, capsys):
    from cli.pack import run_pack_command

    class Args:
        pack_action, pack_dir, trusted_key, static_only, json = "conform", str(TEMPLATE), [], True, True

    assert run_pack_command(Args) == 0
    assert json.loads(capsys.readouterr().out)["conformant"] is True
    pack = copy(tmp_path)
    edit_manifest(pack, lambda raw: raw["modules"][0]["contract"].pop("evidence"))
    Args.pack_dir = str(pack)
    assert run_pack_command(Args) == 1
