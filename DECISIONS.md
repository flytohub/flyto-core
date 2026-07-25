# Decisions

## 2026-07-25 - reverse.sourcemap hand-rolls VLQ decoding and never fetches anything itself

Decision: `reverse.sourcemap` implements its own Source Map v3 base64-VLQ
decoder and mapping-segment parser (`src/core/modules/atomic/reverse/sourcemap.py`)
rather than depending on a pip package, and never performs an HTTP fetch —
it only accepts the source map JSON (or a `data:` URI) as a plain parameter.

Reason (no dependency): the one plausible candidate, the `sourcemap` package
on PyPI, has an active GitHub repo but its last **PyPI** release is 2017 —
installing it would pull 8-year-old code. The Source Map v3 spec is small
and has been stable for a decade, so hand-rolling the decoder (~150 LOC) was
judged lower-risk than a stale dependency, consistent with `reverse.code`'s
same reasoning for choosing actively-maintained `tree-sitter`/`jsbeautifier`
over alternatives. The decoder was verified against hand-computed VLQ test
vectors (round-tripping an independent encoder through the decoder across
positive/negative/multi-continuation values, plus a full mappings string
with known per-segment deltas) before writing `tests/modules/test_reverse_sourcemap.py`,
the same "verify empirically first" discipline used for Phase 1's CDP
line-number semantics and Phase 2's hook/network/WebSocket mechanics.

Reason (no fetch): `Debugger.scriptParsed`'s `sourceMapURL` field was already
captured by `ReverseSession` and already exposed by `reverse.scripts`
(action=list) — no changes needed there. When `sourceMapURL` points to an
external `.map` file (not an inline `data:` URI), fetching it is a security-
sensitive operation: `http.get` (`src/core/modules/atomic/http/get.py`)
explicitly wires SSRF protection (`validate_url_with_env_config`,
`guarded_aiohttp_request` from `src/core/utils.py`) into every request,
including redirect-hop revalidation. That protection is not ambient — a new
module fetching a URL itself would need to reuse those same helpers
correctly or risk bypassing SSRF guarding entirely. Since the fetch is a
single already-solved step (`http.get`), `reverse.sourcemap` takes the
already-fetched (or already-decoded) text as input instead of duplicating
that security-sensitive code, keeping the module itself session-independent
and permission-free, matching `reverse.code`'s precedent exactly.

## 2026-07-25 - reverse.code (Phase 3) is pure Python, no Node.js, and no permission gate

Decision: `reverse.code`'s beautify/list_functions/list_strings/find_calls
actions are built entirely on `tree-sitter` + `tree-sitter-javascript` (AST
parsing/querying) and `jsbeautifier` (reformatting) — all pure-Python,
prebuilt-wheel pip packages added as a new optional `jsast` extra. No Node.js
subprocess is involved anywhere in this module.

Reason: research into a Node.js-based route (needed for real AST tooling
like `@babel/parser`/`acorn`/`terser`) found the cross-platform Node
invocation problem is not currently solved in this codebase. Playwright's
bundled Node binary is reachable only via `playwright._impl._driver`, a
private module with no compatibility guarantee — and this exact binary is
already known to be unreliable (`src/core/browser/driver.py`'s
`_find_external_node()` exists specifically to work around it crashing
under PyInstaller `--onefile`). The apparent fallback, `~/.flyto/node/`
(referenced by a `_NODE_VERSION` constant in `driver.py`), turned out to
have no downloader anywhere in the repo — it's dead code, not a working
auto-install mechanism. `sandbox.execute_js` was also considered and
rejected as an internal primitive: it's denylisted by default and only
exposes stdout/stderr/exit_code, no structured-output channel. Building
reliable Node infrastructure is its own project, not something to bundle
into this module's scope.

Decision: `reverse.code` declares `required_permissions=[]` — the only
`reverse.*` module with no permission gate.

Reason: every other module in this category is gated behind `browser.debug`
because it reads live in-memory browser state (locals, closures, hook
records, captured network/WebSocket traffic) or freezes the page.
`reverse.code` operates on a plain JS source string passed as a parameter —
it never creates or touches a CDP session, never touches a live page, and
never executes the JS it analyzes (tree-sitter only parses syntax structure;
jsbeautifier only reformats text). There is no elevated capability to gate.

Decision: real semantic deobfuscation (control-flow-flattening reversal,
string-array decoding via constant folding) is explicitly out of scope for
`reverse.code` and deferred to a separate, not-yet-started Phase 4.

Reason: those transforms require actually executing/evaluating JS
(Babel/webcrack-style passes), which pure-Python AST tools cannot do, and
which depends on solving the Node-invocation reliability problem above
first. Scoping `reverse.code` to beautify + structural search (functions,
strings, call sites) delivers real value now without taking on that
unsolved infrastructure dependency.

## 2026-07-25 - reverse.* Phase 2 extends ReverseSession instead of a second session type

Decision: `reverse.hook`, `reverse.network`, and `reverse.websocket` (function
hooking, network-initiator tracing, WebSocket capture) all operate on the same
`ReverseSession`/CDP session that `reverse.attach` already creates, rather
than opening a parallel CDP session or session registry for Network/Page
domain work.

Reason: two independent arguments point the same way. First, Chrome only
populates `Network.requestWillBeSent`'s `initiator.stack` with full JS call
frames when the Debugger agent is active — `ReverseSession.enable()` already
calls `Debugger.enable` unconditionally, so a shared session gets rich
initiator stacks for free, while a standalone Network-only session would get
poorer data. Second, `mcp_handler.py`'s `is_reverse = module_id.startswith("reverse.")`
check and the existing `debugger_session` registry (wired across STDIO MCP,
HTTP MCP, and plain REST in Phase 1) already generically cover any new
`reverse.*` module id — extending the one session type meant Phase 2 needed
zero new transport-wiring changes.

Decision: `reverse.hook` wraps a function that already exists at the time
`install_hook()` runs — a built-in available from document start (e.g.
`window.fetch`, `window.Math.max`) or a page-defined function installed after
the page has already loaded it. It does not implement an
`Object.defineProperty`-based lazy-hook guard for a property a page assigns
*after* our init script runs, and it does not defend against the page later
reassigning the same property out from under an installed hook.

Reason: a fully general lazy-hook (trapping assignment of a not-yet-defined,
possibly-deeply-nested property, and re-trapping after reassignment) is
substantially more complex than direct wrapping, and the direct-wrap approach
already covers the two most common real cases (hooking built-in browser APIs,
and hooking an already-loaded page function after navigation). Documenting
the limitation keeps Phase 2's scope matched to its actual engineering cost;
a lazy-hook guard can be added later as a targeted enhancement if a concrete
use case needs it, without changing `reverse.hook`'s params_schema or the
CDP-level mechanism (`Page.addScriptToEvaluateOnNewDocument` /
`Page.removeScriptToEvaluateOnNewDocument`).

## 2026-07-25 - reverse.* CDP debugger uses a dedicated pause/resume primitive, not BreakpointManager

Decision: `ReverseSession` (src/core/browser/reverse_session.py) owns its own
`asyncio.Event` + last-pause-state dict for pause/resume, mirroring the
existing `browser.dialog` pattern (register a page/CDP event listener, block on
an asyncio primitive with a timeout, clean up in `finally`). It does not reuse
`src/core/engine/breakpoints/manager.py`'s `BreakpointManager`.

Reason: `BreakpointManager` is built for human-approval breakpoints with
pluggable stores (in-memory/Redis/HTTP) so a resolution can reach a different
worker process than the one that created the request. That cross-process value
is moot for a CDP debugger session — the live `CDPSession` object only exists
in the process that called `reverse.attach`, so no other process could ever act
on a pause anyway. A dedicated primitive is simpler and keeps the two
breakpoint concepts (human-approval gates vs. JS execution pauses) from
bleeding into each other's data models. This also means `reverse.*` session
state is process-local, exactly like `browser.*` session state (see STATE.md).

## 2026-07-25 - A paused CDP debugger freezes the page; workflow authors must design around it

Decision: document, rather than engineer around, the fact that while a page is
paused at a `reverse.*` breakpoint, the browser freezes that page's
JS/renderer. Any other `browser.*` step issued against the same page before
`reverse.resume` will block until its own timeout, since Chrome will not
service a generic `Runtime.evaluate`-based call while the isolate is paused
(only `reverse.evaluate_on_call_frame`, which uses
`Debugger.evaluateOnCallFrame`, can execute during a pause, and only in the
scope of the paused call frame).

Reason: this is expected CDP semantics, not a flyto-core bug — trying to make
other browser steps "just work" during a pause would require either a fake
queuing layer or silently no-oping calls, both of which would hide real state
from workflow authors. Recipes that use `reverse.*` breakpoints must trigger
the paused code path without awaiting it (fire-and-forget), call
`reverse.wait_paused`, inspect/resume, and only then issue further `browser.*`
steps against that page.

## 2026-07-22 - Documentation is source-backed and release-controlled

Decision: keep concise narrative guides for intent and operations, generate
exhaustive references from Python AST/runtime catalog/repository assets, map
every maintained source/configuration area to documentation, and reject drift,
broken local links, unowned files, stale Flyto2 naming, or unapproved public
mailboxes in CI.

Reason: hand-maintained totals and symbol lists become stale in a 452-module
runtime. Generated inventory proves coverage while narrative docs remain usable.

## 2026-07-22 - Evidence-bearing workflow reads require authentication

Decision: require the active Execution API bearer token for workflow status and
evidence GET routes, not only workflow mutation and replay routes.

Reason: status and evidence can disclose workflow parameters, outputs, errors,
and artifact paths. They are operational data, not public module metadata.

## 2026-07-22 - Optional capability dependencies use explicit extras

Decision: publish `crypto`, `dns`, and `ai` extras, include their dependencies
in contributor validation, and return package-extra install instructions when
a module cannot load its SDK.

Reason: runtime discovery may expose optional modules, but installation and
failure behavior must still be predictable without bloating the base package.

## 2026-07-21 - Runtime identity and test security state are process-safe

Decision: import the installed Python package only as `core`, reject legacy
`src.core` imports, and permit private-network or auth exceptions only through
fixtures that restore process state. Test helpers that load external modules
must sandbox `sys.modules` instead of modifying imported frameworks.

Reason: duplicate package identities and collection-time environment changes
made auth and SSRF controls depend on test order. A security gate must fail
closed under the complete suite, not only when a test runs alone.

## 2026-07-21 - Coverage measures the control kernel

Decision: retain the 60% line gate for the orchestration and security-control
kernel. Atomic modules, third-party adapters, enterprise overlays, test-runtime
packages, and optional plugin implementations use catalog, schema, contract,
and real integration gates and do not dilute the kernel percentage.

Reason: one aggregate percentage across the control plane and hundreds of
independently deployable adapters was permanently red while hiding which
boundary lacked evidence. The split keeps the kernel threshold enforceable
without skipping adapter tests or lowering the threshold.

## 2026-06-23 - Warroom verification is deterministic first

Decision: Warroom pass/fail decisions come from replayable program evidence:
site/action/API/state graphs, module assertions, screenshots, DOM evidence, and
redacted reports. LLM review is opt-in and advisory only.

Reason: Flyto2 Warroom must work as a verification instrument, not a prompt
wrapper. LLM output cannot make a failing deterministic gate pass by itself.

## 2026-06-21 - Project memory is release-controlled

Decision: keep root project memory files, workflow docs, and handoff registry in
the repository and validate them in CI.

Reason: flyto-core is used to prove product loops. Its own workflow expectations
must be durable, visible, and checked.

## 2026-06-21 - Recipes are product contracts

Decision: maintained recipes should represent executable contracts for product
flows and release smoke, not only demos.

Reason: Flyto2 needs closed-loop verification from UI and API behavior back to
backend state, evidence, and release readiness.
