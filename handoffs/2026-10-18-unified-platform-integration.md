# Unified platform integration (2.41.0)

Owner: claude
Branch: feat/unified-platform-integration-20261018 (local, cut from origin/main 795d07e)
Date: 2026-10-18

## What changed

Every open flyto-core branch is brought onto one linear branch by
cherry-pick, oldest base first, with no merge commits:

- `feat/runtime-capability-bridge-client-20261011` (PR #135): the opt-in
  Runtime capability bridge and its workspace_id follow-up.
- `integration/consolidation-20261011` (PR #136): #135 plus a merge of
  `backup/local-work-20261011` (82bfbe1). The backup was an older copy of the
  same bridge on a 2026-09-30 base. Its code, tests and handoff are superseded
  by #135. What it added beyond #135 is carried in one commit: the
  ARCHITECTURE / PROJECT / docs/README paragraphs that #136's merge kept, and
  the 2026-09-30 decision record in DECISIONS.md.
- `feat/iot-ecosystem-adapters-20261013` (PR #138), then `claude/j06-interop`.
  The branch's merge of main (62889a8) is dropped; the resulting tree equals
  `claude/j06-interop` plus the bridge.
- `claude/contract-states-channels` (PR #139), then `claude/j05-ucc-contract`.
- `claude/jprep-real-world`, `claude/portable-capability-spec` (PR #140).

Three commits are new here:

- `core.pack.compatibility` gains `contract.resource_states` (since 2.41.0).
  The matrix was written on 2.40 and would have passed a pack that declares
  `establishes` / `occupies` with `min_host: 2.40.0`.
- The Runtime bridge admits only the literal loopback addresses 127.0.0.1 and
  ::1. It used a plain aiohttp session and accepted `localhost`, which
  `test_plain_aiohttp_sessions_exist_only_for_fixed_vendor_hosts` refuses; the
  file is on that allowlist now, with the reason.
- CHANGELOG: one 2.41.0 section (2026-10-18) for everything above. The
  optional IoT package is listed separately because the Core wheel does not
  carry it.

Generated references (`docs/reference/`, TOOL_CATALOG, inventory counts in
prose) were regenerated at every conflicting step, never hand-merged.

## Verified

Python 3.11 venv, `pip install -e '.[dev,browser]'`, `npm ci --ignore-scripts`:

- `scripts/check_documentation.py`, `scripts/check_brand_identity.py`,
  `scripts/check_release_drift.py`, `bash scripts/lint-project-memory.sh`,
  `scripts/lock-deps.sh` (no lock diff), `npm run audit`: pass.
- CI ruff surfaces, and ruff on every Python file the branch changes: pass.
- `pytest -m 'not browser and not e2e'`: 5461 passed, 174 skipped, coverage
  69.13%.
- `examples/integrations`: 74 passed, ruff pass, wheel builds.
- `python -m build` + `twine check`: both artifacts pass.
- `flyto-index verify --strict --full-scan`: 20 pass, 1 fail. The failure is
  the `taint/path_traversal` finding `66be6a74...` (mcp route to
  `src/cli/recipe.py:80`); the same fingerprint fails on origin/main 795d07e.

## Not verified

- Browser and e2e suites; `pip_audit` (needs network).
- MCP `task(action='validate')`: the MCP server is pinned to another root.
- No live Runtime bridge, IoT device or hardware.

## Follow-ups

- The pre-existing taint finding on the recipe path.
- Tag and publish 2.41.0 only after the owner accepts one release carrying all
  of the above.
