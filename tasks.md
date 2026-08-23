# Tasks

## Open

- `PluginService` / runtime plugin lifecycle: the out-of-process plugin path
  (`src/core/api/plugins/service.py`, `src/core/plugin/`) is still outside the
  discovery transaction. It is omitted from the coverage kernel, has no
  equivalent rollback, and its `PluginLoader.discover_plugins` returns its own
  live mapping. Not addressed by the registry 1.4.0 work, open since
  2026-08-08. This item is scoped to that runtime lifecycle only — it is not a
  statement about the plugin surface as a whole; other plugin surfaces are
  documented open separately (see the next item).
- Other plugin surfaces documented open in this repository, listed so the item
  above is not read as covering them. Per `docs/specs/PLUGIN_MANIFEST_SPEC.md`:
  the `flyto.plugin.v1` manifest/adoption slice is implemented but deliberately
  inert; `RuntimeInvoker.set_plugin_manager` has no caller anywhere, leaving
  `_plugin_manager` as `None` so a workflow step cannot reach a plugin
  subprocess; and the limits on what flyto-core can bound for a plugin running
  as its own process are recorded there rather than resolved. Neither the
  registry 1.4.0 work nor its acceptance touched or assessed these.

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

- Added the three-module verified deterministic domain-solver baseline,
  registration-validated semantic contracts, hashed manifest/catalog projection,
  canonical evidence receipts, and focused known-answer/falsification coverage.

- Implemented the first inert `flyto.plugin.v1` supply-chain/adoption slice:
  strict bounded recursively canonical closed-schema validation, shared
  pre-canonicalization unsafe-Unicode rejection for values, keys, endpoints,
  and allowlists with stable non-reflective errors, offline descriptor-bound artifact digest verification
  with a portable race-safe nofollow fallback and hard cap, derived environment
  names, exact no-DNS locality checks with a small unique bounded ASCII
  host-authority allowlist, immutable detached results, and focused hostile-input
  and descriptor-race coverage. Existing-ID collision checks accept only an
  exact list/tuple of at most 256 unique bounded control-free ASCII reverse-DNS
  IDs, validated before membership without consuming arbitrary iterables. It does not install,
  load, start, download, execute, or provide OS containment.

- Closed the capability/extension/runtime change set on 2026-08-12: all pinned
  checks and 2,785 non-browser/e2e tests pass. Codex also fixed a routed-plugin
  policy alias that could omit the actual handler manifest's permissions; the
  regression pins both resolved identity and denial. Commit `0a353ff` passed
  clean-tree strict Indexer verification 19/19.
- Made plugin discovery a transaction over the registry, keyed on what each
  `register_all()` actually registered: stale modules a plugin stopped
  providing are removed, a failed load restores displaced rows to their real
  owner, and the contribution record is replayed only into a registry that
  began the pass empty. Closed the registry torn-read window in the same work:
  every public read holds `_discovery_lock` for its whole body,
  `discover_plugins`/`refresh` return a copied plugin mapping on every path,
  and `PluginInfo` is frozen so a caller cannot edit registry state through a
  value it was handed. `REGISTRY_VERSION` is 1.4.0. Verified and accepted
  2026-08-11 on branch `main`: six pinned checks, Core module-contract proof,
  strict Indexer verification, and an independent 78 registry / 25 catalog test
  replay all passed. Accepted against these flyto coding implementation
  revisions (SHA-256, not Git commit hashes): docs — `job_453f3754aa2041309060b75a`
  / `ebeb0ebfcab2d56bec576a944dcadd23fa197ff9726c558379df1c76eb12e341`;
  source/tests — `job_ad0baf4f580e4bc6aaac37de`
  / `b391189517db77146c4ab51def48ed7ada04fb30308296480e2e083df46bf65c`;
  catalog/tests — `job_8d8d49019afa402a8c503aa0`
  / `a08df544401cf36a54dfe4f6fc084512cb3035a9febf885442baca5cd8366f15`.
- Settled the `registry_plugin_contract` coverage question: the pinned argv in
  `.flyto/coding.yaml` now passes `--no-cov`, so the check reports the registry
  contract it was pinned to prove rather than the project-wide coverage floor
  it inherited from `addopts`.
- Hardened the remaining reported module boundaries: agent Ollama requests are
  localhost-only by default and use the guarded HTTP path, while the reported
  file readers and browser/document writers enforce `FLYTO_SANDBOX_DIR` before
  touching the filesystem. Updated supported dependency floors and CI tooling
  so the Python 3.10+ audited environment has no known package vulnerabilities.
- Closed the reported outbound-request and cloud-download gaps: core API,
  OAuth2, and provider webhooks now use connect-time/per-redirect SSRF guards;
  Azure, GCS, and S3 downloads enforce the filesystem sandbox before writes.
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
