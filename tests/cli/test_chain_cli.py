"""``flyto chain verify``: exit codes 0 verified, 1 refused, 2 incomplete; JSON report on stdout."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cli.chain import run_chain_command

GOLDEN = Path(__file__).resolve().parents[1] / "core" / "chain" / "fixtures" / "golden"
HOST = "host:dev-golden"


def _run(argv, capsys):
    code = run_chain_command(argv)
    return code, json.loads(capsys.readouterr().out)


@pytest.fixture
def bundle(tmp_path):
    keys = tmp_path / "keys.json"
    keys.write_text(json.dumps([json.loads((GOLDEN / "cloud-keys.json").read_text()),
                                json.loads((GOLDEN / "host-keys.json").read_text())]))
    return keys


def test_verified_exits_zero(bundle, capsys):
    code, report = _run(["verify", str(GOLDEN / "record.json"), "--keys", str(bundle)], capsys)
    assert (code, report["result"]) == (0, "verified")


def test_keys_may_be_given_one_document_per_flag(capsys):
    code, _ = _run(["verify", str(GOLDEN / "record.json"), "--keys", str(GOLDEN / "cloud-keys.json"),
                    "--keys", str(GOLDEN / "host-keys.json")], capsys)
    assert code == 0


def test_refused_exits_one(bundle, tmp_path, capsys):
    record = json.loads((GOLDEN / "record.json").read_text())
    record["sections"][0]["body"]["principal"] = "user:someone-else"
    path = tmp_path / "record.json"
    path.write_text(json.dumps(record))
    code, report = _run(["verify", str(path), "--keys", str(bundle)], capsys)
    assert (code, report["result"]) == (1, "refused")


def test_incomplete_exits_two(bundle, tmp_path, capsys):
    from core.chain import section_digest

    record = json.loads((GOLDEN / "record.json").read_text())
    record["sections"] = record["sections"][:-1]
    record["head"] = section_digest(record["sections"][-1])
    path = tmp_path / "record.json"
    path.write_text(json.dumps(record))
    code, report = _run(["verify", str(path), "--keys", str(bundle)], capsys)
    assert (code, report["result"]) == (2, "incomplete")


def test_host_only_trust_from_the_command_line(capsys):
    code, report = _run(["verify", str(GOLDEN / "record.json"), "--keys", str(GOLDEN / "host-keys.json"),
                         "--trust", "host-only"], capsys)
    assert code == 0
    assert report["trust"] == "host-only"


def test_an_unreadable_input_is_refused_not_a_crash(tmp_path, capsys):
    path = tmp_path / "record.json"
    path.write_text("{not json")
    code, report = _run(["verify", str(path), "--keys", str(GOLDEN / "host-keys.json")], capsys)
    assert (code, report["problems"]) == (1, ["CHAIN_INPUT_UNREADABLE"])


def test_the_flyto_entry_point_routes_chain(bundle):
    done = subprocess.run(
        [sys.executable, "-c", "import sys; from cli.main import main; sys.argv[0] = 'flyto'; main()",
         "chain", "verify", str(GOLDEN / "record.json"), "--keys", str(bundle)],
        capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["result"] == "verified"
