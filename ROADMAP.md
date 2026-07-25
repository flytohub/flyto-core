# Flyto2 Roadmap

## Strategic Priorities

### 0. Warroom Deterministic Verification
- Deterministic graph, scenario generation, replay, report, and LLM-review
  boundary in `flyto-core`
- Multi-route BFS crawler for arbitrary sites
- Stronger state-machine inference, visual diff scoring, and Cloud Warroom UI
  integration

### 0.5. Reverse-Engineering Toolkit
- **Phase 1 (done, 2026-07-25):** `reverse.*` interactive JS debugger on CDP's
  Debugger domain — attach/detach, script list/get_source/search, set/remove
  breakpoints, pause/resume/step, call-frame inspection, and
  `evaluate_on_call_frame`. Gated behind the deny-by-default `browser.debug`
  permission. See `DECISIONS.md` (2026-07-25 entries) for the pause/resume and
  CDP-freeze design rationale.
- **Phase 2 (done, 2026-07-25):** function hooking (`reverse.hook` —
  install/remove/list/get_records via CDP's
  `Page.addScriptToEvaluateOnNewDocument`), network-initiator tracing
  (`reverse.network` — which JS call stack triggered a given request, via
  CDP's Network domain), and WebSocket frame capture (`reverse.websocket`).
  All three extend the same `ReverseSession`/CDP session `reverse.attach`
  creates rather than a second session type. See `DECISIONS.md`
  (2026-07-25 Phase 2 entry) for the rationale and known hooking limitations.
- **Phase 3 (done, 2026-07-25):** `reverse.code` —
  beautify/list_functions/list_strings/find_calls. Pure Python
  (`tree-sitter` + `tree-sitter-javascript` + `jsbeautifier`, new optional
  `jsast` extra), no Node.js. Beautifies minified JS and structurally
  searches its AST. The only `reverse.*` module with no permission gate — it
  never touches a browser/CDP session and never executes the analyzed code.
  See `DECISIONS.md` (2026-07-25 Phase 3 entry).
- **Strengthening pass (done, 2026-07-25):** `reverse.sourcemap` —
  resolve/list_sources/get_original_source. Resolves a generated (minified/
  bundled) code location back to its original source file/line/column/name
  via a hand-rolled Source Map v3 VLQ decoder (no pip dependency — the one
  plausible package on PyPI hasn't been released since 2017). Also
  session-independent and permission-free; never fetches an external `.map`
  file itself (delegates to `http.get`, already SSRF-guarded, as a normal
  workflow step). Not a new numbered phase — it fills a capability gap in
  Phase 1-3 rather than adding a new tier. See `DECISIONS.md`
  (2026-07-25 sourcemap entry).
- **Hardening pass (done, 2026-07-25):** `reverse.hook`'s JS rewritten on
  `Object.defineProperty` so hooks survive both lazy (not-yet-defined at
  install time) properties and later reassignment — narrows the previous
  "only wraps what already exists" limitation down to just an
  immediate-parent-doesn't-exist-yet edge case. Also added a shared session
  idle-timeout reaper (`src/core/session_reaper.py`, 30 min default) wired
  into all three transports, reaping both `browser_sessions` and
  `debugger_sessions` uniformly so a session abandoned mid-workflow no
  longer leaks for the server's full lifetime. Not a new phase — a
  strengthening pass on Phase 1/2, same as the sourcemap entry above. See
  `DECISIONS.md` (2026-07-25 hook/reaper entry).
- **Strengthening pass (done, 2026-07-25):** `reverse.request_breakpoint` —
  set/remove/list request-level (XHR/fetch) breakpoints via CDP's
  `DOMDebugger.setXHRBreakpoint`/`removeXHRBreakpoint`, pausing execution on a
  matching request URL instead of a known script/line — a hit surfaces
  through the same `Debugger.paused` event as a script breakpoint, so
  `wait_paused`/`resume`/`get_call_frames`/`evaluate_on_call_frame` all apply
  unchanged. Also gave `reverse.attach` session-snapshot reuse: reattaching to
  a page that already has an enabled session now returns its existing
  snapshot (script cache, breakpoints, request breakpoints, hooks) instead of
  detaching and rebuilding from scratch, unless `force_new=True`. Not a new
  phase — strengthens Phase 1. See `DECISIONS.md` (2026-07-25 request
  breakpoint / session reuse entry).
- **Phase 4 (done, 2026-07-25):** `reverse.deobfuscate` — real semantic
  deobfuscation (control-flow-flattening reversal, string-array decoding,
  self-defending/debug-protection bypass, webpack/browserify unpacking) via
  the `webcrack` npm package, run in a dedicated Node.js sidecar worker
  (`deobfuscate_worker/worker.mjs`, spawned and killed per invocation) rather
  than the generic JSON-RPC plugin runtime (`src/core/runtime/manager.py`,
  found to have unenforced resource limits and no kill-on-timeout, and whose
  plugin manifests aren't wired into `ModuleRegistry` at all) or Playwright's
  private/fragile bundled Node. This delivers Phase 4's goal via a narrower
  path than originally assumed below: it requires a **system-installed**
  Node.js 22/24 (the same accepted tradeoff the existing plugin `node`
  language config and `reverse.code`'s `jsast` extra already make) rather
  than solving Node auto-bundling — that larger problem (the `~/.flyto/node/`
  downloader remains unimplemented) is sidestepped, not solved, and remains
  open for any future need that requires it. See `DECISIONS.md`
  (2026-07-25 deobfuscate entry) for the full rationale, including why the
  `restringer` npm package was left out of this first version.

### 1. Marketplace Ecosystem
- Template marketplace for buying/selling workflows
- Community-contributed modules
- Rating and review system
- Revenue sharing for creators

### 2. Cloud Execution & Scheduling
- Cloud-based workflow execution
- Cron scheduling (no local machine needed)
- Webhook triggers
- Execution history and logs in cloud

### 3. Team Collaboration
- Shared workspaces
- Role-based access control
- Real-time collaboration
- Version control for workflows

---

## Moat Analysis

| Feature | Moat Strength | Rationale |
|---------|---------------|-----------|
| Marketplace | Strong | Network effects, ecosystem lock-in |
| Cloud Sync | Strong | Cross-device, team collaboration |
| Webhook/Scheduling | Medium | Requires server infrastructure |
| Team Features | Medium | Multi-user permissions |

## Notes

- Core modules remain open source
- Cloud features provide sustainable moat
- Focus on ecosystem over feature parity

## Documentation Maintenance

- Keep generated source and runtime references deterministic and CI-enforced.
- Add real browser/E2E evidence when the required services and credentials are
  available; do not represent skipped integrations as verified.
- Resolve whether plugin HTTP management stays source-only or becomes an
  explicitly mounted authenticated product surface.
