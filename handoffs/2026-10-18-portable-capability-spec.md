# Portable capabilities: contracts shipped with the thing that performs them

Owner: claude
Branch: claude/portable-capability-spec
Date: 2026-10-18

## What changed

- `docs/specs/PORTABLE_CAPABILITY_SPEC.md` (new): how a device adapter or a
  trained policy ships its own `flyto.capability-contract.v1` contracts in a
  `flyto.pack.v1` pack that any host can read. Guidance only; the rules stay in
  `docs/CAPABILITY_CONTRACT.md` and `docs/specs/PACK_MANIFEST_SPEC.md`.
- `examples/packs/tabletop-arm/flyto-pack.json` (new): a learned pick-and-place
  capability (movement, bounded target point, `distance_to` evidence in frame
  `table`, 2 cm tolerance, photo artifact) and its `role: safe_stop` stop.
  Manifest only: there is no runner, so it is not installable.
- `tests/core/pack/test_portable_capability_example.py` (new): the example
  validates, the page's excerpt equals the file's row, the four verdicts the
  page lists are what `judge` returns, and an unbounded number is refused.
- `docs/README.md` index entry; `CHANGELOG.md` Unreleased entry.

## Why

The owner wants learned skills packaged as capability contracts that live with
the model, not inside Flyto2. `flyto.pack.v1` already makes that possible;
publishers had no page that said how, or how to write a contract for a
learned policy. No new format was added.

Rejected: a separate skill registry, and a JSON-Schema or WoT TD extension
written now (both listed under "Not covered yet").

## Verified

- New tests: 7 passed (`pytest --no-cov tests/core/pack/test_portable_capability_example.py`).
- Drift check: changing the page's tolerance to 0.03 made the excerpt test fail
  (1 failed, 6 passed); restored.
- The example's verdicts were also run by hand with `judge`: 1 cm usable;
  5 cm, wrong frame and no observation not usable.

## Not verified

- GitHub Actions (organization billing lock).
- Whether Flyto2 Cloud installs a pack: the pack spec states Cloud does not yet
  call `install_pack`. This page describes the format, not Cloud ingestion.

## Follow-ups

- When flyto-core #139 (`establishes`, `occupies`) is released, add them to the
  learned-policy table.
- After Proof #2 (flyto-cloud ROADMAP "CONVERGED P0"): the AM-ARM200 adapter's
  first contracts follow this page.
