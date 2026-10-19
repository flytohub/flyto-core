# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Adapter and firmware upgrade compatibility: what a version upgrades from, and what it may roll back to.

A pack declares, in its ``upgrade`` section::

    "upgrade": {
      "supersedes": ["0.1.0", "0.2.0"],
      "rollback": ["0.2.0"],
      "migrations": [{"from": "0.1.0", "state": "calibration", "reversible": false}]
    }

* ``supersedes`` — the earlier versions this one upgrades from, exactly;
* ``rollback`` — the earlier versions this one may be replaced by again
  (each one it supersedes, no other);
* ``migrations`` — the stored state that changes when upgrading from a
  version (``from`` is one it supersedes; ``state`` names the store;
  ``reversible`` says whether rolling back can undo it). A rollback across
  an irreversible migration cannot be declared (``ROLLBACK_IRREVERSIBLE``).

A host switching versions asks :func:`check_transition` (``install_pack``
does, given ``upgrade_from``). Each row of :data:`TRANSITIONS` names when it
applies, who must declare it, and the refusal when nobody did: an upgrade
the new version does not declare is ``UPGRADE_UNDECLARED``, a downgrade the
running version does not declare is ``ROLLBACK_UNDECLARED``, and the same
version with other content is ``VERSION_REBUILT``. The answer names the
migrations the switch crosses, for the pack's runtime to apply; flyto-core
holds no pack state of its own and runs none of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping

from .compatibility import version_key
from .manifest import _IDENT, _SEMVER, PackManifestError, manifest_sha256

__all__ = ["TRANSITIONS", "Transition", "check_transition", "validate_upgrade"]

MAX_VERSIONS = 64
MAX_MIGRATIONS = 64
_UPGRADE_KEYS = frozenset({"supersedes", "rollback", "migrations"})
_MIGRATION_KEYS = frozenset({"from", "state", "reversible"})

Manifest = Mapping[str, Any]


def _fail(code: str, message: str) -> None:
    raise PackManifestError(code, message)


def _versions(value: Any, where: str, below: str) -> List[str]:
    if type(value) is not list or len(value) > MAX_VERSIONS:
        _fail("INVALID_UPGRADE", f"{where} must be a list of at most {MAX_VERSIONS} versions")
    for item in value:
        if type(item) is not str or not _SEMVER.fullmatch(item):
            _fail("INVALID_UPGRADE", f"{where} holds a version that is not semver")
        if version_key(item) >= version_key(below):
            _fail("INVALID_UPGRADE", f"{where} names {item}, which is not earlier than {below}")
    if len(set(value)) != len(value):
        _fail("INVALID_UPGRADE", f"{where} names a version twice")
    return sorted(value, key=version_key)


def _migration(value: Any, index: int, supersedes: List[str]) -> Dict[str, Any]:
    where = f"upgrade.migrations[{index}]"
    if type(value) is not dict or set(value) != _MIGRATION_KEYS:
        _fail("INVALID_UPGRADE", f"{where} is {{from, state, reversible}}")
    if value["from"] not in supersedes:
        _fail("INVALID_UPGRADE", f"{where}.from must be a version the pack supersedes")
    if type(value["state"]) is not str or len(value["state"]) > 96 or not _IDENT.fullmatch(value["state"]):
        _fail("INVALID_UPGRADE", f"{where}.state must be an identifier")
    if type(value["reversible"]) is not bool:
        _fail("INVALID_UPGRADE", f"{where}.reversible must be true or false")
    return {"from": value["from"], "state": value["state"], "reversible": value["reversible"]}


def validate_upgrade(value: Any, manifest: Manifest) -> Dict[str, Any]:
    """The normalized ``upgrade`` section of ``manifest``, or a typed refusal."""
    version = manifest["pack"]["version"]
    if type(value) is not dict or "supersedes" not in value or not set(value) <= _UPGRADE_KEYS:
        _fail("INVALID_UPGRADE", "upgrade is {supersedes, rollback?, migrations?}")
    supersedes = _versions(value["supersedes"], "upgrade.supersedes", version)
    rollback = _versions(value.get("rollback", []), "upgrade.rollback", version)
    if not set(rollback) <= set(supersedes):
        _fail("INVALID_UPGRADE", "upgrade.rollback names a version the pack does not supersede")
    migrations = value.get("migrations", [])
    if type(migrations) is not list or len(migrations) > MAX_MIGRATIONS:
        _fail("INVALID_UPGRADE", f"upgrade.migrations must be a list of at most {MAX_MIGRATIONS}")
    normalized = [_migration(item, index, supersedes) for index, item in enumerate(migrations)]
    for target in rollback:
        crossed = [item for item in normalized if version_key(item["from"]) >= version_key(target)]
        if any(not item["reversible"] for item in crossed):
            _fail("ROLLBACK_IRREVERSIBLE", f"rolling back to {target} crosses an irreversible migration")
    return {"supersedes": supersedes, "rollback": rollback,
            "migrations": sorted(normalized, key=lambda item: (version_key(item["from"]), item["state"]))}


def _upgrade(manifest: Manifest) -> Mapping[str, Any]:
    return manifest.get("upgrade") or {"supersedes": [], "rollback": [], "migrations": []}


def _crossed(owner: Manifest, since: str, direction: str) -> List[Dict[str, Any]]:
    return [{**item, "direction": direction} for item in _upgrade(owner)["migrations"]
            if version_key(item["from"]) >= version_key(since)]


@dataclass(frozen=True)
class Transition:
    kind: str
    #: Whether this row applies: (running version key, target version key).
    applies: Callable[[tuple, tuple], bool]
    #: Whether the switch is declared: (running manifest, target manifest).
    declared: Callable[[Manifest, Manifest], bool]
    refusal: str
    #: The migrations the switch crosses.
    migrations: Callable[[Manifest, Manifest], List[Dict[str, Any]]]


TRANSITIONS = (
    Transition("same", lambda run, to: to == run,
               lambda running, target: manifest_sha256(running) == manifest_sha256(target), "VERSION_REBUILT",
               lambda running, target: []),
    Transition("upgrade", lambda run, to: to > run,
               lambda running, target: running["pack"]["version"] in _upgrade(target)["supersedes"],
               "UPGRADE_UNDECLARED",
               lambda running, target: _crossed(target, running["pack"]["version"], "forward")),
    Transition("rollback", lambda run, to: to < run,
               lambda running, target: target["pack"]["version"] in _upgrade(running)["rollback"],
               "ROLLBACK_UNDECLARED",
               lambda running, target: _crossed(running, target["pack"]["version"], "reverse")),
)


def check_transition(running: Manifest, target: Manifest) -> Dict[str, Any]:
    """Replace ``running`` with ``target``: the transition and the migrations it crosses, or a typed refusal."""
    if running["pack"]["id"] != target["pack"]["id"]:
        _fail("PACK_ID_MISMATCH", "a version of another pack is not an upgrade")
    run, to = version_key(running["pack"]["version"]), version_key(target["pack"]["version"])
    row = next(item for item in TRANSITIONS if item.applies(run, to))
    if not row.declared(running, target):
        _fail(row.refusal, f"{target['pack']['id']} {running['pack']['version']} -> {target['pack']['version']}: "
              f"the {row.kind} is not declared")
    return {"kind": row.kind, "from": running["pack"]["version"], "to": target["pack"]["version"],
            "migrations": row.migrations(running, target)}
