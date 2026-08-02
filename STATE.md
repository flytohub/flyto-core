# Flyto2 Core State

## Current State

- MCP clients no longer have to guess whether a connection is ready or keep a
  fragile server-side session alive. Core supports the stateless MCP
  2026-07-28 request model, publishes discovery and cache guidance, validates
  HTTP request mirrors before execution, and still accepts handshake-based
  clients from 2024-11-05 through 2025-11-25.
- Warroom deterministic verification v1 exists in `flyto-core`: it can build a
  redacted site graph, generate replay scenarios, execute module assertions, and
  emit JSON/Markdown evidence packs. LLM review is disabled by default and
  advisory only.
- The generated catalog currently exposes 468 modules across 85 categories, and
  the bundled recipe inventory contains 41 recipes.
- Project memory structure has been bootstrapped for repeatable workflow and
  validation handoffs.
- The repository already contains workflow assets and CI for maintained recipe
  bundle tests.
- Core is positioned as the validation layer for frontend, engine, admin, and
  enterprise deployment smoke loops.
- Python runtime code and tests use one canonical package identity, `core`.
  The suite rejects `src.core` imports because duplicate module identities can
  split auth, registry, and security state inside one process.
- Security-sensitive test exceptions are fixture-scoped. Collection-time
  private-network and verification-auth overrides are rejected by contract.
- The browser-contract JavaScript runtime is declared and locked in
  `package.json` / `package-lock.json`; `npm audit` is part of local closure.
- Core API, OAuth2 token, and provider-webhook HTTP emitters use the shared
  connect-time DNS and per-redirect SSRF guards. OAuth2 error responses do not
  reflect provider response bodies.
- Azure, GCS, and S3 download destinations are canonicalized and confined to
  `FLYTO_SANDBOX_DIR` before any provider SDK can create or write a local file.
- CSV, YAML, Excel, PDF, image, browser persistence, and document-generation
  paths are canonicalized and confined before any filesystem sink. Browser
  cookie imports and document readers use the same boundary for reads.
- Agent-chain Ollama calls are loopback-only by default. Loopback calls run in
  an exact host/port network scope; explicitly enabled remote calls still use
  the shared DNS-pinned, redirect-revalidating SSRF boundary and do not reflect
  provider error bodies.
- Cryptography uses the patched 48.x line, while Python 3.10+ API and CI
  environments select patched Starlette, pip, and setuptools floors. Python
  3.9 keeps explicit compatibility branches for upstream lines that no longer
  publish patched Python 3.9 releases.
- The 60% line coverage gate measures the maintained orchestration and
  security-control kernel. Pluggable module implementations and product
  overlays remain covered by catalog, contract, and integration suites.
- Source-backed documentation now covers 951 maintained Python files, 5,519
  declarations, 483 literal module registrations, all CLI/HTTP/environment
  surfaces, and all maintained recipe/workflow assets. CI rejects drift,
  missing ownership, broken local links, stale naming, and mailbox violations.
- Workflow status and evidence reads now require bearer authentication.
- `crypto`, `dns`, and `ai` extras express tested optional dependency
  boundaries; the development extra supports the complete offline suite.
- `testing.visual.compare` now delegates real PNG decoding and pixel comparison
  to a detachable TypeScript worker with a scrubbed environment, bounded JSON
  and image inputs, pre-decode PNG dimension checks, non-overwriting diff
  evidence, and content hashes. Its no-mock subprocess matrix covers 101
  distinct cases across identical, pixel-difference, and dimension-mismatch
  tiers.
- Trusted security campaigns may open a task-local exact host/port outbound
  scope. Redirects and connect-time DNS checks remain inside that scope, cloud
  metadata endpoints remain permanently denied, and concurrent tasks do not
  inherit one another's authorization.
- Plugin runtime loads now select only directories recorded by confined
  manifest discovery. External plugin IDs cannot construct filesystem paths,
  symlink escapes are rejected, and MCP header-decoding failures return a
  stable generic error instead of exception details.

## Release Blockers

- No repo-specific release blocker is recorded from this audit.
- Cross-repo production readiness still depends on remote CI stability and on
  adding stronger enterprise airgap smoke recipes.
- Browser/E2E integrations that require external services, browsers, or
  credentials remain environment-backed evidence and are not inferred from the
  offline suite.
- `reverse.*` (CDP debugger, Phase 1 + Phase 2, hardened 2026-07-25) known
  risks: session state (`ReverseSession` objects, keyed by `debugger_session`
  id) is process-local, matching the existing `browser_sessions` constraint
  across all three transports (STDIO MCP, HTTP MCP, plain REST) — a
  `debugger_session` id minted by one server process cannot be resolved by
  another; this remains an accepted constraint, not something planned for
  redesign. Cleanup is now three-layered: explicit `reverse.detach`/
  `browser.close` (primary path), a shared idle-timeout reaper
  (`src/core/session_reaper.py`, 30 min default via
  `FLYTO_SESSION_IDLE_TIMEOUT_S`) wired into all three transports that
  closes/detaches sessions with no recorded activity past the timeout, and
  the STDIO transport's EOF-cleanup loop as a final backstop. A session
  abandoned mid-workflow (crash, disconnect) no longer leaks its Chromium
  process/CDP session for the server's entire lifetime, though process-local
  scoping is still unchanged. `reverse.hook` now traps the target property
  with `Object.defineProperty` (get/set accessor) instead of a one-time
  overwrite, so it survives both a page assigning the property after install
  and a page reassigning it later; the one remaining known limitation is
  narrower — a path whose *immediate parent* object doesn't exist yet at
  document-start (e.g. `myNamespace.fn` where `myNamespace` is itself
  lazily created) still can't be trapped. See DECISIONS.md for the
  pause/resume design rationale, the CDP-freeze caveat, and the hook/reaper
  redesign rationale.
- `reverse.code` (Phase 3) requires the optional `jsast` extra
  (`tree-sitter`, `tree-sitter-javascript`, `jsbeautifier`) — raises a clear
  `pip install 'flyto-core[jsast]'` error if it isn't installed. Unlike the
  rest of `reverse.*`, it needs no permission (no browser/CDP access, no code
  execution) and does not depend on `reverse_session` state at all. It only
  beautifies and structurally searches JS source text — real semantic
  deobfuscation is `reverse.deobfuscate` (Phase 4, see below).
- `reverse.sourcemap` requires no extra pip dependency (hand-rolled VLQ
  decoder) and no permission, same reasoning as `reverse.code`. It never
  fetches an external `.map` file itself — the caller uses `http.get`
  (already SSRF-guarded) for that and passes the fetched text in. It only
  resolves generated-to-original locations and reads `sourcesContent` that
  was already embedded in the source map — it cannot fetch an original file
  that isn't inlined.
- `reverse.request_breakpoint` (request-level XHR/fetch breakpoints via
  `DOMDebugger.setXHRBreakpoint`) reuses the same `Debugger.paused`
  pause/resume pipeline as script breakpoints, so it carries the same
  CDP-freeze caveat and process-local session scoping as the rest of
  `reverse.*`. `reverse.attach` now reuses an existing enabled session on the
  same page instead of always detaching and recreating one (pass
  `force_new=True` for the old behavior) — this changes what a redundant
  `reverse.attach` call returns (`reused: true` plus the session's existing
  snapshot) but not what a fresh attach on a new page returns. See
  `DECISIONS.md` (2026-07-25 request breakpoint / session reuse entry).
- `reverse.deobfuscate` (Phase 4) requires a system-installed Node.js 22 or
  24 on `PATH` plus a one-time `npm install` in
  `src/core/modules/atomic/reverse/deobfuscate_worker/` — raises a clear
  `ModuleError` naming the exact fix if either is missing. Unlike
  `reverse.code`, it is gated behind a new deny-by-default `code.execute`
  permission, since its `webcrack` engine unconditionally evaluates the
  input inside an `isolated-vm` sandbox. It manages its own dedicated Node.js
  subprocess (spawned and killed per invocation) rather than the generic
  JSON-RPC plugin runtime (`src/core/runtime/manager.py`), which was found
  to have unenforced resource limits, no kill-on-timeout, and no wiring from
  plugin manifests into `ModuleRegistry` — not something to build on
  silently. Does not include `restringer`: the npm-published package is
  maintained by an unofficial fork whose dependency tree has dropped the
  `isolated-vm` sandbox the canonical `HumanSecurity/restringer` project
  still declares. See `DECISIONS.md` (2026-07-25 deobfuscate entry).

## Verification Matrix

| Gate | Command | Scope |
| --- | --- | --- |
| Project memory | `bash scripts/lint-project-memory.sh` | Required docs, handoffs, architecture headings, secret-like material |
| Documentation | `python scripts/check_documentation.py` | Generated drift, ownership, catalog, local links |
| Brand | `python scripts/check_brand_identity.py` | Flyto2 naming and approved public aliases |
| Dependencies | `PYTHON=.venv/bin/python bash scripts/lock-deps.sh` plus `pip_audit` | Canonical base lock and vulnerability scan |
| Audited lint | CI Ruff command in `.github/workflows/ci.yml` | Changed maintenance, API security, dependency-boundary surfaces |
| Offline tests | `python -m pytest -m 'not browser and not e2e'` | Full offline suite plus 60% control-kernel coverage gate |
| JS runtime | `npm ci --ignore-scripts && npm run audit` | Locked jsdom runtime and dependency audit |
| Build | `python -m build && twine check dist/*` | Wheel/sdist integrity and metadata rendering |
| Indexer | `flyto-index verify . --full-scan --strict --json` | Repository closure and 90-point docs budget |

## Last Verification

Verified locally on 2026-08-02:

- project memory, documentation, brand, generated catalog/reference, and
  audited plus changed-surface Ruff checks passed;
- 2,336 tests passed, 13 skipped, 273 deselected, with 61.39% coverage;
- Python `pip-audit` and npm audit both reported 0 vulnerabilities;
- `actionlint` accepted the PyPI publishing workflow and its pinned
  `pypa/gh-action-pypi-publish` v1.14.2 commit;
- wheel and source distribution built, and Twine validated both artifacts;
- Flyto2 Indexer strict full scan passed 19/19 checks with 0 warnings/failures,
  docs score 100, README score 100, 0 secret findings, and 0 high-risk taint
  flows;
- exact code SHA `31cbf19c18455056fd9db9473c519bd72a724be2` passed remote
  CI `30751451499`, Security `30751451672`, and CodeQL `30751451016`.
  GitHub then reported zero open code-scanning, Dependabot, and secret-scanning
  alerts.
