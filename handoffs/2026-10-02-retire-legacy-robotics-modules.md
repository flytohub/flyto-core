# Retire the legacy robotics module pack

Owner: claude
Branch: claude/retire-legacy-robotics
Date: 2026-10-02

## What changed

`flyto-modules-robotics` (`robotics.move` / `robotics.turn` / `robotics.stop`,
an HTTP client for a Flyto2 gateway on the robot) is retired, with owner
approval. Core never depended on it; this removes what existed only to test or
illustrate it.

- Deleted `scripts/verify-robotics-registration.sh`. It verified only that pack
  and was called from nowhere (no CI job, script or doc).
- Deleted `tests/modules/test_robotics_outcome.py`. It skipped unless the pack
  was installed, and CI never installed it.
- `tests/modules/test_robotics_vision_agent_outcome.py`: removed
  `TestRoboticsDeclaresAndDoesNotDispatch`, which had the same skip guard, and
  its docstring bullet. The vision and agent tests are unchanged. The file name
  was kept to avoid churn.
- `tests/core/test_outcome_declaration_coverage.py`: removed the three
  `robotics.*` entries and their comment from `UNDECLARED`, which may only
  shrink. The rule that an absent optional package is not read as deletions
  stays, and its docstring no longer names the pack.
- `src/core/plugin/loader.py`, `src/core/api/routes/extensions.py`, `STATE.md`,
  `docs/API.md`: illustrative names changed to `flyto-modules-example` /
  `flyto-plugin-example`. Only docstrings and comments changed. Note that the
  `InstallExtensionRequest` docstring also appears as an OpenAPI schema
  description.
- Regenerated `docs/reference/*`. Updated the source-inventory tokens in
  `docs/MIGRATION_STATUS.md` and `docs/WHITEPAPER.md` (one more line). Added a
  `CHANGELOG.md` Unreleased/Removed entry.

Left alone on purpose:
- `tests/core/api/test_extensions.py` keeps `flyto-modules-robotics` /
  `Flyto_Modules_Robotics` as fake test vectors. It never installs anything, and
  the assertions rely on that exact spelling.
- `DECISIONS.md` and older `CHANGELOG.md` entries are history.
- `docs/API.md`'s "`robotics` is ambiguous between the two kinds" is a
  generic bare-name example.

## Why

The architecture forbids a Flyto2 gateway on the robot. Motion reaches equipment
through an external adapter (`ros2.generic` in flyto-robotics). The deleted
tests and verifier only covered the retired pack.

## Verified

- `pytest -m 'not browser'` against the worktree source (local `.venv`,
  `PYTHONPATH=src`): 4,758 passed, 178 skipped, 64 failed. All 64 failures are
  environmental and match clean `origin/main`: 63 in `tests/test_hints.py`
  (`Cannot find module 'jsdom'`, because the worktree has no `npm ci`) and
  `tests/test_version_identity.py` (the venv's installed Core is the main
  checkout's editable install). The same two files on a clean `origin/main`
  worktree gave 64 failed / 2 passed.
- The touched tests (`test_outcome_declaration_coverage.py`,
  `test_robotics_vision_agent_outcome.py`, `tests/core/api/test_extensions.py`):
  129 passed.
- `scripts/check_documentation.py` (after `generate_reference.py` and the
  inventory-token update), `check_brand_identity.py`,
  `check_release_drift.py` (2.33.0) and `lint-project-memory.sh`: pass.
- `flyto-index verify --strict --full-scan`: 20 pass / 0 warn / 1 fail. The
  failure is `weak_scan_taint`, one medium-confidence path_traversal finding
  `flyto-66be6a7449f057065a6429e5`, and it reproduces identically on a clean
  `origin/main` worktree with the same local indexer. It is pre-existing and
  not introduced here.
- `flyto-index task validate`: overall fail, for pre-existing reasons only.
  Repository-wide ruff reports errors in untouched files (e.g.
  `examples/agent_demo/run.py`). The focused pytest had 17 passed and 0 failed,
  but missed the coverage floor that a single file cannot reach. Ruff on the
  edited files reports the same 8 style findings as before the change.

## Not verified

- Package build/twine, npm audit and `pip_audit` were not run. No dependency or
  packaging file changed.
- `tests/core/api/test_extensions.py` still uses the old name as test data, so
  a repo-wide grep for `flyto-modules-robotics` still finds it there.

## Follow-ups

- Archive `flytohub/flyto-modules-robotics` and deprecate any PyPI release.
- Companion flyto-cloud PR #413 removes the pin from every requirement set, the
  CE lock and the Builder catalog.
