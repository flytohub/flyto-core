"""``flyto pack doctor``: every refusal code has a readable cause and an actionable fix.

One table maps each code to its cause and fix. The completeness test reads
the pack sources themselves: every code a ``_fail(...)`` or
``PackManifestError(...)`` call can raise must have a row, and a row for a
code nothing raises is stale. A code chosen at run time (a table lookup, a
passed-through code) is allowed only at the known call sites listed here,
each tied to the table its codes come from, so a new dynamic site fails this
test until it is accounted for.
"""

import ast
import json
from pathlib import Path

import pytest
from devkit_helpers import ROOT, cli, decided_scaffold, edit_json, operation

from core.pack import bundle, doctor, supply_chain
from core.pack.recorded import TEST_FAILURES
from core.pack.scaffold import SCAFFOLD_REFUSALS

PACK_SOURCES = ROOT / "src" / "core" / "pack"
PLUGIN_MANIFEST = ROOT / "src" / "core" / "plugin" / "manifest.py"
RAISERS = frozenset({"_fail", "PackManifestError"})
FORWARDERS = frozenset({"_fail", "_safe_text"})


def _name(func):
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None


def _literal_codes(node):
    """The codes an argument expression can be: string constants, through conditionals; None when dynamic."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        body, orelse = _literal_codes(node.body), _literal_codes(node.orelse)
        return None if body is None or orelse is None else body | orelse
    return None


def _raised_codes(path, *, within=None):
    """``(static codes, dynamic call sites)`` for every raising call in one source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    if within is not None:
        tree = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == within)
    # A forwarding helper (``def _fail(code, message): raise PackManifestError(code, ...)``)
    # raises what its callers pass; the codes are collected at those callers.
    forwarded = {id(call) for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in FORWARDERS
                 for call in ast.walk(node) if isinstance(call, ast.Call)}
    static, dynamic = set(), set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args or id(node) in forwarded:
            continue
        name = _name(node.func)
        argument = node.args[1] if name == "_safe_text" and len(node.args) > 1 else node.args[0]
        if name not in RAISERS and name != "_safe_text":
            continue
        found = _literal_codes(argument)
        if found is None:
            dynamic.add((path.name, ast.unparse(argument)))
        else:
            static |= found
    return static, dynamic


def _emitted_codes():
    static, dynamic = set(), set()
    for path in sorted(PACK_SOURCES.glob("*.py")):
        codes, sites = _raised_codes(path)
        static |= codes
        dynamic |= sites
    return static, dynamic


def _plugin_endpoint_codes():
    return _raised_codes(PLUGIN_MANIFEST, within="validate_plugin_endpoint")[0]


#: Each call site whose code is chosen at run time, and where its codes come from.
DYNAMIC_SITES = {
    ("bundle.py", "spec['mismatch']"): lambda: {spec["mismatch"] for spec in bundle.ITEM_KINDS.values()},
    ("supply_chain.py", "REVOCATION_SIGNATURE_REFUSALS.get(exc.code, 'REVOCATION_INVALID')"):
        lambda: set(supply_chain.REVOCATION_SIGNATURE_REFUSALS.values()) | {"REVOCATION_INVALID"},
    ("host.py", "exc.code"): _plugin_endpoint_codes,
}


def every_code():
    static, dynamic = _emitted_codes()
    assert dynamic == set(DYNAMIC_SITES), "a refusal code is chosen at run time at a site this test does not know"
    for source in DYNAMIC_SITES.values():
        static |= source()
    return static | set(TEST_FAILURES) | set(SCAFFOLD_REFUSALS)


def test_every_refusal_code_the_validator_can_emit_has_a_row():
    missing = sorted(every_code() - set(doctor.DIAGNOSES))
    assert missing == []


def test_no_row_names_a_code_nothing_emits():
    stale = sorted(set(doctor.DIAGNOSES) - every_code())
    assert stale == []


def test_the_scan_finds_codes_from_every_validating_module():
    static, _ = _emitted_codes()
    # A spot check that the scan is reading the sources, not an empty set.
    assert {"CONSEQUENCE_MISSING", "INVALID_SEMVER", "STANDALONE_DERIVED", "PACK_REVOKED",
            "UNTRUSTED_KEY", "MODULE_NOT_PROVIDED", "INVALID_TEXT", "INVALID_KEY"} <= static


@pytest.mark.parametrize("code", sorted(doctor.DIAGNOSES))
def test_every_row_says_what_happened_and_what_to_do(code):
    row = doctor.DIAGNOSES[code]
    assert row.cause.strip() and row.fix.strip()
    assert row.cause != row.fix
    assert len(row.cause) <= 240 and len(row.fix) <= 320


# -- the command ------------------------------------------------------------------------------


def test_doctor_explains_undecided_consequences_and_names_every_operation(tmp_path, capsys):
    target = tmp_path / "items-pack"
    cli("init", target)
    capsys.readouterr()
    assert cli("doctor", target) == 1
    out = capsys.readouterr().out
    assert "CONSEQUENCE_MISSING" in out
    assert "account.entitlements" in out and "item.get" in out
    assert "flyto pack consequence" in out


def test_doctor_lists_every_operation_level_refusal_at_once(tmp_path):
    target = decided_scaffold(tmp_path)

    def break_two(doc):
        operation(doc, "item.get")["sensitive"] = ["not-a-path"]
        operation(doc, "account.entitlements")["path"] = "/v1/{unknown}"
    edit_json(target / "flyto-pack.json", break_two)
    report = doctor.diagnose(target)
    assert report["valid"] is False
    found = {(item["operation"], item["code"]) for item in report["diagnoses"]}
    assert ("item.get", "INVALID_JSONPATH") in found
    assert ("account.entitlements", "PATH_PARAM_UNDECLARED") in found
    for item in report["diagnoses"]:
        assert item["cause"] and item["fix"]


def test_doctor_on_a_valid_pack_says_so_and_points_at_the_next_step(tmp_path, capsys):
    target = decided_scaffold(tmp_path)
    capsys.readouterr()
    assert cli("doctor", target) == 0
    out = capsys.readouterr().out
    assert "no refusal" in out and "flyto pack test" in out


def test_doctor_json_carries_code_cause_and_fix(tmp_path, capsys):
    target = tmp_path / "items-pack"
    cli("init", target)
    capsys.readouterr()
    cli("doctor", target, "--json")
    report = json.loads(capsys.readouterr().out)
    first = report["diagnoses"][0]
    assert first["code"] == "CONSEQUENCE_MISSING"
    assert first["operations"] == ["account.entitlements", "item.get"]
    assert first["fix"] == doctor.DIAGNOSES["CONSEQUENCE_MISSING"].fix


def test_doctor_explains_an_unknown_code_without_inventing_one():
    entry = doctor.explain("SOMETHING_NEW", "message")
    assert entry["code"] == "SOMETHING_NEW"
    assert entry["cause"] == doctor.UNLISTED.cause


def test_doctor_on_a_missing_directory_is_a_typed_refusal(tmp_path):
    report = doctor.diagnose(Path(tmp_path / "absent"))
    assert report["valid"] is False
    assert report["diagnoses"][0]["code"] in {"FILE_UNREADABLE", "PACK_UNREADABLE"}
