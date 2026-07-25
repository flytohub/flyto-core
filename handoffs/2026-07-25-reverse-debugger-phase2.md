# Reverse-Engineering Debugger, Phase 2

## Scope

Adds three modules to the `reverse.*` category (see
`2026-07-25-reverse-debugger-phase1.md` for Phase 1): function hooking,
network-initiator tracing, and WebSocket frame capture. This closes out
`ROADMAP.md` 0.5's Phase 2 item; deobfuscation/AST tooling remains the sole
remaining Phase 2+ item, deferred as a separate follow-up phase (needs new
npm dependencies and a cross-platform Node invocation path — a different
engineering axis from the CDP-wrapping work here).

## What Changed

- `src/core/browser/reverse_session.py` extended (not replaced) with:
  - Hooking (Page domain): `install_hook()` builds a JS wrapper via a
    placeholder-templated script (`_HOOK_SCRIPT_TEMPLATE`, substituted via
    `.replace()` with `json.dumps()`-encoded values — avoids f-string brace
    escaping and JS-injection from user-supplied `function_path`), installs
    it via `Page.addScriptToEvaluateOnNewDocument` (persists across
    navigation/reload), and immediately `page.evaluate()`s it once so an
    already-loaded page's function gets hooked too. `remove_hook()` calls
    `Page.removeScriptToEvaluateOnNewDocument` and best-effort restores the
    original function on the current page.
  - Network (Network domain): `enable_network()` (idempotent, shared by both
    hooking-adjacent features below) registers `Network.requestWillBeSent`
    and the four `webSocket*` events, bounded to the last 500 requests / 200
    frames per WebSocket connection (oldest dropped, FIFO via dict insertion
    order). `get_request_initiator()` walks the CDP `initiator.stack`'s
    parent chain into a flat list of `{functionName, url, lineNumber,
    columnNumber}` frames.
  - `detach()` extended to best-effort remove all installed hooks and Network
    listeners alongside the existing Debugger-domain cleanup.
- Three new modules under `src/core/modules/atomic/reverse/`: `hook`
  (install/remove/list/get_records), `network`
  (start/stop/list/get_initiator), `websocket`
  (start/stop/list/get_frames) — same conventions as Phase 1 (`category='reverse'`,
  `stability=BETA`, `required_permissions=['browser.debug']`).
- No transport-wiring changes — `mcp_handler.py`'s `is_reverse` prefix check
  and the existing `debugger_session` registry already cover any new
  `reverse.*` module id generically.
- Catalog reconciled to 464 modules across 85 categories; same doc/citation
  sweep as Phase 1 (this time the `tests/test_public_metadata.py` citation
  contract was caught and fixed in the same pass, not after the fact).

## Known Limitations (see STATE.md, DECISIONS.md)

- `reverse.hook` only wraps a function that already exists at install time
  (a built-in from document start, or an already-loaded page function). It
  does **not** implement an `Object.defineProperty`-based lazy-hook guard for
  a property a page assigns *after* our init script runs, and does not
  defend against the page later reassigning the same property. Verified
  empirically: hooking `window.Math.max` survives `page.reload()` and stops
  re-applying after `remove`; a page-defined function assigned by the page's
  own inline `<script>` would NOT be hookable via the persistent path, since
  `addScriptToEvaluateOnNewDocument` runs before any page script — this is
  why the test uses a genuine built-in (`Math.max`), not a page-defined
  function, for the reload-persistence assertion.
- Network/WebSocket capture is bounded (500 requests, 200 frames/connection,
  oldest dropped) to prevent unbounded memory growth on long-lived sessions.
- Same process-local session-registry and manual-cleanup constraints as
  Phase 1 apply (shared `ReverseSession`).

## Verification

- Scratch scripts (not committed) verified each mechanism end-to-end against
  real Chromium before the final test suite was written: hook install/call/
  reload-persistence/remove, network-initiator stack contents, and a raw
  RFC 6455 WebSocket handshake + echo round-trip — the same "verify the CDP
  behavior empirically before trusting the test" discipline that caught
  Phase 1's `scriptParsed` listener-ordering bug.
- `tests/modules/test_reverse_modules.py` extended with sub-phases C
  (hooking), D (network-initiator), E (WebSocket) — 46 tests total (was 22),
  all passing against a real Chromium instance. WebSocket tests use a
  minimal stdlib-only echo server (no new pip dependency — `websockets` is
  present in some dev sandboxes only as an unrelated tool's transitive
  dependency and must not be relied on in CI).
- `python scripts/check_documentation.py` passes.
- `bash scripts/lint-project-memory.sh` passes.
- `tests/test_public_metadata.py` (public-description citation contract)
  passes.
