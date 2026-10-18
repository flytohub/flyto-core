# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Offline conformance for a third-party ``flyto.pack.v1`` adapter pack.

``flyto pack conform DIR`` asks a pack the questions a host will ask it in
the field, before it ships. It needs no network, no account and no Flyto2
service: it reads the directory, then runs the pack's own runner through the
same install and JSON-RPC path ``install_pack`` uses, and talks to it directly
so the runner's own refusals are tested, not the host's.

Evidence level of a pass: **D2**, a local run of an exact command. It is a
statement about the pack against whatever the runner drove, which should be
the vendor's simulator. It is not hardware certification, and not proof that
a device stops: that needs the device, a measured stop and an independent
observation.

**Run it against a simulator, or with the machine clear of people.** Two
checks call actuating capabilities: one inside the published bounds, one
deliberately outside them, which a conforming runner refuses.

Static checks read only the files. Running checks are skipped with
``run=False``. A check that cannot apply reports ``not_applicable``, which is
never a pass, and a report where nothing ran is not conformant.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .compatibility import CONFORMANCE_SUITE, MATRIX_VERSION, required_host, version_key
from .manifest import PackManifestError, pack_tree_digest, read_pack_manifest
from .signature import read_signature, verify_manifest_signature

REPORT_SCHEMA = CONFORMANCE_SUITE
EVIDENCE_LEVEL = "D2"

PASS, FAIL, NOT_APPLICABLE = "pass", "fail", "not_applicable"


@dataclass(frozen=True)
class Check:
    check: str
    verdict: str
    detail: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {"check": self.check, "verdict": self.verdict, "detail": self.detail}


def _contract(row: Mapping[str, Any]) -> Mapping[str, Any]:
    contract = row.get("contract")
    return contract if isinstance(contract, Mapping) else {}


def _is_stop(row: Mapping[str, Any]) -> bool:
    return _contract(row).get("role") == "safe_stop"


def _actuators(manifest: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    return [row for row in manifest["modules"] if _contract(row).get("actuates") is True and not _is_stop(row)]


def _numeric_bounds(row: Mapping[str, Any]) -> List[Tuple[str, float, float]]:
    found = []
    for name, spec in (row.get("params_schema") or {}).items():
        if isinstance(spec, Mapping) and spec.get("type") in ("number", "integer") and "min" in spec and "max" in spec:
            found.append((name, float(spec["min"]), float(spec["max"])))
    return found


def probe_arguments(row: Mapping[str, Any], *, outside: Optional[str] = None) -> Dict[str, Any]:
    """In-bounds arguments for every declared parameter; ``outside`` names one pushed past its maximum."""
    arguments: Dict[str, Any] = {}
    for name, spec in (row.get("params_schema") or {}).items():
        kind = spec.get("type") if isinstance(spec, Mapping) else None
        arguments[name] = _PROBES.get(kind, _PROBES["string"])(spec)
    for name, low, high in _numeric_bounds(row):
        if name == outside:
            arguments[name] = high + max(1.0, high - low)
    return arguments


def _midpoint(spec: Mapping[str, Any]) -> Any:
    low, high = spec.get("min"), spec.get("max")
    if low is None or high is None:
        return spec.get("default", 0)
    middle = (float(low) + float(high)) / 2.0
    return int(middle) if spec.get("type") == "integer" else middle


_PROBES: Mapping[Any, Callable[[Mapping[str, Any]], Any]] = {
    "number": _midpoint,
    "integer": _midpoint,
    "boolean": lambda spec: bool(spec.get("default", False)),
    "string": lambda spec: str(spec.get("default") or "conformance"),
}


# -- static ------------------------------------------------------------------


def _check_digest(root: Path, manifest: Mapping[str, Any]) -> Check:
    declared = (manifest.get("artifact") or {}).get("digest")
    if declared is None:
        return Check("tree_digest", NOT_APPLICABLE, "no artifact.digest: a development pack, not a distributable one")
    if pack_tree_digest(root) != declared:
        return Check("tree_digest", FAIL, "files do not match artifact.digest")
    return Check("tree_digest", PASS, declared)


def _check_signature(root: Path, manifest: Mapping[str, Any], trusted_keys: Mapping[str, Any]) -> Check:
    document = read_signature(root)
    if document is None:
        return Check("signature", NOT_APPLICABLE, "unsigned")
    if not trusted_keys:
        return Check("signature", NOT_APPLICABLE, "signed, but no trusted key was given to verify it")
    try:
        verified = verify_manifest_signature(manifest, document, trusted_keys)
    except PackManifestError as error:
        return Check("signature", FAIL, error.code)
    return Check("signature", PASS, verified.get("key_id", ""))


def _check_stop_declared(manifest: Mapping[str, Any]) -> Check:
    needing = [row["module_id"] for row in manifest["modules"] if _contract(row).get("requires_safe_stop") is True]
    if not needing:
        return Check("safe_stop_declared", NOT_APPLICABLE, "nothing declared needs a stop")
    if not any(_is_stop(row) for row in manifest["modules"]):
        return Check("safe_stop_declared", FAIL, f"{sorted(needing)} need a stop; no row has role safe_stop")
    return Check("safe_stop_declared", PASS, "role safe_stop present")


def _check_evidence_declared(manifest: Mapping[str, Any]) -> Check:
    actuators = _actuators(manifest)
    if not actuators:
        return Check("evidence_declared", NOT_APPLICABLE, "nothing declared actuates")
    silent = [row["module_id"] for row in actuators if not _contract(row).get("evidence")]
    if silent:
        return Check("evidence_declared", FAIL, f"actuates with nothing that proves it worked: {sorted(silent)}")
    return Check("evidence_declared", PASS, f"{len(actuators)} actuating, each with evidence")


def _check_compatibility(manifest: Mapping[str, Any], host_version: str) -> Check:
    declared = manifest["pack"].get("min_host")
    needed, features = required_host(manifest)
    if not declared:
        return Check("compatibility", FAIL, f"no min_host; this pack needs flyto-core >= {needed} ({', '.join(features)})")
    if version_key(declared) < version_key(needed):
        return Check("compatibility", FAIL, f"min_host {declared} is older than {needed}, needed by {', '.join(features)}")
    if host_version != "unknown" and version_key(host_version) < version_key(declared):
        return Check("compatibility", FAIL, f"this flyto-core {host_version} is older than min_host {declared}")
    return Check("compatibility", PASS, f"min_host {declared} covers {needed} (matrix v{MATRIX_VERSION})")


# -- running -----------------------------------------------------------------


Invoke = Callable[[str, Dict[str, Any]], Any]


def _envelope(answer: Any) -> Optional[bool]:
    """The envelope's ``ok``; None when the answer is not an envelope at all."""
    if isinstance(answer, Mapping) and isinstance(answer.get("ok"), bool):
        return answer["ok"]
    return None


async def _ask(invoke: Invoke, module_id: str, arguments: Dict[str, Any]) -> Tuple[Optional[bool], str]:
    try:
        answer = await invoke(module_id, arguments)
    except Exception as error:  # noqa: BLE001 - a runner may fail in any way; that is the finding
        return None, f"raised {type(error).__name__}"
    ok = _envelope(answer)
    error = answer.get("error") if isinstance(answer, Mapping) else None
    return ok, (error.get("code", "") if isinstance(error, Mapping) else "")


async def _running_checks(manifest: Mapping[str, Any], invoke: Invoke) -> List[Check]:
    checks: List[Check] = []
    malformed: List[str] = []
    for row in manifest["modules"]:
        if _contract(row).get("actuates") is not True:
            ok, _ = await _ask(invoke, row["module_id"], probe_arguments(row))
            if ok is None:
                malformed.append(row["module_id"])
    stops = [row for row in manifest["modules"] if _is_stop(row)]
    stop_answers = [await _ask(invoke, row["module_id"], {}) for row in stops]
    not_stopped = [row["module_id"] for row, (ok, _) in zip(stops, stop_answers, strict=True) if ok is not True]
    checks.append(_graded("safe_stop_answers", bool(stops), not_stopped, "did not stop", f"{len(stops)} answered ok"))
    in_bounds: List[str] = []
    refused: List[str] = []
    clamped: List[str] = []
    # The envelope's ok -> where the answer is counted.
    sorted_by_answer = {True: in_bounds, False: refused, None: malformed}
    for row in _actuators(manifest):
        ok, code = await _ask(invoke, row["module_id"], probe_arguments(row))
        sorted_by_answer[ok].append(f"{row['module_id']}:{code}" if code else row["module_id"])
        for name, _low, _high in _numeric_bounds(row):
            past, _ = await _ask(invoke, row["module_id"], probe_arguments(row, outside=name))
            if past is not False:
                clamped.append(f"{row['module_id']}.{name}")
        for row_stop in stops:
            await _ask(invoke, row_stop["module_id"], {})
    actuators = _actuators(manifest)
    checks.append(_graded("completes_in_bounds", bool(actuators), refused, "refused in bounds",
                          f"{len(in_bounds)} completed"))
    bounded = [row for row in actuators if _numeric_bounds(row)]
    checks.append(_graded("refuses_out_of_bounds", bool(bounded), clamped, "accepted past the published maximum",
                          "every bound refused"))
    checks.append(_graded("answers", True, sorted(set(malformed)), "no answer (crashed, timed out or unreadable) from",
                          "every call answered"))
    return checks


def _graded(name: str, applicable: bool, failures: Sequence[str], failed_means: str, passed: str) -> Check:
    """One running check's verdict: not applicable, failed with what failed, or passed."""
    if not applicable:
        return Check(name, NOT_APPLICABLE, "nothing declared it applies to")
    if failures:
        return Check(name, FAIL, f"{failed_means}: {list(failures)}")
    return Check(name, PASS, passed)


async def _run_installed(root: Path, manifest: Mapping[str, Any], trusted_keys: Mapping[str, Any]) -> List[Check]:
    from .host import _INSTALLED, install_pack, uninstall_pack

    pack_id = manifest["pack"]["id"]
    try:
        install_pack(root, trusted_keys=trusted_keys, require_signature=False)
    except PackManifestError as error:
        return [Check("installs", FAIL, error.code)]
    try:
        transport = _INSTALLED[pack_id].transport
        timeout = int(manifest["runtime"]["request_timeout_ms"])

        async def invoke(module_id: str, arguments: Dict[str, Any]) -> Any:
            context = {"pack_id": pack_id, "module_id": module_id, "execution_id": "conformance"}
            return await transport.invoke(module_id, arguments, context, timeout)

        return [Check("installs", PASS, "installed from a host-private copy"), *await _running_checks(manifest, invoke)]
    finally:
        await uninstall_pack(pack_id)


def _host_version() -> str:
    from .host import _host_version as read

    return read()


async def conform_async(pack_dir: Any, *, trusted_keys: Optional[Mapping[str, Any]] = None, run: bool = True) -> Dict[str, Any]:
    root = Path(pack_dir)
    keys = dict(trusted_keys or {})
    try:
        manifest = read_pack_manifest(root)
    except PackManifestError as error:
        checks = [Check("manifest", FAIL, error.code)]
        return _report(root, None, checks)
    checks = [
        Check("manifest", PASS, f"{manifest['pack']['id']} {manifest['pack']['version']}"),
        _check_digest(root, manifest),
        _check_signature(root, manifest, keys),
        _check_stop_declared(manifest),
        _check_evidence_declared(manifest),
        _check_compatibility(manifest, _host_version()),
    ]
    if run:
        checks.extend(await _run_installed(root, manifest, keys))
    return _report(root, manifest, checks)


def conform(pack_dir: Any, *, trusted_keys: Optional[Mapping[str, Any]] = None, run: bool = True) -> Dict[str, Any]:
    """Run the suite from synchronous code (the CLI)."""
    return asyncio.run(conform_async(pack_dir, trusted_keys=trusted_keys, run=run))


def _report(root: Path, manifest: Optional[Mapping[str, Any]], checks: Sequence[Check]) -> Dict[str, Any]:
    failed = [item.check for item in checks if item.verdict == FAIL]
    ran = [item for item in checks if item.verdict != NOT_APPLICABLE]
    return {
        "schema": REPORT_SCHEMA,
        "matrix_version": MATRIX_VERSION,
        "evidence_level": EVIDENCE_LEVEL,
        "hardware_acceptance": "NOT_VERIFIED",
        "pack": dict(manifest["pack"]) if manifest else None,
        "host_version": _host_version(),
        "conformant": not failed and bool(ran),
        "failed": failed,
        "results": [item.to_dict() for item in checks],
    }


def render(report: Mapping[str, Any]) -> str:
    marks = {PASS: "pass", FAIL: "FAIL", NOT_APPLICABLE: "n/a "}
    lines = [f"  [{marks[item['verdict']]}] {item['check']:<22} {item['detail']}" for item in report["results"]]
    verdict = "conformant" if report["conformant"] else f"not conformant: {', '.join(report['failed']) or 'nothing ran'}"
    lines.append(f"\n{verdict} ({report['evidence_level']}; hardware NOT_VERIFIED; not applicable is not a pass)")
    return "\n".join(lines)


__all__ = ["EVIDENCE_LEVEL", "REPORT_SCHEMA", "conform", "conform_async", "probe_arguments", "render"]

