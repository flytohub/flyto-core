# Adapter developer kit: offline pack conformance, compatibility matrix, template pack (J17 preparation)

Owner: claude
Branch: claude/jprep-real-world (from origin/main at 795d07e)
Date: 2026-10-18
Evidence level: **D2** (local tests against the template's simulated axis). J17
in the flyto-cloud 2026-10-16 gap audit stays a hypothesis: no third party, no
real device and no firmware-upgrade run has used this.

## What changed

- `src/core/pack/conformance.py`, `flyto pack conform <pack-dir> [--trusted-key ID=FILE] [--static-only] [--json]`:
  static checks (manifest, tree digest, signature, a `role: safe_stop` row for
  anything that needs a stop, evidence on every actuating capability,
  `min_host` against the matrix) and, unless `--static-only`, running checks
  through the existing `install_pack` path, talking to the runner directly:
  the stop answers ok, an in-bounds actuation completes, a value past a
  published maximum is refused rather than clamped, every call is answered.
  `not_applicable` is never a pass. Reports `evidence_level: D2`,
  `hardware_acceptance: NOT_VERIFIED`. Exit 0 conformant, 1 otherwise.
- `src/core/pack/compatibility.py`: the versioned matrix (version 1) of
  feature -> first flyto-core that accepts it (contract 2.35.0, optional
  fields 2.36.0, pack 2.37.0, absolute targets 2.38.0, recovery semantics
  2.39.0, evidence display keys 2.40.0), read by the `compatibility` check.
  `docs/specs/ADAPTER_COMPATIBILITY_MATRIX.md` renders it; a test keeps them
  equal. Its verified pack × device × host table is deliberately empty.
- `examples/packs/adapter-template/`: a `flyto.pack.v1` pack with three
  contracts (bounded non-idempotent `move_to` with `distance_to` evidence,
  `read_position`, `halt` with `role: safe_stop`) and a stdlib JSON-RPC
  runner over a simulated axis. Follows the PORTABLE_CAPABILITY_SPEC guidance
  on PR #140 (unmerged); adds no format.

No second executor or schema: the runner is reached through `install_pack`
and the existing plugin transport; the matrix is read by the one check.

## Verified (local)

- `PYTHONPATH=src .venv/bin/python -m pytest tests/core/pack/ --no-cov`: 101 passed.
  The new test file proves each check against a template copy broken one way
  (clamping runner, runner that refuses everything, stop that refuses, runner
  that dies, no stop row, no evidence, stale or missing `min_host`, changed
  files after signing, invalid manifest).
- Full non-browser, non-E2E suite (`-x`): 5163 passed, 174 skipped, then stopped at 1 failure,
  `tests/test_hints.py::TestStampSelector::test_native_select_uses_id`: `Cannot find module 'jsdom'`
  in this machine's Node, unrelated to this change; the rest of the suite after it did not run.
- `flyto-index verify --strict`: every check passes except `weak_scan_taint`, one
  pre-existing finding (`api/routes/mcp.py` -> `cli/recipe.py:load_recipe`, path
  traversal, medium confidence) in files this change does not touch.
- `scripts/generate_reference.py` then `scripts/check_documentation.py`: PASS.
- `scripts/check_brand_identity.py`: PASS. Ruff on the touched files: clean.

## Not verified

- GitHub Actions; a real third-party pack; any hardware.
- Running checks on a non-Python runner (Node, Go): the path is the same
  transport, not exercised here.
- The local venv's installed metadata says 2.31.0, so a CLI run from this
  venv reports `compatibility` fail for a 2.40.0 pack; tests pin 2.40.0.

## Known limits

- Evidence is declared and checked for presence, not judged: the pack
  protocol carries no observation channel, and the host judges evidence from
  adapter observations (`core.capability_host`).
- The plugin manager logs "crashed (exit: None)" when a pack is uninstalled
  after a graceful shutdown; pre-existing, not changed here.
