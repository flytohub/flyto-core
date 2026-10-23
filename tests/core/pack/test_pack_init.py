"""``flyto pack init``: a provider scaffolds its own connector pack, and decides every consequence.

The scaffold is a whole pack in one step: the manifest with its
``connector``, ``entitlements``, ``scopes`` and ``standalone`` sections, a
``fixtures/`` folder of recorded exchanges, and a test file. What it never
writes is a consequence. That is a decision about what a call does to the
world, so every operation starts without one, from the blank template and
from an OpenAPI document alike, and the HTTP method is not read as one. The
pack refuses to validate and to build until the author has set each, and the
refusal names every operation still undecided.
"""

import json
import runpy

import pytest
from devkit_helpers import (
    BLANK_DECISIONS,
    LOCK,
    cli,
    decided_scaffold,
    operation,
    read_json,
    write_json,
)

from core.pack.connector import CONSEQUENCES
from core.pack.manifest import PackManifestError, read_pack_manifest
from core.pack.portable import build_portable_pack

OPENAPI = {
    "openapi": "3.0.3",
    "info": {"title": "Example tracker API", "version": "1.0"},
    "servers": [{"url": "https://api.tracker.example"}],
    "components": {"securitySchemes": {"token": {"type": "http", "scheme": "bearer"}}},
    "paths": {
        "/v1/issues/{issue}": {
            "get": {"operationId": "getIssue", "parameters": [
                {"name": "issue", "in": "path", "required": True, "schema": {"type": "string"}}]},
        },
        "/v1/search": {
            # A POST that only reads, which is why the method is never the decision.
            "post": {"operationId": "searchIssues", "requestBody": {"content": {"application/json": {
                "schema": {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}}}}},
        },
        "/v1/issues/{issue}/close": {
            "post": {"operationId": "closeIssue", "parameters": [
                {"name": "issue", "in": "path", "required": True, "schema": {"type": "string"}}]},
        },
    },
}


def refusal(pack_dir):
    with pytest.raises(PackManifestError) as caught:
        read_pack_manifest(pack_dir)
    return caught.value


# -- the blank template -----------------------------------------------------------


def test_init_writes_a_manifest_fixtures_and_a_test_file(tmp_path):
    target = tmp_path / "items-pack"
    assert cli("init", target, "--pack-id", "com.example.items") == 0
    assert sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()) == [
        "fixtures/exchanges.json", "flyto-pack.json", "tests/test_pack.py",
    ]
    manifest = read_json(target / "flyto-pack.json")
    assert {"connector", "entitlements", "scopes", "standalone"} <= set(manifest)
    assert manifest["pack"]["id"] == "com.example.items"
    assert manifest["runtime"]["binding"] == "connector"
    assert manifest["entitlements"]["probe"] in {op["id"] for op in manifest["connector"]["operations"]}
    assert manifest["standalone"]["lockfile"] == "requirements.lock"
    fixtures = read_json(target / "fixtures" / "exchanges.json")
    assert fixtures["schema"] == "flyto.pack-fixtures.v1"
    assert fixtures["exchanges"] and fixtures["calls"] and fixtures["customers"]


def test_every_scaffolded_operation_starts_with_consequence_unset(tmp_path):
    target = tmp_path / "items-pack"
    cli("init", target)
    operations = read_json(target / "flyto-pack.json")["connector"]["operations"]
    assert len(operations) >= 2
    assert all("consequence" not in op for op in operations)


def test_validation_refuses_and_names_every_undecided_operation(tmp_path):
    target = tmp_path / "items-pack"
    cli("init", target)
    error = refusal(target)
    assert error.code == "CONSEQUENCE_MISSING"
    assert error.operations == ("account.entitlements", "item.get")
    assert error.operation == "account.entitlements"
    assert "account.entitlements" in str(error) and "item.get" in str(error)


def test_the_build_refuses_until_every_consequence_is_set_naming_each(tmp_path, capsys):
    target = tmp_path / "items-pack"
    cli("init", target)
    with pytest.raises(PackManifestError) as caught:
        build_portable_pack(target, tmp_path / "out.zip", lockfile=LOCK)
    assert caught.value.code == "CONSEQUENCE_MISSING"
    assert caught.value.operations == ("account.entitlements", "item.get")

    capsys.readouterr()
    assert cli("build", target, "--lock", LOCK, "-o", tmp_path / "cli.zip") == 1
    err = capsys.readouterr().err
    assert "CONSEQUENCE_MISSING" in err and "account.entitlements" in err and "item.get" in err

    # One decided, one not: still refused, and only the undecided one is named.
    cli("consequence", target, "account.entitlements=observe")
    error = refusal(target)
    assert error.code == "CONSEQUENCE_MISSING" and error.operations == ("item.get",)

    cli("consequence", target, "item.get=observe")
    report = build_portable_pack(target, tmp_path / "out.zip", lockfile=LOCK)
    assert report["pack_id"] == "com.example.items-pack"  # derived from the directory name
    assert (tmp_path / "out.zip").is_file()


def test_the_consequence_command_records_only_what_the_author_decides(tmp_path, capsys):
    target = tmp_path / "items-pack"
    cli("init", target)
    capsys.readouterr()
    assert cli("consequence", target, "item.get=external_write") == 0
    manifest = read_json(target / "flyto-pack.json")
    assert operation(manifest, "item.get")["consequence"] == "external_write"
    assert "consequence" not in operation(manifest, "account.entitlements")
    # A decision can be changed; it is still the author's.
    assert cli("consequence", target, "item.get=observe") == 0
    assert operation(read_json(target / "flyto-pack.json"), "item.get")["consequence"] == "observe"


@pytest.mark.parametrize("decision, code", [
    ("item.get=harmless", "CONSEQUENCE_UNKNOWN"),
    ("nothing.here=observe", "CONSEQUENCE_TARGET_UNKNOWN"),
    ("item.get", "CONSEQUENCE_DECISION_INVALID"),
])
def test_the_consequence_command_refuses_with_a_typed_reason(tmp_path, capsys, decision, code):
    target = tmp_path / "items-pack"
    cli("init", target)
    before = (target / "flyto-pack.json").read_bytes()
    capsys.readouterr()
    assert cli("consequence", target, decision) == 1
    assert f"[{code}]" in capsys.readouterr().err
    assert (target / "flyto-pack.json").read_bytes() == before


def test_every_consequence_level_is_accepted(tmp_path):
    target = tmp_path / "items-pack"
    cli("init", target)
    for level in CONSEQUENCES:
        assert cli("consequence", target, f"item.get={level}") == 0


def test_init_refuses_a_directory_that_is_not_empty(tmp_path, capsys):
    target = tmp_path / "busy"
    target.mkdir()
    (target / "notes.txt").write_text("mine", encoding="utf-8")
    capsys.readouterr()
    assert cli("init", target) == 1
    assert "[INIT_TARGET_NOT_EMPTY]" in capsys.readouterr().err
    assert sorted(p.name for p in target.iterdir()) == ["notes.txt"]


def test_init_refuses_an_invalid_pack_id(tmp_path, capsys):
    capsys.readouterr()
    assert cli("init", tmp_path / "x", "--pack-id", "Not An Id") == 1
    assert "[INVALID_PACK_ID]" in capsys.readouterr().err
    assert not (tmp_path / "x").exists()


def test_the_generated_test_file_runs_the_pack_against_its_fixtures(tmp_path):
    target = decided_scaffold(tmp_path)
    namespace = runpy.run_path(str(target / "tests" / "test_pack.py"))
    namespace["test_the_pack_passes_its_recorded_fixtures"]()


def test_the_decided_scaffold_validates_and_imports_no_host_product(tmp_path):
    target = decided_scaffold(tmp_path)
    manifest = read_pack_manifest(target)
    assert [row["module_id"] for row in manifest["modules"]] == ["items.account.entitlements", "items.item.get"]
    source = (target / "tests" / "test_pack.py").read_text(encoding="utf-8")
    # A pack depends on flyto-core only: never on Flyto2 Cloud or Desktop.
    assert "flyto_cloud" not in source and "desktop" not in source.lower()
    assert "from core.pack" in source


# -- from an OpenAPI document ---------------------------------------------------------


def openapi_scaffold(tmp_path):
    source = tmp_path / "openapi.json"
    source.write_text(json.dumps(OPENAPI), encoding="utf-8")
    target = tmp_path / "tracker-pack"
    assert cli("init", target, "--openapi", source, "--pack-id", "com.example.tracker") == 0
    return target


def test_init_from_openapi_reuses_the_draft_import_and_decides_nothing(tmp_path):
    target = openapi_scaffold(tmp_path)
    manifest = read_json(target / "flyto-pack.json")
    operations = {op["id"]: op for op in manifest["connector"]["operations"]}
    assert set(operations) == {"get_issue", "search_issues", "close_issue"}
    assert manifest["connector"]["base_url"] == "https://api.tracker.example"
    assert manifest["connector"]["auth"][0]["credential"] == "token"
    # A GET, a reading POST and a writing POST: none is guessed.
    assert all("consequence" not in op for op in operations.values())
    assert {"entitlements", "scopes", "standalone"} <= set(manifest)
    error = refusal(target)
    assert error.code == "CONSEQUENCE_MISSING"
    assert error.operations == ("get_issue", "search_issues", "close_issue")  # in the order the file declares


def test_init_from_openapi_writes_one_call_per_operation_and_records_nothing_it_did_not_see(tmp_path):
    target = openapi_scaffold(tmp_path)
    fixtures = read_json(target / "fixtures" / "exchanges.json")
    assert sorted(call["operation"] for call in fixtures["calls"]) == ["close_issue", "get_issue", "search_issues"]
    # No response is invented: the author records what the provider answers.
    assert fixtures["exchanges"] == []


def test_init_from_openapi_names_a_probe_when_told_which(tmp_path):
    source = tmp_path / "openapi.json"
    source.write_text(json.dumps(OPENAPI), encoding="utf-8")
    target = tmp_path / "tracker-pack"
    assert cli("init", target, "--openapi", source, "--probe", "get_issue") == 0
    assert read_json(target / "flyto-pack.json")["entitlements"]["probe"] == "get_issue"


def test_an_openapi_document_that_is_not_openapi_3_is_refused_before_anything_is_written(tmp_path, capsys):
    source = tmp_path / "old.json"
    write_json(source, {"swagger": "2.0", "paths": {}})
    capsys.readouterr()
    assert cli("init", tmp_path / "x", "--openapi", source) == 1
    assert "[UNSUPPORTED_OPENAPI]" in capsys.readouterr().err
    assert not (tmp_path / "x").exists()


def test_the_blank_decisions_cover_every_template_operation(tmp_path):
    target = tmp_path / "items-pack"
    cli("init", target)
    ids = sorted(op["id"] for op in read_json(target / "flyto-pack.json")["connector"]["operations"])
    assert ids == sorted(decision.split("=", 1)[0] for decision in BLANK_DECISIONS)
