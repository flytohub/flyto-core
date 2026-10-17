# Resource states and parts in the capability contract (2.41.0)

Owner: claude
Branch: claude/contract-states-channels
Date: 2026-10-17

## What changed

- `src/core/capability_contract.py`: two optional contract keys, validated
  like the other identifier lists:
  - `establishes`: 1..16 resource states a completed call leaves true, the
    counterpart of the existing `requires`;
  - `occupies`: 1..8 parts of the resource a running call holds.
- Both appear in the normalized contract only when declared. A contract
  without them occupies the whole resource and normalizes and hashes as on
  2.40.
- A `safe_stop` that declares `occupies` is refused: a stop must be admitted
  whatever else runs on the resource.
- `RESOURCE_STATE_FIELDS` is the feature test; `OCCUPIES_MAX` is the bound.
- `tests/core/vectors/capability_contract_resource_states.json`: admit and
  refuse vectors for a re-implementing host.
- `tests/core/test_capability_contract_resource_states.py`: covers the
  vectors, hash stability and non-aliasing.
- `docs/CAPABILITY_CONTRACT.md`: new rows in the schema table and a section,
  "Resource states and parts (2.41.0)".
- Release bookkeeping: version 2.41.0 (pyproject, server.json, SECURITY*.md),
  CHANGELOG and STATE; regenerated docs/reference; inventory counts updated.

## Why

These are the multi-part, multi-capability semantics the UCC gap audit
(flyto-cloud J05) names: a quadruped must stand before it walks, and a
humanoid's arm and legs are separate parts. The contract already had
`requires`. Without `establishes`, nothing could say which call satisfies a
requirement. Without `occupies`, a host could only hold a whole resource.
Both keys are optional additions to v1, following the 2.36/2.39/2.40
pattern; there is no v2 schema.

## Verified

- Contract suites with this tree's `src`: 369 passed.
- Release closure in a fresh `.venv` with `.[dev,browser]` (CI's extras):
  - `check_documentation`, `check_brand_identity`, lock reproducibility and
    `pip_audit` passed;
  - the documented Ruff list plus the two changed files passed;
  - `python -m build` and `twine check` passed;
  - `npm audit --audit-level=high` passed.
- `pytest -m 'not browser and not e2e'`: 5,349 passed, 63 failed. The same
  command on unmodified origin/main fails 64 tests, and no test fails only
  on this branch; they need network or external services.
- `flyto-index verify --full-scan --strict`: only `weak_scan_taint` fails,
  and it fails identically on origin/main. This is the existing
  `api/routes/mcp.py` -> `mcp_handler.py` -> `cli/recipe.py` flow recorded in
  the 2026-10-13 ecosystem adapters handoff.

## Not verified

- **Host enforcement.** No host enforces `requires`, `establishes` or
  `occupies` yet, neither `capability_host` here nor Flyto2 Cloud. This is
  the schema only.
- **GitHub CI.** Not run: GitHub Actions is locked by a billing issue across
  the organization.
- **Release.** Not released to PyPI.

## Follow-ups

- `capability_host`: refuse a call whose `requires` the resource does not
  report, and hold per part when `occupies` is declared.
- Flyto2 Cloud: per-part leases and precondition checks from the contract,
  then pin 2.41.0.
- Declare `establishes` and `occupies` in the robotics and Home Assistant
  packs (PR #138) where they apply.
