# Decisions

## 2026-08-08 - Policy has a plugin dimension, and it can only narrow

Decision: `enforce_module_policy` takes the plugin a module arrived from, and
three environment variables scope policy to it — `FLYTO_PLUGIN_GRANTS`
(`plugin:permission` pairs), `FLYTO_PLUGIN_DENYLIST`, `FLYTO_PLUGIN_ALLOWLIST`.
A plugin module is checked against its own grants only; the process-global
`FLYTO_GRANTED_PERMISSIONS` does not reach it. The global module filter runs
first, so the plugin dimension can never widen what a plugin may run.

Reason: with one global grant set, a plugin that *honestly* declared
`required_permissions: [shell.execute]` was asking the operator to grant
shell.execute to every module in the process — flyto-core's own and every other
plugin's. Declaring a permission is how a plugin tells the truth about itself,
and it must not be how it acquires reach. An operator who granted shell.execute
so flyto-core could run a build step has not granted it to everything they
install afterwards.

Ownership is assigned, never claimed. The registry stamps the plugin whose
`register_all` is running into the module's metadata and overwrites whatever the
module supplied. The lie worth blocking is not "I am plugin B" but "I am no
plugin at all", because the empty owner is the one the global grant still
covers — so a module registered during a plugin load that supplies
`plugin: ""` is corrected to the loading plugin, and a module registered with no
metadata at all is given the minimum needed to stay attributable rather than
defaulting to first-party.

The marker is cleared in `finally`, so a plugin that raises part-way through
registration cannot leave its name attached to the next plugin's modules.

Scope: this bounds what a plugin's modules may do *inside this process*. It does
not bound a plugin that runs as its own process — nothing here can, and a design
that claims otherwise is describing a sandbox flyto-core does not have.

## 2026-08-08 - A module may declare the capability it provides

Decision: `register_module` accepts `provides_capability`, a single capability
id in the vocabulary a Flyto2 Space uses to bind work to resources. It is stored
in module metadata and read back through `ModuleRegistry.capabilities()`, which
returns `{capability: [module_id, ...]}`. It is optional, defaults to empty, and
almost every module leaves it unset.

Reason: this is the plugin contribution point, read side. Before it, installing
a package added a step to the builder but told the host nothing — a Space's
evidence layer could not learn that a capability had become available until an
operator hand-typed its name into a command somewhere else. "Install the plugin
and the loop can use it" was not expressible.

A capability with several providers is returned whole rather than resolved here.
Which provider runs is a binding decision the host makes with the resources it
has; discarding one would be this registry deciding something it cannot know.

Scope, stated because it is easy to over-read: this serves plugins that arrive
through the Python `flyto.modules` entry point. It is one binding, not the
ecosystem's contribution point — a plugin written in another language cannot use
it at all, and the language-neutral manifest that would serve those is a
separate, unbuilt contract.

`build_module_metadata` takes the new field last and with a default, so callers
outside this repository keep working unchanged.

## 2026-08-08 - Sandbox guard coverage is a CI property, not an author's habit

Decision: every module that declares a path-shaped parameter must route it
through `validate_path_with_env_config`, and
`tests/core/test_write_sink_coverage.py` walks the registry to enforce that on
every run. A parameter may be exempted only by an entry in
`NON_FILESYSTEM_PARAMS` stating what the value actually addresses — a JSONPath,
a URL segment, a remote host path — and the exemption is void the moment the
module's source contains a filesystem call.

Reason: the guard was already centralized and already correct. Every published
arbitrary file read/write advisory against this project
(GHSA-2956-977x-2w3r, GHSA-p34x-fmph-9fjx, GHSA-xchh-cp84-9838,
GHSA-hmq9-xw4w-7ppc, GHSA-wc94-386q-5478, GHSA-p64w-hgfm-824v) is the same
defect: a module that did not call it. Fixing them one report at a time never
converged, because each wave patched the modules that had been named and left
the ones that had not — GHSA-p64w explicitly notes the prior waves missed
`browser.download`. Centralization without a coverage check only moves the
failure from "the guard is wrong" to "the guard was not called", which is
harder to see and just as exploitable. A registry-wide audit at the time this
decision was made found 13 further unguarded modules that no one had reported.

Consequence: adding a module with a path parameter now forces one of two
explicit acts — call the guard, or write down why the parameter is not a path.
Neither can be skipped silently. The cost is that the default sandbox
(the process working directory) is now actually enforced on modules that
previously ignored it, which is a breaking change for callers that passed
absolute paths outside it; `FLYTO_SANDBOX_DIR` is the supported way to widen it.

## 2026-08-08 - The outbound boundary is a host check, not only a URL check

Decision: `core/utils.py` owns three outbound guards, not one.
`enforce_outbound_url` keeps the http(s) path; `enforce_outbound_service_url`
parses the host out of a non-HTTP endpoint (`redis://`, `ws://`, a proxy URL);
`enforce_outbound_host` guards a bare hostname for raw TCP. All three share one
policy — loopback allowed, `FLYTO_ALLOWED_HOSTS` allowed,
`FLYTO_ALLOW_PRIVATE_NETWORK` allowed, otherwise resolve and reject private,
link-local, metadata, or unresolvable — and one resolver, `resolve_guard_ip`,
promoted out of `port.check`. `tests/core/test_outbound_guard_coverage.py`
enforces that every module with a network-shaped parameter reaches one of them.

Reason: `validate_url_ssrf` only understands http(s), so every module that took
a bare host or a `redis://` endpoint had no guard available to call. That is
why the gap was structural rather than careless: Redis, MySQL, SMTP, SSH, the
CDP endpoint, the browser proxy and the network probes were reaching arbitrary
internal addresses with no shared primitive to reach for, and `port.check` had
quietly grown the only correct host resolver in the codebase — the one whose
IPv6 fail-open was GHSA-v7q9-pr72-5fmv. A guard nobody can call is not a
boundary.

Decision: loopback stays allowed for infrastructure connections. Reason:
self-hosted deployments legitimately point Redis, MySQL and SMTP at
`localhost`, and blocking that breaks real operation without closing any path —
a workflow that can reach loopback can already do so through the module's own
default configuration. The attack this bounds is reaching *elsewhere* on the
private network, above all the cloud metadata endpoint.

Consequence: workflows that deliberately target a private host now need
`FLYTO_ALLOWED_HOSTS` or `FLYTO_ALLOW_PRIVATE_NETWORK=true`. Unresolvable hosts
are refused rather than attempted, which is a behaviour change for callers that
relied on a connection error to probe DNS. The coverage test is MRO-aware
because guards are legitimately inherited (`LLMClientMixin` holds the
`ollama_url` guard for `agent.chain` and `agent.autonomous`); a same-file scan
would report those as unguarded and train readers to ignore the test.

## 2026-08-02 - Plugin IDs select discovered directories; they never construct paths

Decision: `PluginManager` records the resolved directory associated with each
validated manifest during discovery. A later `load_plugin(plugin_id)` request
validates the external identifier and uses it only as a dictionary key; it no
longer joins the request value, or naming variants derived from it, onto the
plugin root. Discovery also rejects directory symlinks that resolve outside the
configured root.

Reason: a manifest ID and its physical directory name are separate identities.
Constructing candidate paths from a route parameter unnecessarily coupled them
and left filesystem probes dependent on external input, even though manifest
validation blocked common traversal strings. The discovery map both preserves
namespaced IDs whose directory names differ and gives the runtime a simple
invariant: every path used by language detection and entry-point validation was
enumerated and confined before any load request selected it.

Decision: MCP header decoder exceptions are server-side details. The HTTP
transport returns one fixed `invalid Mcp-Name header encoding` message rather
than reflecting `str(exc)` into a JSON-RPC response.

Reason: current decoder errors are intentionally generic, but keeping exception
text on a remote response path makes that safety depend on every future decoder
implementation. A stable protocol message preserves diagnostics semantics
without exposing paths, parser internals, or chained exception data.

## 2026-07-25 - reverse.deobfuscate (Phase 4): own Node.js subprocess, not the generic plugin runtime; webcrack only, not restringer; new code.execute permission

Decision (delivery mechanism): `reverse.deobfuscate` manages its own Node.js
subprocess directly (`asyncio.create_subprocess_exec('node', worker.mjs, ...)`
in the module's `execute()`) rather than going through the existing polyglot
JSON-RPC plugin runtime (`src/core/runtime/manager.py`/`process.py`/
`languages.py`, documented in `docs/PLUGIN_SDK.md`), even though that system
already declares a `node` language config.

Reason: investigation before writing any code found the generic plugin
runtime unfinished in ways that matter here. `ProcessConfig`'s declared
`max_memory_mb`/`max_cpu_percent` are never enforced anywhere. An `invoke()`
timeout (`process.py`) raises `PluginTimeoutError` but never kills the
subprocess — the abandoned process keeps running. Restart backoff is
declared but unused. Most importantly, a `plugin.yaml` manifest's `modules:`
list is never wired into `ModuleRegistry` — there is no code path that turns
a plugin manifest into a callable module today, and no example `plugin.yaml`
exists anywhere in this repo. Building "the strongest" implementation of a
security-sensitive, code-executing feature on top of that would either
inherit those gaps silently or require first fixing shared plugin
infrastructure with a much larger blast radius than one new module. A
dedicated, self-contained subprocess call is simpler, fully reviewable in one
module, and explicitly fixes the exact "no kill on timeout" gap found in
`process.py` — `reverse.deobfuscate`'s own timeout path calls `proc.kill()`
and awaits `proc.wait()` before raising, unlike the shared runtime.

Decision (Node.js requirement): require a system-installed Node.js 22 or 24
on `PATH`, plus a one-time `npm install` in the sidecar worker directory
(`src/core/modules/atomic/reverse/deobfuscate_worker/`) — the same BYO-runtime
tradeoff the existing plugin `node` language config already makes, and the
same shape of tradeoff `reverse.code`'s `jsast` pip extra makes (clear error
if missing, not auto-installed).

Reason: this repo has no reliable, working Node.js auto-bundling mechanism.
Playwright's bundled Node is reachable only via the private, undocumented
`playwright._impl._driver`, already known to be fragile under PyInstaller
(`src/core/browser/driver.py`'s `_find_external_node()` exists specifically
to work around it). The `~/.flyto/node/` fallback referenced by
`driver.py`'s `_NODE_VERSION` constant has no downloader implemented
anywhere — dead code, not a working mechanism (confirmed by search across
the repo). Building that downloader is a separate, large, not-yet-scoped
project (`tasks.md`), and bundling it into this change would repeat the same
scope-creep this repo's own Phase 3 decision explicitly avoided. Requiring a
system Node.js delivers Phase 4's functional goal now without taking on that
unsolved dependency — Node.js 22/24 is also webcrack's own stated
requirement (even-numbered releases only, since its `isolated-vm` dependency
warns against non-LTS/odd-numbered Node ABI breakage), not an arbitrary
choice made here.

Decision (engine: webcrack only, not restringer, in this first version):
use `webcrack` (npm, published directly by its author `j4k0xb`) as the sole
deobfuscation engine. Do not add `restringer` in this version, despite it
being part of the original plan approved with the user.

Reason: verifying both packages directly (not just trusting search-summary
descriptions) before implementing found two things that changed the plan.
First, the npm-published `restringer` package (`2.2.0`) is maintained by
`ctrl_esc`/`ctrl-escp/restringer`, a 23-star fork — not the canonical,
598-star `HumanSecurity/restringer`. The fork's published `package.json` has
dropped `isolated-vm` as a dependency, while the canonical GitHub repo's
`package.json` still declares it — an unresolved, unexplained discrepancy in
exactly the dependency the whole "safe dynamic evaluation" story rests on,
not something to build a security-relevant feature on without further
verification. Second, reading `webcrack`'s own source
(`deobfuscate/vm.ts`, `createNodeSandbox()`) showed it unconditionally uses
its own `isolated-vm`-backed sandbox (10s per-eval timeout, isolate disposed
after use) as a normal part of every run — there is no "pure zero-execution"
mode when using webcrack at all, which invalidated the original plan's
safe/full mode split (safe was assumed to mean "webcrack only, zero
execution"; that assumption was wrong). webcrack alone already covers
string-array decoding, control-flow-flattening reversal, self-defending/
debug-protection bypass, and webpack/browserify unpacking — restringer's
40+ modules would be a genuine deeper pass, but not required to deliver
Phase 4's stated goal. Adding it later, once its npm situation is resolved
or it's vendored from the canonical repo at a pinned commit, is tracked in
`tasks.md` rather than blocking this change.

Decision (permission): gate the whole module behind one new deny-by-default
permission, `code.execute` (added to `module_policy.py`'s
`_DANGEROUS_PERMISSIONS`), rather than trying to make part of the module
permission-free the way `reverse.code`/`reverse.sourcemap` are.

Reason: confirmed with the user directly, and now on firmer ground than
originally planned — since webcrack itself always executes sandboxed code
(see above), there was never going to be a genuinely zero-execution mode to
carve out an exemption for, unlike `reverse.code`'s pure AST parsing (which
DECISIONS.md's Phase 3 entry below explicitly says "has no elevated
capability to gate"). One permission covering the whole module is simpler to
reason about and review than a per-call conditional gate would have been.

Decision (packaging): ship the worker's `package.json`/`package-lock.json`/
`worker.mjs` (not `node_modules`) as package data for the
`core.modules.atomic.reverse` package (`pyproject.toml`
`[tool.setuptools.package-data]`, `MANIFEST.in`), so a `pip install
flyto-core` still gets the worker source even though `npm install` remains a
separate, required, manual step.

Reason: the repo's package layout (`package-dir = {"" = "src"}`,
`[tool.setuptools.packages.find] where = ["src"]`) only ships what's under
`src/` by default, and the sidecar needs its own directory (not the root
`package.json`, which is explicitly scoped `flyto2-core-test-runtime` for
jsdom browser-contract tests only — conflating a production runtime
dependency with a test-only manifest would be confusing and wrong). Placing
the worker under `src/core/modules/atomic/reverse/deobfuscate_worker/`
keeps it shippable via ordinary Python packaging with two small, explicit
additions rather than a new packaging mechanism.

## 2026-07-25 - reverse.request_breakpoint reuses the Debugger pause pipeline; reverse.attach gains session-snapshot reuse

Decision (request breakpoint): implement request-level breakpoints via CDP's
`DOMDebugger.setXHRBreakpoint`/`removeXHRBreakpoint` — the same mechanism
Chrome DevTools' Sources > XHR/Fetch Breakpoints panel uses — rather than
building a second, Fetch-domain-based interception/pause/continue pipeline.
`ReverseSession` tracks active request breakpoints in a new
`_request_breakpoints` dict keyed by the URL substring itself (CDP has no
separate breakpoint-id concept here, unlike script breakpoints; setting the
same URL twice is idempotent).

Reason: a request breakpoint's *pause* is just another `Debugger.paused`
event (`reason: "XHR"`), which `ReverseSession._on_paused`/`_paused_event`
already handles — so `reverse.wait_paused`, `reverse.resume`,
`reverse.get_call_frames`, and `reverse.evaluate_on_call_frame` all work
against a request-breakpoint pause with zero changes. A Fetch-domain
interception design would have needed its own pause/continue/fail/fulfill
state machine parallel to the existing one, duplicating exactly the
cross-process-scoping and CDP-freeze concerns already documented below for
script breakpoints, for no behavioral gain. `_enrich_pause` now also passes
through CDP's `data` field unfiltered (reason-specific detail, e.g. the
matched URL for an `"XHR"` pause) since its shape varies by pause reason and
guessing at field names across reasons risks silently returning a wrong key.
Verified against a real Chromium instance: setting a breakpoint on `ping.json`,
triggering `fetch('/ping.json')`, and observing `reason == "XHR"` in the pause
result (`tests/modules/test_reverse_modules.py::TestReverseSubPhaseF`).

Decision (session-snapshot reuse): `reverse.attach` now checks whether
`context['reverse_session']` is already enabled and attached to the exact
same page object (`existing.page is browser.real_page`) before deciding to
detach; if so, it returns that session's existing snapshot (script cache,
script/request breakpoint counts, hook count, pause/network-enabled state)
instead of detaching and calling `ReverseSession.enable()` again. A new
`force_new` param (default `False`) opts back into the old unconditional
detach-and-recreate behavior.

Reason: before this, calling `reverse.attach` a second time on the same page
— e.g. a recipe defensively re-attaching without knowing whether a debugger
session was already live — silently discarded every breakpoint, request
breakpoint, and installed hook, and forced Chrome to re-send the full
`Debugger.scriptParsed` backfill for no reason. Comparing the CDP session's
page object directly (rather than, say, comparing URLs) avoids a false-positive
reuse across a same-URL navigation that actually tore down and recreated the
underlying page. If `browser.real_page` differs (navigated to a new page/tab)
or no session exists yet, behavior is unchanged — detach the stale session
(best-effort) and create a fresh one. Verified against a real Chromium
instance: setting a script breakpoint, reattaching without detaching, and
confirming the breakpoint is still present and the session object identity is
unchanged (`tests/modules/test_reverse_modules.py::TestReverseSessionReuse`).

Both additions strengthen Phase 1 rather than opening a new phase — no new
permission, no new transport wiring (the existing `is_reverse =
module_id.startswith("reverse.")` checks in `mcp_handler.py` and
`api/routes/modules.py` already cover the new module id by prefix).
Reconciled the generated catalog to 467 modules across 85 categories.

## 2026-07-25 - reverse.hook rewritten on Object.defineProperty; session idle-timeout reaper added

Decision (hook redesign): `reverse.hook`'s injected JS (`_HOOK_SCRIPT_TEMPLATE`
in `src/core/browser/reverse_session.py`) now traps the target property with
a single `Object.defineProperty(parent, key, {get, set})` accessor instead of
directly overwriting `parent[key]` once at install time.

Reason: the previous one-shot overwrite had two known gaps — a property the
page assigns *after* the init script runs was never wrapped (nothing existed
yet to overwrite), and a page reassigning an already-hooked property silently
clobbered the hook, ending recording with no error. The accessor closes both
gaps at once: the `set` trap re-wraps whatever value gets assigned (including
the first-ever assignment of a not-yet-defined property), and the `get` trap
always returns the current wrapped version. Verified empirically with a
Playwright scratch script across 4 scenarios (hook-before-define, hook survives
reassignment, hooking an existing built-in like `Math.max`, and reload
persistence) before touching the real module, per this codebase's established
"verify empirically first" discipline. `defineProperty` throwing (some
built-ins are non-configurable) falls back to the old one-time direct wrap —
narrower, but not a regression, since that path never worked with reassignment
anyway. Remaining known limitation: a path whose *immediate parent* object
does not exist yet at document-start (e.g. `myNamespace.fn` where
`myNamespace` itself is lazily created later) still cannot be trapped — the
common cases (`window.X`, existing built-in namespaces) are unaffected. No
Python-level API change — `install_hook`/`remove_hook`/`list_hooks`/
`get_hook_records` and `reverse.hook`'s params/output schema are untouched.

Decision (session reaper): added `src/core/session_reaper.py`, a shared
idle-timeout sweep wired identically into all three transports (STDIO
`mcp_server.py`, HTTP MCP `api/routes/mcp.py`, plain REST
`api/routes/modules.py`) plus the HTTP server's `lifespan` (`api/server.py`).
It reaps both `browser_sessions` and `debugger_sessions` uniformly — closing
or detaching, then removing from the relevant dict and from the shared
`session_activity` timestamp map.

Reason: before this, a session was only ever cleaned up by an explicit
`browser.close`/`reverse.detach` call, or (STDIO only) on process EOF. A
session abandoned mid-workflow — client crash, disconnect, forgotten cleanup
— leaked a live Chromium process and/or CDP session for the server's entire
lifetime. This applied to `browser_sessions` too (it never had a reaper
either), so both are swept the same way rather than fixing only the newer
`debugger_sessions` as a half-measure. Default timeout is 30 minutes
(`FLYTO_SESSION_IDLE_TIMEOUT_S` env override), generous enough that a human
actively debugging — including long pauses at a breakpoint while thinking —
is unlikely to trip it; this is an intentional, documented tradeoff, not a
bug. A session with **no** entry in `session_activity` is deliberately left
alone rather than treated as stale — absence of activity data is not evidence
of staleness, and protects any session minted by a code path that (for now
or forever) doesn't call `touch_session`. This also fixed a small pre-existing
gap noticed while wiring the HTTP server's shutdown path: it previously closed
`browser_sessions` on shutdown but never detached `debugger_sessions`.

Both items leave the accepted architectural constraints from earlier phases
in place: sessions are still process-local (not shared across server
instances or restarts — unchanged since Phase 1, mirrors `browser_sessions`'
pre-existing design) and Phase 4 (real semantic deobfuscation) remains
blocked on Node.js infrastructure that doesn't exist in this codebase yet
(see the `reverse.code` decision below).

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
