# Reverse-Engineering Toolkit — Hook Robustness + Session Reaper

## Scope

A hardening pass on the `reverse.*` toolkit (Phase 1-3 + the sourcemap
strengthening pass — see the prior handoffs in this directory), not a new
phase and no catalog/module-count change. Fixes two of the four gaps
identified when reviewing the toolkit's overall completeness: `reverse.hook`
only wrapping functions that already existed at install time, and no
cleanup path for sessions abandoned mid-workflow. The other two gaps stay
out of scope: process-local session state is an accepted architectural
constraint (unchanged since Phase 1, mirrors `browser_sessions`), and
Phase 4 (real semantic deobfuscation) remains blocked on Node.js
infrastructure that doesn't exist in this codebase.

## What Changed

### Part 1 — `reverse.hook` robustness (`src/core/browser/reverse_session.py`)

- `_HOOK_SCRIPT_TEMPLATE` rewritten: the target property is now trapped with
  `Object.defineProperty(parent, key, {get, set})` instead of a one-time
  direct overwrite. The `set` trap re-wraps any value assigned to the
  property (including its first-ever assignment, if the property didn't
  exist at install time); the `get` trap always returns the current wrapped
  version.
- Falls back to the old one-time direct wrap only if `defineProperty` throws
  (non-configurable built-ins) — narrower behavior for that specific case,
  not a regression, since reassignment-survival never worked there anyway.
- `remove_hook`'s restore path: `delete parent[key]` (removes the accessor),
  then `parent[key] = currentRaw` (restores a plain data property holding
  whatever the last real value was).
- No Python-level API change — `install_hook`/`remove_hook`/`list_hooks`/
  `get_hook_records` and `reverse.hook`'s params/output schema are untouched.
  `capture_args`/`capture_result`/`max_records`/ring-buffer/`safeSerialize`
  logic is unchanged.
- Verified empirically with a Playwright scratch script (4 scenarios: hook
  before the page defines the property, hook survives reassignment, hooking
  an existing built-in like `Math.max`, reload persistence) before touching
  the real module — same "verify empirically first" discipline as prior
  phases.

### Part 2 — Session idle-timeout reaper

- New `src/core/session_reaper.py`: `touch_session`/`untrack_session`
  (stamp/clear a last-activity timestamp), `reap_stale_sessions` (one sweep
  — anything idle past `timeout_s` gets closed/detached, best-effort,
  exceptions logged and swallowed, then removed from its session dict and
  from the activity map; a session with **no** activity entry is left
  alone), `reaper_loop` (sleep/sweep/repeat until `CancelledError`,
  `timeout_s` defaults from `FLYTO_SESSION_IDLE_TIMEOUT_S` env var, 1800s
  default).
- Wired into all three transports identically:
  - `src/core/mcp_handler.py`: `execute_module()`/`handle_jsonrpc_request()`
    gained a `session_activity` param; `touch_session`/`untrack_session`
    called at every resolve/mint/remove point for both browser and debugger
    sessions.
  - `src/core/mcp_server.py`: module-level `_session_activity` dict; reaper
    task started at the top of `async_main()`, cancelled (and awaited)
    before the existing EOF cleanup loops.
  - `src/core/api/state.py`: `ServerState.session_activity`.
  - `src/core/api/routes/mcp.py`: passes `state.session_activity` through to
    `handle_jsonrpc_request()`.
  - `src/core/api/routes/modules.py`: this route has its own independent
    session-resolution logic (from Phase 1) — mirrors the same
    `touch_session`/`untrack_session` calls directly.
  - `src/core/api/server.py`: reaper task started/cancelled in `create_app()`'s
    `lifespan`. Also fixed a small pre-existing gap noticed while touching
    this code: shutdown previously only closed `browser_sessions`, never
    detached `debugger_sessions` — now does both.
- Both session types (`browser_sessions` and `debugger_sessions`) are reaped
  uniformly — `debugger_sessions` never had a reaper either, so fixing only
  one would have been a half-measure.

## Key Design Decisions (see DECISIONS.md)

1. `Object.defineProperty` is one mechanism that fixes both the
   lazy-property and reassignment gaps at once — verified against 4 concrete
   scenarios before writing any real code.
2. 30-minute default idle timeout: generous enough that a human actively
   debugging (including long pauses at a breakpoint) won't trip it; an
   intentional, documented tradeoff.
3. Absence of activity data means "leave alone," not "reap" — protects any
   session minted by a code path that doesn't (yet) call `touch_session`.
4. Both session types reaped the same way, via the same shared module, wired
   into all three transports with the same call shape already established
   for `browser_sessions`/`debugger_sessions`.

## Verification

- Extended `tests/modules/test_reverse_modules.py`'s `TestReverseSubPhaseC`
  with two new e2e cases against real Chromium: hook-before-define and
  hook-survives-reassignment (both against `window.lazyAppFn`). All existing
  hook tests (built-in hook, reload persistence, removal) pass unchanged —
  full file: 48 passing tests.
- New `tests/core/test_session_reaper.py` (15 tests): pure unit tests
  against `reap_stale_sessions`/`touch_session`/`untrack_session`/
  `reaper_loop` using fake session objects and synthetic timestamps — no
  real sleeping, no browser.
- `tests/core/test_mcp_server.py` extended with `TestSessionActivityTracking`
  (2 tests): confirms `browser.launch` populates `_session_activity` and
  `browser.close` clears it. Full file: 11 passing tests.
- `python -m py_compile` on every touched file; `create_app()` smoke-tested
  directly to confirm `session_activity`/`debugger_sessions` attributes
  exist on server state.
- No catalog/module-count change — no doc-count sweep needed.
