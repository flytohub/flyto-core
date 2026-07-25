# Reverse-Engineering Toolkit — Request Breakpoints + Session-Snapshot Reuse

## Scope

Two small, independent strengthening passes on the `reverse.*` toolkit
(Phase 1), not a new phase:

1. **Request-level breakpoints**: pause execution when an XHR/fetch request
   URL matches a substring, instead of only being able to break at a known
   script/line.
2. **Session-snapshot reuse**: `reverse.attach` no longer unconditionally
   discards an already-attached session's state when called again on the
   same page.

## What Changed

- `src/core/browser/reverse_session.py`:
  - Added `set_request_breakpoint`/`remove_request_breakpoint`/
    `list_request_breakpoints`, backed by CDP's `DOMDebugger.setXHRBreakpoint`/
    `removeXHRBreakpoint`. Tracked in a new `_request_breakpoints` dict keyed
    by the URL substring (CDP's own identity for this kind of breakpoint —
    no separate breakpoint-id). A hit is just another `Debugger.paused` event
    (`reason: "XHR"`), so no changes were needed to pause/resume/step/
    call-frame inspection.
  - `_enrich_pause` now also passes through CDP's `data` field unfiltered
    (reason-specific detail, e.g. the matched URL for an `"XHR"` pause).
  - Added `page`/`is_enabled` properties and a `snapshot()` method (script/
    breakpoint/request-breakpoint/hook counts, pause/network-enabled state)
    so a caller can decide whether to reuse an existing session.
  - `detach()` now also clears `_request_breakpoints`.
- `src/core/modules/atomic/reverse/request_breakpoint.py` (new):
  `reverse.request_breakpoint` — set/remove/list actions, same
  `browser.debug` permission gate as every other session-bearing `reverse.*`
  module.
- `src/core/modules/atomic/reverse/attach.py`: new `force_new` param
  (default `False`). When an existing session is already enabled and
  attached to the exact same page object, `reverse.attach` now returns that
  session's `snapshot()` (plus `reused: true`) instead of detaching and
  recreating it. Version bumped to 1.1.0.
- `src/core/modules/atomic/reverse/wait_paused.py`: output now also includes
  `data`, so a request-breakpoint pause's matched URL is inspectable without
  a second round-trip.
- `src/core/modules/atomic/reverse/__init__.py`: wired in
  `request_breakpoint`.
- No transport changes needed — `mcp_handler.py`/`api/routes/modules.py`
  already gate on `module_id.startswith("reverse.")`, which covers the new
  module id by prefix.
- Catalog reconciled to 467 modules across 85 categories; docs regenerated
  and the module-count prose hand-fixed across
  README/ARCHITECTURE/STATE/PROJECT/CHANGELOG/docs tree, plus the
  `pyproject.toml`/`server.json`/`demo.py`/`tests/test_public_metadata.py`
  public-description citation contract.

## Known Limitations (see STATE.md)

- Request breakpoints share every existing `reverse.*` process-local session
  scoping and CDP-freeze constraint — no new risk surface, just a second way
  to trigger the same pause mechanism.
- Session reuse compares page object identity
  (`existing.page is browser.real_page`), not URL — a same-URL navigation
  that actually tore down and recreated the page is correctly treated as a
  new page (no reuse), not incorrectly matched by URL string equality.

## Verification

- `tests/modules/test_reverse_modules.py`: added `TestReverseSubPhaseF`
  (request breakpoint set/list/trigger-pause/resume/remove, asserting
  `reason == "XHR"` against a real Chromium instance) and
  `TestReverseSessionReuse` (reattach-without-detach reuses the session and
  preserves a previously-set breakpoint; `force_new=True` discards it). Full
  file (60 tests) passes against a real Chromium instance.
- `python scripts/check_documentation.py` passes.
- `pytest tests/test_public_metadata.py` passes (citation contract updated).
