"""Adapter upgrade compatibility: a pack says which versions it upgrades from and which it may roll back to.

``upgrade.supersedes`` names the earlier versions a pack upgrades from;
``upgrade.rollback`` the earlier versions it may be replaced by again;
``upgrade.migrations`` the stored state that changes between them. A host
refuses an upgrade the new version does not declare (``UPGRADE_UNDECLARED``)
and a downgrade the running version does not declare
(``ROLLBACK_UNDECLARED``). The path is tested the way a Space runs it: every
version is kept beside the others, the running one is uninstalled, and the
chosen one is installed with ``upgrade_from`` naming what ran.
"""

import json
import shutil
from pathlib import Path

import pytest

from core.pack.compatibility import required_host
from core.pack.host import install_pack, installed_packs, uninstall_pack
from core.pack.manifest import PackManifestError, read_pack_manifest, validate_pack_manifest
from core.pack.upgrade import TRANSITIONS, check_transition

#: The adapter template, a subprocess-jsonrpc device pack.
TEMPLATE = Path(__file__).resolve().parents[3] / "examples" / "packs" / "adapter-template"


def code_of(call):
    with pytest.raises(PackManifestError) as info:
        call()
    return info.value.code


def version_dir(tmp_path, version, upgrade=None):
    """One version of the template pack, kept beside the others as a Space keeps them."""
    target = tmp_path / "packs" / version
    shutil.copytree(TEMPLATE, target)
    doc = json.loads((target / "flyto-pack.json").read_text(encoding="utf-8"))
    doc["pack"]["version"] = version
    if upgrade is not None:
        doc["upgrade"] = upgrade
        doc["pack"]["min_host"] = "2.41.0"
    (target / "flyto-pack.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return target


def manifest_with(version, upgrade=None):
    doc = json.loads((TEMPLATE / "flyto-pack.json").read_text(encoding="utf-8"))
    doc["pack"]["version"] = version
    if upgrade is not None:
        doc["upgrade"] = upgrade
    return validate_pack_manifest(doc)


# -- declaration ---------------------------------------------------------------------------


def test_the_upgrade_section_is_normalized():
    manifest = manifest_with("0.3.0", {"supersedes": ["0.2.0", "0.1.0"], "rollback": ["0.2.0"],
                                       "migrations": [{"from": "0.1.0", "state": "calibration", "reversible": False}]})
    assert manifest["upgrade"] == {
        "supersedes": ["0.1.0", "0.2.0"], "rollback": ["0.2.0"],
        "migrations": [{"from": "0.1.0", "state": "calibration", "reversible": False}],
    }
    assert "pack.upgrade" in required_host(manifest)[1]


@pytest.mark.parametrize("upgrade", [
    {"supersedes": ["0.3.0"]},                       # not earlier than the pack
    {"supersedes": ["0.1.0", "0.1.0"]},              # twice
    {"supersedes": ["0.1"]},                         # not semver
    {"supersedes": ["0.1.0"], "rollback": ["0.0.9"]},  # rollback to a version it does not supersede
    {"supersedes": ["0.1.0"], "migrations": [{"from": "0.0.9", "state": "x", "reversible": True}]},
    {"supersedes": ["0.1.0"], "migrations": [{"from": "0.1.0", "state": "x"}]},
    {"supersedes": ["0.1.0"], "extra": True},
])
def test_a_malformed_upgrade_section_is_refused(upgrade):
    assert code_of(lambda: manifest_with("0.3.0", upgrade)) == "INVALID_UPGRADE"


def test_rolling_back_across_an_irreversible_migration_cannot_be_declared():
    upgrade = {"supersedes": ["0.1.0", "0.2.0"], "rollback": ["0.1.0"],
               "migrations": [{"from": "0.2.0", "state": "calibration", "reversible": False}]}
    assert code_of(lambda: manifest_with("0.3.0", upgrade)) == "ROLLBACK_IRREVERSIBLE"


# -- transitions ---------------------------------------------------------------------------


def test_the_transitions_are_a_table():
    assert [row.kind for row in TRANSITIONS] == ["same", "upgrade", "rollback"]


def test_a_declared_upgrade_names_its_migrations():
    old = manifest_with("0.1.0")
    new = manifest_with("0.2.0", {"supersedes": ["0.1.0"],
                                  "migrations": [{"from": "0.1.0", "state": "calibration", "reversible": True}]})
    transition = check_transition(old, new)
    assert transition["kind"] == "upgrade"
    assert transition["migrations"] == [{"from": "0.1.0", "state": "calibration", "reversible": True,
                                         "direction": "forward"}]


def test_an_undeclared_upgrade_is_refused():
    assert code_of(lambda: check_transition(manifest_with("0.1.0"), manifest_with("0.2.0"))) == "UPGRADE_UNDECLARED"
    skipping = manifest_with("0.3.0", {"supersedes": ["0.2.0"]})
    assert code_of(lambda: check_transition(manifest_with("0.1.0"), skipping)) == "UPGRADE_UNDECLARED"


def test_a_downgrade_needs_the_running_version_to_declare_it():
    old = manifest_with("0.1.0")
    new = manifest_with("0.2.0", {"supersedes": ["0.1.0"]})
    assert code_of(lambda: check_transition(new, old)) == "ROLLBACK_UNDECLARED"
    allowing = manifest_with("0.2.0", {"supersedes": ["0.1.0"], "rollback": ["0.1.0"]})
    assert check_transition(allowing, old)["kind"] == "rollback"


def test_the_same_version_rebuilt_is_refused():
    one = manifest_with("0.1.0")
    other = validate_pack_manifest({**json.loads(json.dumps(one)), "pack": {**one["pack"], "title": "Rebuilt"}})
    assert check_transition(one, one)["kind"] == "same"
    assert code_of(lambda: check_transition(one, other)) == "VERSION_REBUILT"


def test_another_pack_is_not_an_upgrade():
    other = manifest_with("0.2.0")
    other = validate_pack_manifest({**json.loads(json.dumps(other)), "pack": {**other["pack"], "id": "org.other.x"}})
    assert code_of(lambda: check_transition(manifest_with("0.1.0"), other)) == "PACK_ID_MISMATCH"


# -- through the install-beside model ------------------------------------------------------


@pytest.mark.asyncio
async def test_upgrade_and_rollback_through_install_beside(tmp_path, host_version_241):
    v1 = version_dir(tmp_path, "0.1.0")
    v2 = version_dir(tmp_path, "0.2.0", {"supersedes": ["0.1.0"], "rollback": ["0.1.0"],
                                          "migrations": [{"from": "0.1.0", "state": "position_log",
                                                          "reversible": True}]})
    v3 = version_dir(tmp_path, "0.3.0", {"supersedes": ["0.2.0"]})
    install_pack(v1, require_signature=False)
    running = read_pack_manifest(v1)

    # Undeclared jump 0.1.0 -> 0.3.0: refused before anything is unloaded by a careful host,
    # and refused by install_pack itself for any host that is not careful.
    await uninstall_pack("com.example.positioner")
    assert code_of(lambda: install_pack(v3, require_signature=False, upgrade_from=running)) == "UPGRADE_UNDECLARED"
    assert "com.example.positioner" not in installed_packs()
    install_pack(v1, require_signature=False)

    # Declared upgrade 0.1.0 -> 0.2.0.
    await uninstall_pack("com.example.positioner")
    install_pack(v2, require_signature=False, upgrade_from=running)
    assert installed_packs()["com.example.positioner"].version == "0.2.0"
    running = read_pack_manifest(v2)

    # Declared rollback 0.2.0 -> 0.1.0.
    await uninstall_pack("com.example.positioner")
    install_pack(v1, require_signature=False, upgrade_from=running)
    assert installed_packs()["com.example.positioner"].version == "0.1.0"
    running = read_pack_manifest(v1)

    # 0.3.0 does not declare a rollback to 0.2.0: once on 0.3.0, going back is refused.
    await uninstall_pack("com.example.positioner")
    install_pack(v2, require_signature=False, upgrade_from=running)
    await uninstall_pack("com.example.positioner")
    install_pack(v3, require_signature=False, upgrade_from=read_pack_manifest(v2))
    await uninstall_pack("com.example.positioner")
    assert code_of(lambda: install_pack(v2, require_signature=False, upgrade_from=read_pack_manifest(v3))) == \
        "ROLLBACK_UNDECLARED"
