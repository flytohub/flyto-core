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
- **Phase 4 (not started):** true semantic deobfuscation — control-flow-
  flattening reversal, string-array decoding via constant folding, and other
  transforms that require actually executing/evaluating JS (Babel/webcrack-
  style), which pure-Python AST tools cannot do. Blocked on solving the
  Node.js-invocation reliability problem first: Playwright's bundled Node is
  only reachable via a private, undocumented API (`playwright._impl._driver`)
  already known to be fragile under PyInstaller (see `driver.py`'s
  `_find_external_node()` workaround), and the imagined `~/.flyto/node/`
  fallback has no downloader anywhere in the repo (`_NODE_VERSION` is dead
  code). Needs new npm dependencies and CI audit surface too. A separate
  follow-up phase, not an extension of the Phase 1/2/3 module set.

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
