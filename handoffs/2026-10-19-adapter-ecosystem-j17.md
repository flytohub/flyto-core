# Adapter ecosystem (J17): certification, generated matrix, upgrades, key rotation, device template

Owner: claude
Branch: lane/j17-ecosystem (on core-integ 350a592)
Date: 2026-10-19

## What changed

Mechanisms for a vendor who joins without editing core. No vendor, device or
partnership is named or claimed anywhere; vendor-like names appear only in
test fixtures (`com.example.*`).

- `src/core/pack/certification.py` (new): `flyto.pack-certification.v1`.
  `certify(source, private_key, key_id, ...)` runs the `CHECKS` table in order:
  `verify` (`verify_pack_dir`: digest, files, signature through rotations,
  revocations; `PACK_NOT_BUILT` without `artifact.digest`; `ALREADY_INSTALLED`
  when this process already runs the pack), `compatibility` (conformance's
  `min_host` vs matrix check), `conform`, `pack_test` (connector only, against
  the pack's recorded fixtures), `standalone_health` (connector + `standalone`
  only: `health()` pointed at `serve_fixtures` with a fixture customer's test
  credential in an env-only resolver, so nothing reaches a provider or a
  keychain). A failed `verify` blocks every later check (`not_run`): an
  unverified pack is never run. A record is signed (`sign_detached`, domain
  `flyto.pack-certification.v1\n`) only when `verify`, `compatibility` and
  `conform` pass and the others pass or are not applicable. It names the pack
  `{id, version, digest}`, `core {min: min_host, max: certifying host}`, the
  matrix version, features used, every check, `evidence_level: D2`,
  `hardware_acceptance: NOT_VERIFIED`, `certified_at`, `certifier_key_id`.
  `verify_certification` (`CERTIFICATION_INVALID`, `_UNTRUSTED_KEY`,
  `_SIGNATURE_MISMATCH`). Policy `flyto.pack-certification-policy.v1`: a rule
  table (`packs` fnmatch pattern, `require`, `certifiers`, `max_age_days`),
  first match decides; `CertificationGate.check` refuses `PACK_UNCERTIFIED`
  (no verifying record from a named certifier for this exact digest) and
  `CERTIFICATION_STALE` (`STALENESS` table: host newer than `core.max`, older
  than `core.min`, matrix changed, expired).
- `src/core/pack/publisher_keys.py` (new): `flyto.publisher-key-rotation.v1`
  (`sign_key_rotation`, `rotation_digest`, `resolve_publisher_keys`: at most 8
  hops from a trusted key, every supplied statement must connect;
  `KEY_ROTATION_INVALID`, `KEY_ROTATION_BROKEN`, `KEY_ROTATION_TOO_LONG`,
  `PUBLISHER_KEY_REVOKED`). `verify_publisher` is now the one publisher check
  that `install_pack` and `verify_pack_dir` both call.
- `src/core/pack/supply_chain.py`: revocation list `flyto.pack-revocations.v2`
  (own domain) adds `revoked_keys: [{key_id, reason, since, retained}]`;
  `RevocationList.revoked_keys`, `check_signer`, `signed_after_revocation`. A
  v1 list loads unchanged and `sign_revocations` still emits v1 unless
  `revoked_keys` is passed.
- `src/core/pack/upgrade.py` (new): the `upgrade` manifest section
  (`supersedes`, `rollback` subset of it, `migrations {from, state,
  reversible}`; `INVALID_UPGRADE`, `ROLLBACK_IRREVERSIBLE`) and
  `check_transition` over the `TRANSITIONS` table (`same`/`VERSION_REBUILT`,
  `upgrade`/`UPGRADE_UNDECLARED`, `rollback`/`ROLLBACK_UNDECLARED`;
  `PACK_ID_MISMATCH`), returning the migrations crossed.
- `src/core/pack/host.py`: `install_pack(..., key_rotations=, certification=,
  upgrade_from=)`. `portable.verify_pack[_dir]` and `standalone.load_standalone`
  / `health` take `key_rotations` and `certification` too.
- `src/core/pack/manifest.py`: top-level `upgrade` key; a declared module row
  whose contract has no `safety_class` is `CONSEQUENCE_MISSING`, naming every
  such module (`operations=`).
- `src/core/pack/compatibility.py`: feature `pack.upgrade` (2.41.0),
  `features_used`, `compatibility_matrix` (`flyto.pack-compatibility-matrix.v1`)
  and `render_matrix_markdown`. `scripts/generate_reference.py` writes
  `docs/reference/pack-compatibility-matrix.json` and `.md`; the spec page no
  longer holds a hand-written table.
- `src/core/pack/scaffold.py`: `TEMPLATES` table (`connector`,
  `device-adapter`); the device template writes a subprocess-jsonrpc module
  pack (move_to with bounds and evidence, read_state, a safe_stop), every
  contract without `safety_class`, a stdlib runner against a simulated
  device, and a pytest file running `conform`. `decide_consequences` decides
  module rows too (`safety_class` + the level's effect from
  `CONSEQUENCE_CONTRACTS`). `INIT_TEMPLATE_UNKNOWN`, `INIT_TEMPLATE_CONFLICT`.
- `src/core/pack/doctor.py`: rows for all 18 new codes; the completeness test
  knows the two new dynamic sites.
- `src/cli/pack.py`: `flyto pack certify | matrix | rotate-key`,
  `init --template`, and `--key-rotation`, `--certification-policy`,
  `--certifier-key`, `--certification` on `verify`, `run`, `health`.
- Docs: `docs/guides/BUILD_A_PACK.md` sections 9 (certify and publish
  privately, key rotation) and 10 (a device adapter), every command run by
  the guide test; section 6 now unloads what it loaded. Spec:
  `ADAPTER_COMPATIBILITY_MATRIX.md`, `PACK_MANIFEST_SPEC.md`; `docs/CLI.md`,
  `CHANGELOG.md`, `STATE.md`, `DECISIONS.md`, regenerated `docs/reference/`,
  inventory tokens.

## Why

J17 asks for an ecosystem a vendor joins without editing core. Every piece
reuses the existing primitives (one ed25519 `sign_detached` step with a domain
per document, `verify_pack_dir`/`install_pack`, `conform`, `pack test`,
`health`, `FEATURES`), so there is one implementation of each check.

Rejected: a timestamp as a key's revocation point (a compromised key can
backdate); certifying a pack that does not verify; trusting a rotated key
without a chain; a hand-written matrix; scaffold defaults for consequences.

## Verified

Evidence files are in the lane scratchpad `round9/j17-evidence/`.

- Failing first (`failing-first.txt`): all five new test files failed at
  collection before any code: `ModuleNotFoundError: core.pack.certification`,
  `core.pack.upgrade`, `core.pack.publisher_keys`; `ImportError` for
  `compatibility.MATRIX_SCHEMA` and `scaffold.TEMPLATES` (5 errors).
- New tests, 71 passed: `test_pack_certification.py` 22,
  `test_compatibility_matrix.py` 6, `test_pack_upgrade.py` 16 (incl. the
  install-beside upgrade/rollback path through `install_pack(upgrade_from=)`),
  `test_publisher_key_rotation.py` 16, `test_device_adapter_template.py` 11
  (incl. a decided, signed device pack certifying with `pack_test` and
  `standalone_health` not applicable). `test_build_a_pack_guide.py` 4 passed
  with sections 9 and 10 run as written; `test_pack_doctor.py` 162 passed with
  the 18 new codes.
- `tests/core/pack` + `tests/test_documentation_generators.py`, mid-lane:
  659 passed, 2 failed, both the doctor completeness test naming the new
  codes without rows; after the rows that file passed 162, and the full
  suite below covers the rest.
- Full non-browser suite `pytest -m 'not browser and not e2e' --no-cov`:
  6064 passed, 174 skipped, 508 deselected, 0 failed (13 min).
- `generate_reference.py` regenerated, `--check` PASS (1017 files, 6,855
  declarations); `check_documentation.py` PASS (198 Markdown files, 258
  local links) after the inventory tokens; `check_brand_identity.py` PASS;
  `lint-project-memory.sh` PASS; ruff clean on every changed Python file
  (3 import-order/`dict.fromkeys` findings fixed).
- `flyto-index verify --strict` on the commit: PASS, 21 pass, 0 warn, 0 fail.
- Exploration before editing: `flyto-index context` / `impact` CLI on this
  worktree (install_pack 45 direct references, verify_pack_dir 3,
  load_revocations 9, verify_manifest_signature 12, validate_pack_manifest
  54). The MCP server is pinned to flyto-indexer's own root, so MCP `task`
  plan ran but its gates and `task(action='validate')` could not target this
  repository; not run.

## Not verified

- No real vendor, certifier, device, firmware or customer. A record is D2,
  never hardware acceptance; the certified list in the generated matrix is
  empty.
- Migrations are declared and reported; nothing in core runs them.
- `certify` on a pack whose fixture customers hold only OAuth credentials
  fails `standalone_health` (no string credential to hand the resolver).
- CI and release were not run. Cloud: see the Cloud handoff
  `2026-10-19-adapter-ecosystem-j17-cloud.md` (lane/j17-cloud).

## Follow-ups

- Distribute certification records and rotation statements with a release
  channel (today they are files a host holds).
- A real vendor pack under the device-adapter template, on its own device.
