# J05: the reference reading of establishes / occupies (2.41.0, PR #139 taken over)

Owner: claude
Branch: claude/j05-ucc-contract (from claude/contract-states-channels, PR #139)
Date: 2026-10-18

## What changed

- PR #139 was already current with origin/main (`795d07e`, 2.40.0): main is an
  ancestor of `3c5d179`, so nothing was merged in. This branch builds on it.
- `src/core/capability_resource_states.py` (new): the reference reading of
  the two keys, so every host decides the same way.
  - `occupancy_overlaps(first, second)`: two normalized contracts' calls
    conflict unless both declare `occupies` and share no part. A
    `safe_stop` conflicts with nothing.
  - `unmet_requires(requires, established)`: the required states nothing
    established, in `requires` order.
- `tests/core/vectors/capability_contract_resource_states.json`: three new
  sections.
  - `unchanged`: four contracts without the keys, each with the SHA-256 of
    its canonical normalized JSON computed with origin/main's 2.40.0
    `capability_contract.py`. The test recomputes them on 2.41.0, so an old
    contract is shown to hash byte-identically.
  - `overlaps` (7 vectors) and `satisfies` (4 vectors) for the two rules.
- `tests/core/test_capability_contract_resource_states.py`: tests for the
  new sections.
- `docs/CAPABILITY_CONTRACT.md` ("Reading the keys"), the 2.41.0 CHANGELOG
  entry, STATE, the regenerated `docs/reference/`, and the inventory counts
  (994 files / 6,334 declarations).

## Why

UCC gap audit J05 asks for one formal contract authority with conformance
vectors and a reader. The keys were admitted with no reading of them, so
each host would have written its own overlap rule. Flyto2 Cloud now reads
both keys on `claude/j05-ucc-contract` and mirrors these vectors. There is
no new schema and no v2.

## Verified

- Failing first: the new test module failed at collection (ImportError:
  `occupancy_overlaps` not in Core) before the module existed.
- `pytest -q tests/core/test_capability_contract_resource_states.py`: 31 passed.
- `pytest -q tests/core -k contract`: 412 passed.
- `scripts/generate_reference.py`, then `scripts/check_documentation.py`: passed.
- `scripts/check_brand_identity.py`: passed.
- `ruff check` on the changed source and test files: clean.
- `scripts/lint-project-memory.sh`: PASS.
- `flyto-index scan . && flyto-index verify --strict`: every check passes
  except `weak_scan_taint` (exit 2). PR #139's handoff recorded that same
  failure on unmodified origin/main: the `api/routes/mcp.py` ->
  `cli/recipe.py` flow, which this change does not touch.

## Not verified

- The full `pytest -m 'not browser and not e2e'` suite was not re-run here.
  PR #139's handoff recorded it (63 failures, all also failing on main).
- GitHub CI: not run. Actions is billing-locked.
- Not released to PyPI; Cloud does not pin 2.41.0 (it reads stored contracts
  as data and never imports Core).
- `capability_host` still holds a whole resource per call and does not
  check `requires`.

## Follow-ups

- `capability_host`: hold per part with `occupancy_overlaps`, and refuse on
  `unmet_requires`.
- Declare the keys in the robotics and Home Assistant packs where they apply.
- The contract has no key for a call that *ends* a state, so a state stays
  established for the rest of a task. Add one only once a host needs to
  read it.
