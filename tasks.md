# Tasks

## Open

- Add multi-route BFS crawler for arbitrary sites.
- Connect Warroom evidence packs into Flyto2 Cloud UI.
- Add enterprise airgap smoke recipes for no-egress browser/API checks.
- Add recipe fixtures for capability states and report/export flows.
- Keep maintained recipe bundle tests aligned with product-loop contracts.
- Add `restringer` to `reverse.deobfuscate` once its npm publishing situation
  is resolved (currently maintained by an unofficial fork whose dependency
  tree dropped `isolated-vm`), or vendor it from `HumanSecurity/restringer`
  at a pinned commit instead.
- Build a reliable `~/.flyto/node/` auto-download mechanism if a future need
  requires bundled (not system-installed) Node.js — `reverse.deobfuscate`
  sidesteps this by requiring a system Node.js instead of solving it.

## Watch

- Recipes that depend on local credentials or machine-specific paths.
- Browser checks that pass without asserting real page state.
- Module parameter drift that is not reflected in examples or tests.

## Done

- Added `reverse.deobfuscate` (Phase 4 of the `reverse.*` toolkit): real
  semantic deobfuscation via `webcrack`, run in a dedicated Node.js sidecar
  worker spawned/killed per invocation, gated behind a new `code.execute`
  permission. Requires a system-installed Node.js 22/24. Reconciled the
  generated catalog to 468 modules / 85 categories.
- Added `reverse.request_breakpoint` (set/remove/list request-level XHR/fetch
  breakpoints via CDP's `DOMDebugger.setXHRBreakpoint`) and session-snapshot
  reuse in `reverse.attach` (reattaching to the same still-enabled page
  returns the existing session's snapshot instead of detaching and rebuilding
  it, unless `force_new=True`). Reconciled the generated catalog to 467
  modules / 85 categories.
- Hardened the `reverse.*` toolkit: rewrote `reverse.hook`'s injected JS on
  `Object.defineProperty` so hooks survive lazy (not-yet-defined) properties
  and later reassignment (narrower known limitation: immediate parent object
  must already exist), and added a shared session idle-timeout reaper
  (`src/core/session_reaper.py`, 30 min default, `FLYTO_SESSION_IDLE_TIMEOUT_S`
  override) wired into all three transports, reaping both `browser_sessions`
  and `debugger_sessions` uniformly. No catalog/module-count change — no
  new or changed module IDs.
- Added `reverse.sourcemap` (resolve/list_sources/get_original_source):
  hand-rolled Source Map v3 VLQ decoder, no pip dependency, no permission
  gate, delegates external `.map` fetches to the already SSRF-guarded
  `http.get` instead of fetching anything itself. Strengthens Phase 1-3
  rather than adding a new phase. Reconciled the generated catalog to 466
  modules / 85 categories.
- Added Phase 3 of the `reverse.*` toolkit: `reverse.code`
  (beautify/list_functions/list_strings/find_calls) — pure Python
  (`tree-sitter` + `jsbeautifier`, new `jsast` extra), no Node.js, no
  permission gate (never touches a browser/CDP session or executes code).
  Reconciled the generated catalog to 465 modules / 85 categories.
- Added Phase 2 of the `reverse.*` toolkit: `reverse.hook`
  (install/remove/list/get_records), `reverse.network`
  (start/stop/list/get_initiator), and `reverse.websocket`
  (start/stop/list/get_frames) — all extending the same `ReverseSession`/CDP
  session Phase 1's `reverse.attach` creates. Reconciled the generated
  catalog to 464 modules / 85 categories.
- Added the `reverse.*` CDP debugger module category (Phase 1 of the
  reverse-engineering toolkit): attach/detach, script list/get_source/search,
  breakpoint set/remove, wait_paused, resume, step, get_call_frames, and
  evaluate_on_call_frame, gated behind the new deny-by-default `browser.debug`
  permission. Reconciled the generated catalog to 461 modules / 85 categories.
- Added the source-backed documentation contract, technical whitepaper,
  feature/API/configuration/security/operations/testing guides, generated
  declaration/module/CLI/HTTP/environment references, ownership manifest, and
  deterministic drift/link checks.
- Added a Flyto2 brand and approved-mailbox policy gate for public repository
  content.
- Declared `crypto`, `dns`, and `ai` package extras and aligned contributor
  dependencies with the tested capability set.
- Protected workflow status and evidence reads with the Execution API bearer
  token and added regression coverage.
- Expanded CI from one recipe test to documentation, brand, audited lint,
  non-browser tests, npm audit, package/Twine, and strict Indexer gates.

- Added generic `verification.*` module IDs for deterministic verification
  primitives and kept `warroom.*` as compatibility aliases only; engine-owned
  workflows should compose `verification.*`.
- Renamed the emitted deterministic testing model to the core-owned
  `flyto.core.deterministic_verification.v1` while retaining
  `warroom.automation_test_model.v1` as the legacy schema reference.
- Kept Flyto2 product naming out of core defaults; engine artifacts may attach
  a product contract such as `flyto2.automated_product_testing.v1`.
- Added explicit non-LLM execution policy to automation evidence:
  deterministic evidence is the fact source and gate authority; LLM is only an
  optional evidence reviewer.
- Added event-stream and scheduler-loop summaries to
  `automation_test_model.v1` so Product Verification evidence can distinguish
  callback/SSE contracts and durable scheduler contracts from raw replay facts.
- Added `automation_test_model.v1` to Warroom evidence packs so UI/CI can read
  coverage, scenario synthesis, replay, ghost API, invariant, RBAC, and
  evidence-chain results without interpreting raw JSON.
- Added the 90-point Product Verification evidence gate to `warroom.report`
  with focused tests for pass and blocked paths.
- Split `warroom.run` module success from `replay_ok` product success so failed
  deterministic replay evidence remains available to `warroom.report`.
- Made generated Warroom DOM assertions hydration-aware so SPA pages are not
  scored as blank before body text settles.
- Added a dedicated `flyto-verification` Docker image boundary for full-stack
  Product Verification compose/staging smoke.
- Added operator-controlled SSRF dev-port allowlisting so Product Verification
  can replay local/staging browser targets without turning off the SSRF guard.
- Added deterministic graph/scenario/report modules in `flyto-core`.
- Made e2e/scenario test modules execute real module steps.
- Bootstrapped project memory skeleton and lint gate.
