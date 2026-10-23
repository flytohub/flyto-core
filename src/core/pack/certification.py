# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Pack certification (``flyto.pack-certification.v1``) and the host policy that can require it.

``flyto pack certify PACK`` runs every check a pack can pass offline, in the
order of :data:`CHECKS`:

* ``verify`` — the pack digest, its files, the publisher signature (through
  rotation statements when given), the revocation list. A pack that does not
  verify is never run: every later check is ``not_run``;
* ``compatibility`` — its declared ``min_host`` against the host matrix
  (``core.pack.compatibility``): old enough for no host it cannot run on,
  new enough for every feature it uses;
* ``conform`` — the offline conformance suite (``core.pack.conformance``);
* ``pack_test`` — ``flyto pack test`` against the pack's own recorded
  fixtures (a connector pack; for a module pack the runner is what
  ``conform`` exercises, so this is ``not_applicable``);
* ``standalone_health`` — the standalone health check of a portable pack,
  pointed at the same recorded fixtures with a fixture customer's test
  credential, so it reaches no provider.

Only when every applicable check passes — and ``verify``, ``compatibility``
and ``conform`` always apply — is a record signed::

    {"schema": "flyto.pack-certification.v1",
     "certification": {"pack": {"id", "version", "digest"},
                       "core": {"min": <min_host>, "max": <the flyto-core it passed on>},
                       "matrix_version", "conformance_suite", "features": [...],
                       "checks": [{"check", "verdict", "detail"}, ...],
                       "evidence_level": "D2", "hardware_acceptance": "NOT_VERIFIED",
                       "certified_at", "certifier_key_id"},
     "signature": {"algorithm": "ed25519", "key_id", "signature"}}

over ``b"flyto.pack-certification.v1\\n" + canonical_bytes(certification)``
(:func:`core.pack.signature.sign_detached`). A record is evidence level D2: a
local run of exact commands against recorded fixtures or a simulator. It is
not hardware acceptance and says so.

**Policy** (``flyto.pack-certification-policy.v1``) is a table of rules; the
first whose ``packs`` pattern matches a pack id decides::

    {"schema": "flyto.pack-certification-policy.v1",
     "rules": [{"packs": "com.example.*", "require": true,
                "certifiers": ["certifier-1"], "max_age_days": 365}]}

When the matching rule requires certification, a pack installs only with a
record that verifies against a key the rule names and that names this exact
pack digest; otherwise ``PACK_UNCERTIFIED``. A record that applies no longer
(:data:`STALENESS`) is ``CERTIFICATION_STALE``. No rule, or ``require:
false``, requires nothing.
"""

from __future__ import annotations

import asyncio
import fnmatch
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .compatibility import CONFORMANCE_SUITE, MATRIX_VERSION, features_used, version_key
from .manifest import PackManifestError
from .signature import _KEY_ID, sign_detached, verify_detached

__all__ = [
    "CERTIFICATION_CHECKS",
    "CERTIFICATION_SCHEMA",
    "CHECKS",
    "CertificationGate",
    "POLICY_SCHEMA",
    "STALENESS",
    "certify",
    "load_certification_policy",
    "verify_certification",
]

CERTIFICATION_SCHEMA = "flyto.pack-certification.v1"
CERTIFICATION_DOMAIN = b"flyto.pack-certification.v1\n"
POLICY_SCHEMA = "flyto.pack-certification-policy.v1"
EVIDENCE_LEVEL = "D2"

PASS, FAIL, NOT_APPLICABLE, NOT_RUN = "pass", "fail", "not_applicable", "not_run"
VERDICTS = (PASS, FAIL, NOT_APPLICABLE, NOT_RUN)

MAX_RULES = 64
MAX_RECORDS = 1024
_RECORD_KEYS = frozenset({
    "pack", "core", "matrix_version", "conformance_suite", "features", "checks", "evidence_level",
    "hardware_acceptance", "certified_at", "certifier_key_id",
})
_RULE_REQUIRED = frozenset({"packs", "require"})
_RULE_KEYS = _RULE_REQUIRED | {"certifiers", "max_age_days"}
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_PACK_PATTERN = re.compile(r"^[a-z0-9*?._-]{1,128}$")
CERTIFICATION_SIGNATURE_REFUSALS = {"UNTRUSTED_KEY": "CERTIFICATION_UNTRUSTED_KEY",
                       "SIGNATURE_MISMATCH": "CERTIFICATION_SIGNATURE_MISMATCH"}


def _fail(code: str, message: str) -> None:
    raise PackManifestError(code, message)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _timestamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _host_version() -> str:
    from .host import _host_version as read

    return read()


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------


@dataclass
class _Run:
    """One certification run: the opened pack and what the earlier checks established."""

    root: Path
    trusted_keys: Mapping[str, Any]
    require_signature: bool
    revocations: Any
    key_rotations: Sequence[Any]
    manifest: Optional[Dict[str, Any]] = None
    keys: Optional[Dict[str, Any]] = None
    verification: Optional[Dict[str, Any]] = None


Result = Tuple[str, str]


def _verify(run: _Run) -> Result:
    from .portable import verify_pack_dir
    from .publisher_keys import resolve_publisher_keys

    try:
        run.verification = verify_pack_dir(run.root, trusted_keys=run.trusted_keys,
                                           require_signature=run.require_signature, revocations=run.revocations,
                                           key_rotations=run.key_rotations)
        if run.verification["artifact_digest"] is None:
            return FAIL, "PACK_NOT_BUILT"
        from .host import installed_packs
        from .manifest import read_pack_manifest

        run.manifest = read_pack_manifest(run.root)
        if run.manifest["pack"]["id"] in installed_packs():
            # The checks install the pack; one this process already runs would answer for them.
            return FAIL, "ALREADY_INSTALLED"
        run.keys = resolve_publisher_keys(run.trusted_keys, list(run.key_rotations), revocations=run.revocations)
    except PackManifestError as error:
        return FAIL, error.code
    return PASS, (run.verification["signature"] or {}).get("key_id", "unsigned")


def _compatibility(run: _Run) -> Result:
    from .conformance import _check_compatibility

    check = _check_compatibility(run.manifest, _host_version())
    return check.verdict, check.detail


def _conform(run: _Run) -> Result:
    from .conformance import conform_async

    report = asyncio.run(conform_async(run.root, trusted_keys=run.keys, run=True))
    if not report["conformant"]:
        return FAIL, ", ".join(report["failed"]) or "nothing ran"
    ran = [item["check"] for item in report["results"] if item["verdict"] == PASS]
    return PASS, f"{len(ran)} checks passed"


def _pack_test(run: _Run) -> Result:
    from .recorded import run_pack_tests

    report = run_pack_tests(run.root, conformance=False)
    if not report["passed"]:
        failed = [item["operation"] for item in report["operations"] if item["verdict"] == "fail"]
        return FAIL, f"failed: {failed}" if failed else "the probe or a listing failed"
    return PASS, f"{len(report['operations'])} operations passed their recorded calls"


def _fixture_resolver(manifest: Mapping[str, Any], fixtures: Any) -> Optional[Callable[[Mapping[str, Any]], Any]]:
    """A resolver holding one fixture customer's test credential, or ``None`` when no customer has one."""
    from .standalone_auth import NO_KEYCHAIN_ENV, CredentialResolver

    auth = manifest["connector"]["auth"]
    if not auth:
        return lambda standalone: CredentialResolver(standalone, env={NO_KEYCHAIN_ENV: "1"})
    held = [customer["credential"] for _name, customer in sorted(fixtures.customers.items())
            if isinstance(customer.get("credential"), str)]
    if not held:
        return None
    env = {item["env"]: held[0] for item in manifest["standalone"]["credentials"]
           if item["name"] == auth[0]["credential"]}
    env[NO_KEYCHAIN_ENV] = "1"
    return lambda standalone: CredentialResolver(standalone, env=env)


def _standalone_health(run: _Run) -> Result:
    from .recorded import load_fixtures, serve_fixtures
    from .standalone import health

    resolver = _fixture_resolver(run.manifest, load_fixtures(run.root, run.manifest))
    if resolver is None:
        return FAIL, "no fixture customer holds a test credential to run the health check with"
    with serve_fixtures(run.root) as url:
        report = health(run.root, trusted_keys=run.keys, require_signature=run.require_signature,
                        revocations=run.revocations, resolver_factory=resolver, provider_base_url=url)
    if not report["healthy"]:
        return FAIL, ", ".join(report["problems"])
    return PASS, f"{report['entitled_tools']} of {report['tools']} tools entitled against the recorded fixtures"


def _is_connector(manifest: Mapping[str, Any]) -> bool:
    return manifest["runtime"]["binding"] == "connector"


@dataclass(frozen=True)
class CertificationCheck:
    check: str
    run: Callable[[_Run], Result]
    #: Whether the check applies to this pack; a check that always applies is never ``not_applicable``.
    applies: Callable[[Mapping[str, Any]], bool]
    not_applicable: str = ""


CHECKS: Tuple[CertificationCheck, ...] = (
    CertificationCheck("verify", _verify, lambda manifest: True),
    CertificationCheck("compatibility", _compatibility, lambda manifest: True),
    CertificationCheck("conform", _conform, lambda manifest: True),
    CertificationCheck("pack_test", _pack_test, _is_connector,
                       "not a connector pack: conform exercises its runner"),
    CertificationCheck("standalone_health", _standalone_health,
                       lambda manifest: _is_connector(manifest) and "standalone" in manifest,
                       "no standalone section: the pack runs only inside a host"),
)
CERTIFICATION_CHECKS = tuple(item.check for item in CHECKS)
#: The checks that always apply: their ``not_applicable`` is never a pass.
ALWAYS = tuple(item.check for item in CHECKS if item.not_applicable == "")


def _results(run: _Run) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    blocked = ""
    for item in CHECKS:
        if blocked:
            verdict, detail = NOT_RUN, blocked
        elif item.check != "verify" and not item.applies(run.manifest):
            verdict, detail = NOT_APPLICABLE, item.not_applicable
        else:
            try:
                verdict, detail = item.run(run)
            except PackManifestError as error:
                verdict, detail = FAIL, error.code
        results.append({"check": item.check, "verdict": verdict, "detail": detail})
        if item.check == "verify" and verdict != PASS:
            # An unverified pack is never run: its code is not the code anyone signed.
            blocked = "verify failed; the pack was not run"
    return results


def _passed(checks: Sequence[Mapping[str, str]]) -> bool:
    by_name = {item["check"]: item["verdict"] for item in checks}
    return (set(by_name) == set(CERTIFICATION_CHECKS)
            and all(by_name[name] == PASS for name in ALWAYS)
            and all(verdict in (PASS, NOT_APPLICABLE) for verdict in by_name.values()))


def certify(source: Any, *, private_key: Any, key_id: str, trusted_keys: Optional[Mapping[str, Any]] = None,
            require_signature: bool = True, revocations: Any = None, key_rotations: Sequence[Any] = (),
            certified_at: Optional[str] = None) -> Dict[str, Any]:
    """Run every check on a pack (zip or directory); sign a record only when every one passed."""
    from .portable import opened_pack
    from .supply_chain import pack_digest

    if type(key_id) is not str or not _KEY_ID.fullmatch(key_id):
        _fail("INVALID_KEY", "certifier key id is invalid")
    moment = certified_at or _timestamp(_now())
    if not _TIMESTAMP.fullmatch(moment):
        _fail("CERTIFICATION_INVALID", "certified_at must be a UTC timestamp")
    with opened_pack(source) as root:
        run = _Run(root=Path(root), trusted_keys=dict(trusted_keys or {}), require_signature=require_signature,
                   revocations=revocations, key_rotations=list(key_rotations or ()))
        results = _results(run)
    manifest = run.manifest
    certified = manifest is not None and _passed(results)
    report: Dict[str, Any] = {
        "certified": certified,
        "pack": dict(manifest["pack"]) if manifest else None,
        "pack_digest": pack_digest(manifest) if manifest else None,
        "results": results,
        "record": None,
    }
    if certified:
        body = {
            "pack": {"id": manifest["pack"]["id"], "version": manifest["pack"]["version"],
                     "digest": pack_digest(manifest)},
            "core": {"min": manifest["pack"]["min_host"], "max": _host_version()},
            "matrix_version": MATRIX_VERSION,
            "conformance_suite": CONFORMANCE_SUITE,
            "features": sorted(features_used(manifest)),
            "checks": results,
            "evidence_level": EVIDENCE_LEVEL,
            "hardware_acceptance": "NOT_VERIFIED",
            "certified_at": moment,
            "certifier_key_id": key_id,
        }
        report["record"] = {"schema": CERTIFICATION_SCHEMA, "certification": body,
                            "signature": sign_detached(CERTIFICATION_DOMAIN, body, private_key, key_id)}
    return report


# ---------------------------------------------------------------------------
# Verifying a record
# ---------------------------------------------------------------------------


def _record_body(body: Any) -> Dict[str, Any]:
    if type(body) is not dict or set(body) != _RECORD_KEYS:
        _fail("CERTIFICATION_INVALID", "certification record has the wrong shape")
    pack, core = body["pack"], body["core"]
    if type(pack) is not dict or set(pack) != {"id", "version", "digest"} or not all(
            type(value) is str for value in pack.values()):
        _fail("CERTIFICATION_INVALID", "certification pack is {id, version, digest}")
    if type(core) is not dict or set(core) != {"min", "max"} or not all(type(v) is str for v in core.values()):
        _fail("CERTIFICATION_INVALID", "certification core is {min, max}")
    checks = body["checks"]
    if type(checks) is not list or any(
            type(item) is not dict or set(item) != {"check", "verdict", "detail"} or item["verdict"] not in VERDICTS
            for item in checks):
        _fail("CERTIFICATION_INVALID", "certification checks are {check, verdict, detail}")
    if type(body["certified_at"]) is not str or not _TIMESTAMP.fullmatch(body["certified_at"]):
        _fail("CERTIFICATION_INVALID", "certified_at must be a UTC timestamp")
    if type(body["features"]) is not list:
        _fail("CERTIFICATION_INVALID", "certification features must be a list")
    return body


def verify_certification(document: Any, certifier_keys: Mapping[str, Any]) -> Dict[str, Any]:
    """The record's body when it verifies against ``certifier_keys``; a typed refusal otherwise."""
    if type(document) is not dict or set(document) != {"schema", "certification", "signature"}:
        _fail("CERTIFICATION_INVALID", "certification document has the wrong shape")
    if document["schema"] != CERTIFICATION_SCHEMA:
        _fail("CERTIFICATION_INVALID", f"schema must be {CERTIFICATION_SCHEMA}")
    body = _record_body(document["certification"])
    signature = document["signature"]
    if type(signature) is not dict or set(signature) != {"algorithm", "key_id", "signature"}:
        _fail("CERTIFICATION_INVALID", "certification signature has the wrong shape")
    if signature["key_id"] != body["certifier_key_id"]:
        _fail("CERTIFICATION_INVALID", "the record names another certifier than the key that signed it")
    try:
        verify_detached(CERTIFICATION_DOMAIN, body, signature, certifier_keys)
    except PackManifestError as error:
        raise PackManifestError(CERTIFICATION_SIGNATURE_REFUSALS.get(error.code, "CERTIFICATION_INVALID"),
                                f"certification record: {error}") from None
    return body


# ---------------------------------------------------------------------------
# The host policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Context:
    host_version: str
    now: datetime
    max_age_days: Optional[int]


#: (name, holds): a record that names the pack but for which any row holds no longer applies.
STALENESS: Tuple[Tuple[str, Callable[[Mapping[str, Any], _Context], bool]], ...] = (
    ("host_newer_than_certified", lambda body, ctx: version_key(ctx.host_version) > version_key(body["core"]["max"])),
    ("host_older_than_certified", lambda body, ctx: version_key(ctx.host_version) < version_key(body["core"]["min"])),
    ("matrix_changed", lambda body, ctx: body["matrix_version"] != MATRIX_VERSION),
    ("expired", lambda body, ctx: ctx.max_age_days is not None
     and ctx.now - _parse_time(body["certified_at"]) > timedelta(days=ctx.max_age_days)),
)


@dataclass(frozen=True)
class _Rule:
    packs: str
    require: bool
    certifiers: Tuple[str, ...]
    max_age_days: Optional[int]


def _rule(value: Any, index: int) -> _Rule:
    where = f"rules[{index}]"
    if type(value) is not dict or not set(value) >= _RULE_REQUIRED or not set(value) <= _RULE_KEYS:
        _fail("CERTIFICATION_POLICY_INVALID", f"{where} is {{packs, require, certifiers?, max_age_days?}}")
    if type(value["packs"]) is not str or not _PACK_PATTERN.fullmatch(value["packs"]):
        _fail("CERTIFICATION_POLICY_INVALID", f"{where}.packs must be a pack id pattern")
    if type(value["require"]) is not bool:
        _fail("CERTIFICATION_POLICY_INVALID", f"{where}.require must be true or false")
    certifiers = value.get("certifiers", [])
    if type(certifiers) is not list or len(certifiers) > 64 or any(
            type(item) is not str or not _KEY_ID.fullmatch(item) for item in certifiers):
        _fail("CERTIFICATION_POLICY_INVALID", f"{where}.certifiers must be a list of key ids")
    if value["require"] and not certifiers:
        _fail("CERTIFICATION_POLICY_INVALID", f"{where} requires certification from no certifier")
    max_age = value.get("max_age_days")
    if max_age is not None and (type(max_age) is not int or not 1 <= max_age <= 36_500):
        _fail("CERTIFICATION_POLICY_INVALID", f"{where}.max_age_days must be 1..36500")
    return _Rule(value["packs"], value["require"], tuple(certifiers), max_age)


@dataclass(frozen=True)
class CertificationGate:
    """A verified policy table, the certifier keys it trusts, and the records the host holds."""

    rules: Tuple[_Rule, ...]
    certifier_keys: Mapping[str, Any]
    records: Tuple[Any, ...]

    def rule_for(self, pack_id: str) -> Optional[_Rule]:
        return next((rule for rule in self.rules if fnmatch.fnmatchcase(pack_id, rule.packs)), None)

    def _records_for(self, digest: str, rule: _Rule) -> List[Dict[str, Any]]:
        keys = {key_id: key for key_id, key in self.certifier_keys.items() if key_id in rule.certifiers}
        found = []
        for document in self.records:
            try:
                body = verify_certification(document, keys)
            except PackManifestError:
                continue  # a record that does not verify certifies nothing
            if body["pack"]["digest"] == digest and _passed(body["checks"]):
                found.append(body)
        return found

    def check(self, manifest: Mapping[str, Any], *, host_version: Optional[str] = None,
              now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """The record that admits ``manifest`` (``None`` when nothing is required), or a typed refusal."""
        from .supply_chain import pack_digest

        pack_id = manifest["pack"]["id"]
        rule = self.rule_for(pack_id)
        if rule is None or not rule.require:
            return None
        found = self._records_for(pack_digest(manifest), rule)
        if not found:
            _fail("PACK_UNCERTIFIED", f"{pack_id} {manifest['pack']['version']} has no certification record from "
                  f"{', '.join(rule.certifiers)} for this exact build")
        context = _Context(host_version or _host_version(), now or _now(), rule.max_age_days)
        fresh = [body for body in found if not any(holds(body, context) for _name, holds in STALENESS)]
        if not fresh:
            reasons = sorted({name for body in found for name, holds in STALENESS if holds(body, context)})
            _fail("CERTIFICATION_STALE", f"{pack_id} {manifest['pack']['version']}: every certification record is "
                  f"stale ({', '.join(reasons)}); certify it again on this host")
        return max(fresh, key=lambda body: body["certified_at"])


def load_certification_policy(document: Any, certifier_keys: Mapping[str, Any],
                              records: Sequence[Any] = ()) -> CertificationGate:
    """A policy table, verified in shape, with the certifier keys and records it is checked against."""
    from .signature import load_trusted_keys

    if type(document) is not dict or set(document) != {"schema", "rules"}:
        _fail("CERTIFICATION_POLICY_INVALID", "a policy is {schema, rules}")
    if document["schema"] != POLICY_SCHEMA:
        _fail("CERTIFICATION_POLICY_INVALID", f"schema must be {POLICY_SCHEMA}")
    rules = document["rules"]
    if type(rules) is not list or len(rules) > MAX_RULES:
        _fail("CERTIFICATION_POLICY_INVALID", f"rules must be a list of at most {MAX_RULES}")
    if not isinstance(records, (list, tuple)) or len(records) > MAX_RECORDS:
        _fail("CERTIFICATION_POLICY_INVALID", f"at most {MAX_RECORDS} certification records")
    return CertificationGate(rules=tuple(_rule(item, index) for index, item in enumerate(rules)),
                             certifier_keys=load_trusted_keys(certifier_keys) if certifier_keys else {},
                             records=tuple(records))
