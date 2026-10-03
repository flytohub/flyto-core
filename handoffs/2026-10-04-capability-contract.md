# Capability contract `flyto.capability-contract.v1` (2.35.0 candidate)

Owner: claude
Branch: claude/capability-contract
Date: 2026-10-04

## What changed

- `src/core/capability_contract.py` (new): `CONTRACT_SCHEMA`, `validate_contract(contract, params_schema) -> normalized dict`, `validate_evidence`, pure `judge(evidence_spec, arguments, observations)`, `wrap_angle` (to (-pi, pi]).
- `register_module(..., contract=...)` (last kwarg) and `build_module_metadata(..., contract=None)` (last kwarg): validated in `_validate_module_registration`, stored normalized as `metadata["contract"]`; key absent when not declared.
- `ModuleRegistry.register` validates `metadata["contract"]` too (requires `provides_capability`) and stores the validator's fresh normalized copy. A plugin whose contract is invalid raises inside `register_all`, so the existing load transaction rolls the whole plugin back.
- `capability_manifest`: adds `contract_count` + `contracts: {capability_id: {module_id, contract, params_schema}}` only when at least one module declares a contract (lowest module id wins on a shared capability). No contracts -> identical document and hash.
- `catalog.module.get_module_detail`: adds `contract` (None when absent) and `timeout_ms`; `timeout` now derives seconds from `timeout_ms` (it read a key no row has and was always None).
- `docs/CAPABILITY_CONTRACT.md` (new): schema, exact arithmetic, worked examples (distance, along advance/retreat, abs and signed rotation across +-pi, heading.hold), "Writing a provider" (entry point + lift, inventory, motion), note on flyto-modules-robotics PR #9.
- Version 2.35.0 (pyproject, server.json, SECURITY*.md), CHANGELOG, DECISIONS, STATE, docs index, regenerated `docs/reference/`, inventory counts.

## Why

Providers (devices, ERP connectors, any software) must plug in through `@register_module` alone so flyto-cloud carries no provider-specific code. Cloud and flyto-modules-robotics consume this next.

Arithmetic, as finally agreed with the coordinator to match Cloud's `motion_verification.py`: measured from `before` to the LAST declared phase (`settled` if listed, else `after`); settle drift `after -> settled` (euclidean for distance/along, |delta|, |wrap| for angle ops); ops `distance | along (heading_field) | delta | angle_delta | abs_angle_delta`; `expect.argument` + optional `scale` (non-zero, default 1); angle-op error is `|wrap(measured - expected)|`; `allowed = max(absolute, relative*|expected|)`.

Additions beyond the written spec: optional `schema` key (must equal the id); `read_only` + `actuates: true` rejected; `expect.argument` must be a number/integer param; `phases` must include before and after; `settle` requires `settled` in phases; every declared phase must be observed or the verdict is unusable; `params_schema` must be JSON-serializable when a contract is declared (manifest hash).

## Verified

In the worktree with its own venv (`pip install -e '.[dev,browser]'`, Python 3.12):
- `pytest -m 'not browser'`: 5016 passed, 192 skipped, 468 deselected, coverage 66.25%.
- `tests/core/test_capability_contract.py`: 188 passed (validation table per rule, decorator/raw/plugin registration incl. rollback, manifest conditional key and hash restore, catalog detail, judge tables incl. the Cloud parity cases).
- `ruff check` on the CI-audited list and on every changed/new Python file: clean.
- `scripts/check_documentation.py`, `scripts/check_brand_identity.py`, `scripts/lint-project-memory.sh`, `scripts/check_release_drift.py` (2.35.0 unreleased): pass.
- `flyto-index verify --strict`: 20 pass / 1 fail. The failure is `weak_scan_taint` (path_traversal, `api/routes/mcp.py` -> `cli/recipe.py:load_recipe`), identical on a clean origin/main (9b0dfa6) checkout with the same local indexer; not touched by this change.

## Not verified

- `task(action='validate')` via the MCP server (pinned to another root) — not run.
- `scripts/lock-deps.sh` / pip-audit not run (no dependency change).
- Not run under Python 3.11 (CI's version) or the CI-pinned indexer 0dbae85.
- No first-party module declares a contract; real consumers (flyto-modules-robotics, flyto-cloud) not exercised against this branch here.

## Follow-ups

- Release: merge, tag v2.35.0, publish; then pin in flyto-modules-robotics and flyto-cloud.
- Cloud re-implements `judge` from the doc (Cloud may not import Core); a shared fixture table would keep them honest.
- v1 cannot express absolute end-state evidence (e.g. "lift is on floor N"); a later `value` op could.
- Pre-existing `weak_scan_taint` finding on main needs its own fix.
