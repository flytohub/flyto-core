# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The versioned compatibility matrix: which flyto-core first accepts each pack feature.

A pack's ``min_host`` is a promise to every host that loads it. A pack that
uses evidence display keys but says ``min_host: 2.37.0`` installs on 2.40 and
is refused, with a closed-schema error, by every 2.37–2.39 host in the field.
This table is what ``core.pack.conformance`` reads to catch that before the
pack ships. :func:`compatibility_matrix` turns it into the machine-readable
pack feature x flyto-core version matrix (``flyto.pack-compatibility-matrix.v1``);
``scripts/generate_reference.py`` writes it to
``docs/reference/pack-compatibility-matrix.json`` and ``.md``, and a test
fails when either is stale. Certified packs join the matrix only from
certification records that verified (``core.pack.certification``).

Each row names one feature, the first release that accepts it, and how to
tell from a normalized manifest row (or, for a feature of the pack as a
whole, from the manifest) whether the pack uses it. Rows are only ever added:
a released version never changes what it accepts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Sequence, Tuple

from ..capability_contract import (
    ABSOLUTE_OPS,
    EVIDENCE_DISPLAY_FIELDS,
    OPTIONAL_FIELDS,
    RECOVERY_FIELDS,
    RESOURCE_STATE_FIELDS,
)

MATRIX_VERSION = "1"
MATRIX_SCHEMA = "flyto.pack-compatibility-matrix.v1"
CONFORMANCE_SUITE = "flyto.pack-conformance.v1"

Row = Mapping[str, Any]


def _contract(row: Row) -> Mapping[str, Any]:
    contract = row.get("contract")
    return contract if isinstance(contract, Mapping) else {}


def _evidence(row: Row) -> List[Mapping[str, Any]]:
    return [item for item in _contract(row).get("evidence") or () if isinstance(item, Mapping)]


def _uses_absolute_targets(row: Row) -> bool:
    return any(
        (item.get("measure") or {}).get("op") in ABSOLUTE_OPS or "frame" in (item.get("measure") or {})
        for item in _evidence(row)
    )


_RECOVERY_SEMANTICS = RECOVERY_FIELDS - frozenset(("capabilities", "observe", "guidance"))


def _uses_recovery_semantics(row: Row) -> bool:
    recovery = _contract(row).get("recovery")
    return isinstance(recovery, Mapping) and bool(_RECOVERY_SEMANTICS & set(recovery))


@dataclass(frozen=True)
class Feature:
    feature_id: str
    since: str
    describes: str
    used_by: Callable[[Row], bool]
    #: ``row``: ``used_by`` reads one module row. ``manifest``: it reads the
    #: whole normalized manifest (a binding, a top-level section).
    reads: str = "row"


FEATURES: Tuple[Feature, ...] = (
    Feature("capability_contract.v1", "2.35.0", "`contract` on a module row (`flyto.capability-contract.v1`)",
            lambda row: bool(_contract(row))),
    Feature("contract.optional_fields", "2.36.0", "`role`, `artifacts`, `recovery`, `expected_duration_ms`",
            lambda row: bool(OPTIONAL_FIELDS & set(_contract(row)))),
    Feature("pack.v1", "2.37.0", "`flyto.pack.v1` manifest, `subprocess-jsonrpc` and `http` bindings",
            lambda row: True),
    Feature("evidence.absolute_targets", "2.38.0", "`distance_to` / `angle_to` measure ops, `measure.frame`",
            _uses_absolute_targets),
    Feature("recovery.semantics", "2.39.0", "`recovery.on` / `alternatives` / `preserves` / `resource_scope` / `fills`",
            _uses_recovery_semantics),
    Feature("evidence.display_keys", "2.40.0", "evidence `label`, `unit`, `channel`",
            lambda row: any(EVIDENCE_DISPLAY_FIELDS & set(item) for item in _evidence(row))),
    Feature("contract.resource_states", "2.41.0", "`establishes`, `occupies`",
            lambda row: bool(RESOURCE_STATE_FIELDS & set(_contract(row)))),
    Feature("pack.connector", "2.41.0", "`connector` section and `connector` binding (operations become modules)",
            lambda manifest: (manifest.get("runtime") or {}).get("binding") == "connector", reads="manifest"),
    Feature("pack.entitlements", "2.41.0", "`entitlements` probe and `scopes` sections (the connector pre-check)",
            lambda manifest: bool(manifest.get("entitlements") or manifest.get("scopes")), reads="manifest"),
    Feature("pack.standalone", "2.41.0", "`standalone` section (runs on its own as an MCP server; portable zip)",
            lambda manifest: "standalone" in manifest, reads="manifest"),
    Feature("pack.upgrade", "2.41.0", "`upgrade` section (`supersedes`, `rollback`, `migrations`)",
            lambda manifest: "upgrade" in manifest, reads="manifest"),
)


def version_key(text: Any) -> Tuple[int, ...]:
    """``2.40.0`` -> ``(2, 40, 0)``; anything unreadable sorts lowest."""
    core = str(text or "").split("+", 1)[0].split("-", 1)[0]
    try:
        return tuple(int(part) for part in core.split("."))
    except ValueError:
        return (0,)


def features_used(manifest: Mapping[str, Any]) -> Dict[str, str]:
    """``{feature id: since}`` for every matrix feature ``manifest`` uses."""
    used: Dict[str, str] = {}
    for row in manifest.get("modules") or ():
        for feature in FEATURES:
            if feature.reads == "row" and feature.used_by(row):
                used[feature.feature_id] = feature.since
    for feature in FEATURES:
        if feature.reads == "manifest" and feature.used_by(manifest):
            used[feature.feature_id] = feature.since
    return used


def required_host(manifest: Mapping[str, Any]) -> Tuple[str, List[str]]:
    """The oldest flyto-core that accepts everything ``manifest`` uses, and the features that set it."""
    used = features_used(manifest)
    if not used:
        return "0", []
    newest = max(used.values(), key=version_key)
    return newest, sorted(name for name, since in used.items() if since == newest)


def compatibility_matrix(certified: Sequence[Mapping[str, Any]] = ()) -> Dict[str, Any]:
    """The pack feature x flyto-core version matrix, plus the certified packs given.

    The columns are the releases that changed what a host accepts (each
    feature's ``since``); a cell says whether that release accepts the
    feature. ``certified`` takes verified certification record bodies
    (:func:`core.pack.certification.verify_certification`); nothing is
    listed that no record states.
    """
    versions = sorted({feature.since for feature in FEATURES}, key=version_key)
    return {
        "schema": MATRIX_SCHEMA,
        "matrix_version": MATRIX_VERSION,
        "conformance_suite": CONFORMANCE_SUITE,
        "core_versions": versions,
        "features": [
            {"feature": feature.feature_id, "since": feature.since, "describes": feature.describes,
             "reads": feature.reads,
             "accepted": {version: version_key(version) >= version_key(feature.since) for version in versions}}
            for feature in FEATURES
        ],
        "certified": sorted(
            ({"pack_id": body["pack"]["id"], "version": body["pack"]["version"], "pack_digest": body["pack"]["digest"],
              "core_min": body["core"]["min"], "core_max": body["core"]["max"], "features": list(body["features"]),
              "certifier_key_id": body["certifier_key_id"], "certified_at": body["certified_at"]}
             for body in certified),
            key=lambda row: (row["pack_id"], version_key(row["version"]), row["certifier_key_id"]),
        ),
    }


def render_matrix_markdown(matrix: Mapping[str, Any]) -> str:
    """The matrix as Markdown tables: features by release, then the certified packs."""
    versions = matrix["core_versions"]
    lines = [
        f"Matrix version **{matrix['matrix_version']}** (`{matrix['schema']}`). A cell is `yes` when that",
        "flyto-core release accepts the feature.",
        "",
        "| Feature | Since | " + " | ".join(versions) + " |",
        "| --- | --- | " + " | ".join("---" for _ in versions) + " |",
    ]
    for row in matrix["features"]:
        cells = " | ".join("yes" if row["accepted"][version] else "-" for version in versions)
        lines.append(f"| `{row['feature']}` | {row['since']} | {cells} |")
    lines += ["", "| Feature | What the pack uses |", "| --- | --- |"]
    lines += [f"| `{row['feature']}` | {row['describes']} |" for row in matrix["features"]]
    lines += ["", "## Certified packs", ""]
    if not matrix["certified"]:
        lines.append("None. Only a verified `flyto.pack-certification.v1` record adds a row here.")
    else:
        lines += ["| Pack | Version | Digest | flyto-core | Certifier | Certified at |",
                  "| --- | --- | --- | --- | --- | --- |"]
        lines += [f"| `{row['pack_id']}` | {row['version']} | `{row['pack_digest']}` | "
                  f"{row['core_min']} .. {row['core_max']} | `{row['certifier_key_id']}` | {row['certified_at']} |"
                  for row in matrix["certified"]]
    return "\n".join(lines) + "\n"


__all__ = ["CONFORMANCE_SUITE", "FEATURES", "MATRIX_SCHEMA", "MATRIX_VERSION", "Feature", "compatibility_matrix",
           "features_used", "render_matrix_markdown", "required_host", "version_key"]
