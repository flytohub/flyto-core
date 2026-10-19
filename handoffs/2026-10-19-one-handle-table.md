# One canvas-handle table; routed exits are not fallen into; trigger host settings declared

Owner: claude
Branch: lane/one-handle-table (from core-integ f75f3a2)
Date: 2026-10-19

## What changed

- `src/core/canvas_handles.py` — the one table that says which declared port a
  canvas handle id means (exact id or `handle_id`, fixed aliases `body_out`,
  `done_out`, `item`, side prefix stripped, a generic handle = the module's
  ordinary port) and which events an output handle routes under.
  `validation/connection.py` resolves ports with `resolve_port`;
  `engine/workflow/routing.py` routes with `handle_events`. Neither keeps an
  alias table of its own (d32f0be).
- `engine/workflow/routing.py` / `engine.py` — the router records steps reached
  through a routed exit (a port that is not the source's ordinary one: branch
  true/false, loop body/done, error) and `next_in_order` skips them when a step
  falls through in list order, unless the finishing step names that step as its
  ordinary successor (a47312a).
- `modules/atomic/flow/trigger.py` — declares `timezone`, `webhook_provider`,
  `require_signature`, `triggers`: hidden, `skipDefault`, no secret (9050139,
  3bed738). Catalog and docs reference regenerated.

## Why

Cloud saves failed with "Port not found: output" while the engine ran the same
edge: two alias tables disagreed. The Cloud acceptance suite then showed the
engine ran both branches of an if/else, one extra loop iteration, and an error
handler after success, and that every schedule-trigger save was refused because
the trigger's settings were undeclared.

## Verified

- Failing first: `tests/core/test_one_handle_table.py` 471 failed / 51 passed
  before, 522 passed after; `tests/core/test_routed_steps_not_fallen_into.py`
  3 failed / 2 passed before, 5 passed after; trigger settings absent on
  core-integ, present here (`tests/core/test_trigger_host_settings.py`).
- Non-browser suite (`pytest -m 'not browser'`): 6,292 passed, 6 failed, 192
  skipped. The 6 are `tests/core/pack/test_portable_pack.py` (1) and
  `test_standalone_server.py` (5), which fail identically on core-integ
  f75f3a2. (`tests/test_hints.py` needs jsdom from the repo's node_modules.)
- `generate_reference.py`, `generate_catalog.py`, `check_documentation.py`,
  memory lint PASS; ruff clean on the changed files except pre-existing import
  order in `flow/trigger.py` and `engine/workflow/__init__.py`.
- Fixed-scanner `verify --strict`: 21/0/0.
- End to end through the Cloud editor (lane/editor-acceptance): T01 schedule,
  T03 if/else, T04 loop pass with this branch and fail with core-integ.

## Not verified

- CI on GitHub; a release; Cloud pins still name 795d07e.
- `registry/resolve.py` `enrich_port_handle_metadata` still derives each port's
  `handle_id` on its own; the catalog-wide test holds it to the table's reading,
  but it does not import the table.
- Workflows whose authors relied on falling from a routed target into the next
  listed step (no edge drawn) now stop at the end of that branch.

## Follow-ups

- Bump the core pin in flyto-cloud (test.yml, e2e.yml, mcp-closed-loop.yml) to
  this branch's merge in the same round as lane/editor-acceptance.
