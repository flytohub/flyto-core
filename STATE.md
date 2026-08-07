# Flyto2 Core State

## Current State

- Both security boundaries are now closed registry-wide and enforced in CI,
  rather than patched per advisory:
  - Filesystem — 88 modules declare a path-shaped parameter; 71 reach
    `validate_path_with_env_config`, 17 are documented as not filesystem paths,
    0 unaccounted. Enforced by `tests/core/test_write_sink_coverage.py`.
  - Outbound network — 57 modules declare a URL/host-shaped parameter; 46 reach
    an SSRF guard, 11 are documented as never reaching the network or as
    validating locally, 0 unaccounted. Enforced by
    `tests/core/test_outbound_guard_coverage.py` (MRO-aware, so inherited
    guards count).
  Exemptions require a written reason and are re-verified each run. The audits
  confined roughly 30 modules that no advisory had named — see CHANGELOG
  `[Unreleased]` and the two 2026-08-08 entries in DECISIONS.md.
- Two breaking changes come with that: paths outside `FLYTO_SANDBOX_DIR`
  (default: the process working directory) are refused, and connections to
  private/link-local hosts need `FLYTO_ALLOWED_HOSTS` or
  `FLYTO_ALLOW_PRIVATE_NETWORK=true`. Loopback is unaffected.
- Package metadata is prepared for the 2.26.12 security patch release. The
  release closes the remaining browser file-write and SSRF gaps the 2.26.11
  hardening waves left open (`browser.download`/`screenshot`/`pdf`,
  `warroom.report`, `verify.report`/`visual_diff`/`run`, `browser.launch`,
  `data.dedup`; `browser.goto`'s www-toggle retry), plus a tar-extract
  symlink (Tar Slip), a `port.check` IPv6 SSRF fail-open, and a regex ReDoS,
  tracked by public GitHub security advisories.
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
- Source-backed documentation now covers 952 maintained Python files, 5,544
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

Verified locally on 2026-08-07 for the 2.26.12 release candidate:

- documentation, brand, generated catalog/reference (5,544 declarations
  across 805 files, regenerated after the fix set), and both the CI's fixed
  audited-surface Ruff list and a full changed-surface Ruff diff (every file
  touched by this release, compared byte-for-byte against its pre-fix
  baseline) passed with zero new findings;
- 2,615 tests passed, 18 skipped, with 64.42% coverage (the Juice Shop
  container e2e test is excluded, same as CI's own gate);
- Python `pip-audit` (against a freshly regenerated `requirements.lock`
  adding the `regex` dependency) and npm audit both reported 0
  vulnerabilities;
- wheel and source distribution built, and Twine validated both artifacts;
  additionally, the built wheel was installed into a clean venv and the two
  named advisories plus the four same-class findings (below) were each
  re-exercised directly against the *installed* package (not the source
  tree) to confirm the shipped artifact — not just the source — carries the
  fix;
- Flyto2 Indexer strict full scan passed 19/19 checks with 0 warnings/failures,
  docs score 100, README score 100, 0 secret findings, and 0 high-risk taint
  flows;
- package, MCP registry, and changelog version metadata all resolve to
  `2.26.12`. `actionlint` was not re-run — no workflow file changed in this
  release.

**Remote CI note**: the `v2.26.12` tag and its release commit (`989f3db`)
initially failed remote CI twice — a `requirements.lock` transitive-pin
drift (`soupsieve` resolved to a newer patch between local lock and CI's
own re-lock) and a stale doc regeneration (one file's line numbers hadn't
been refreshed after a later same-day edit) — plus a separately-failing
`npm audit` gate on 5 pre-existing Dependabot alerts for `undici` (a JS
devDependency used only by the `test_hints.py` harness, never shipped in
the wheel). None of the three affected the published package's actual
content, confirmed by re-downloading the live PyPI wheel and diffing its
`screenshot.py` against source. Three follow-up commits on `main`
(`5067f54`, `b32d36c`, `a0587eb`) fixed all three; remote CI is green as of
`a0587eb`. No new PyPI version was needed since nothing shippable changed.

### 2.26.12 fix set

Closes the two publicly-reported advisories plus four same-class findings
surfaced while scoping the first (CWE-22, unvalidated caller path to a write
sink — the exact pattern the advisory calls out as recurring wave-over-wave):

- `browser.download` (GHSA-p64w-hgfm-824v, critical) and, found in the same
  sweep, `browser.screenshot`, `browser.pdf`, `warroom.report`,
  `verify.report` (+ unescaped HTML), `verify.visual_diff`, `verify.run`,
  `browser.launch`'s `record_video_dir`, and `data.dedup`'s `hash_file` — all
  now confined to `FLYTO_SANDBOX_DIR`.
- `browser.goto`'s www-toggle retry (GHSA-662f-hr85-mg6c, high) — the
  toggled host is now revalidated against the SSRF guard before navigating,
  plus a driver-level `_guard_navigation()` defense-in-depth layer.
- Also included: Tar Slip in `archive.tar_extract` (GHSA-pxvx-67rw-8352,
  high), the `port.check` IPv6-transition SSRF fail-open
  (GHSA-v7q9-pr72-5fmv, medium), and regex ReDoS in `regex.*`
  (GHSA-v468-p4jx-7vj3, medium).
