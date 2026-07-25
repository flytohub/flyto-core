# Reverse-Engineering Debugger, Phase 1

## Scope

Adds a `reverse.*` module category: an interactive JavaScript debugger built
on Chrome DevTools Protocol's Debugger domain. Attach to a live page,
list/search loaded scripts, set breakpoints, pause execution, inspect call
frames, evaluate expressions in a paused scope, and step through code. This is
Phase 1 of the reverse-engineering toolkit (see `ROADMAP.md` 0.5); function
hooking, network-initiator tracing, WebSocket capture, and deobfuscation/AST
tooling are explicitly out of scope and are separate follow-up phases.

## What Changed

- `src/core/browser/reverse_session.py`: `ReverseSession`, a thin CDP wrapper
  (sibling of `BrowserDriver`) owning the script cache, breakpoint table, and
  pause/resume/step state via a dedicated `asyncio.Event` — not
  `BreakpointManager`, which solves a different cross-process human-approval
  problem. See `DECISIONS.md` 2026-07-25 for the rationale.
- Nine new modules under `src/core/modules/atomic/reverse/`: `attach`,
  `detach`, `scripts` (list/get_source/search), `breakpoint` (set/remove),
  `wait_paused`, `resume`, `step` (over/into/out), `get_call_frames`,
  `evaluate_on_call_frame`.
- `browser.debug` added to `_DANGEROUS_PERMISSIONS` in
  `src/core/module_policy.py` (deny-by-default) — `evaluate_on_call_frame` can
  read in-memory locals/closures, and a paused debugger freezes the page.
- `debugger_session` registry wired through all three transports (STDIO MCP in
  `mcp_server.py`, HTTP MCP in `api/routes/mcp.py`, plain REST in
  `api/routes/modules.py`), mirroring the existing `browser_session` pattern
  in `mcp_handler.py`'s `execute_module()`.
- Catalog reconciled to 461 modules across 85 categories
  (`src/core/catalog_facts.py`); docs regenerated and the module-count prose
  hand-fixed across README/ARCHITECTURE/STATE/PROJECT/CHANGELOG/docs tree, and
  the `pyproject.toml`/`server.json`/`demo.py` public-description citation
  contract kept in sync (see `tests/test_public_metadata.py`).

## Known Limitations (see STATE.md)

- `debugger_session` state is process-local, exactly like `browser_session`
  state — a session minted by one server process cannot be resolved by
  another.
- Cleanup is manual for Phase 1: `reverse.detach` is the primary path; the
  STDIO transport's EOF loop best-effort `detach()`s any remaining sessions.
  There is no reaper/timeout thread for sessions abandoned mid-workflow.
- A paused debugger freezes the page's JS/renderer; other `browser.*` steps
  issued against the same page before `reverse.resume` will block until their
  own timeout (expected CDP semantics, documented in `DECISIONS.md`).

## Verification

- `tests/modules/test_reverse_modules.py`: 22 e2e tests against a real
  Chromium instance, covering attach/list/get_source/search/detach (sub-phase
  A) and breakpoint/pause/resume/step/evaluate (sub-phase B).
- `python scripts/check_documentation.py` passes.
- `bash scripts/lint-project-memory.sh` passes.
- Full offline suite (`pytest -m "not browser and not e2e"`) shows no new
  failures versus the pre-existing baseline (the only failures are
  `tests/test_hints.py`'s Windows/Node-jsdom environment gap, unrelated to
  this change and reproducible on the unmodified tree).
