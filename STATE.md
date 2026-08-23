# Flyto2 Core State

## Current State

- Outbound HTTP enforces one policy regardless of which client is installed.
  `guarded_httpx_client` is the httpx twin of `guarded_client_session`; all
  twelve httpx call sites use it, `httpx` is a declared `ai` dependency instead
  of an inherited one, and a test refuses any `httpx.AsyncClient(` outside
  `core/utils.py`. Forty bare `aiohttp.ClientSession(` constructions remain,
  mostly to fixed vendor endpoints, and are recorded rather than claimed safe.
- `FLYTO_ALLOW_REMOTE_OLLAMA=true` widens `ai.local_ollama.chat` to hosts the
  shared guard accepts instead of disabling validation. Ollama's port, and only
  it, joins the operator port policy so the feature survives the fix; the
  module's outbound-guard exemption is deleted.
- `data.json_to_csv` writes its default `output.csv` inside the configured
  sandbox instead of naming a sandbox-external `/tmp` path. Missing, malformed,
  empty, and structurally invalid inputs now return typed parameter errors and
  skip resilience retries because repeating deterministic input defects cannot
  make them succeed.

- `http.response_assert` exposes `body_matches` as an optional regex parameter.
  Registry metadata no longer turns an editor preset into a required input, so
  status-only and header-only assertions remain valid.

- A legacy single-mode module result with `ok: false` is now a step failure,
  not successful data. It enters the same retry, trace, error-edge, and
  `on_error` contract as an exception; `on_error: continue` remains the explicit
  opt-in for preserving the failure result and continuing.

- Every registered module now exposes `ui_label_key`. Declarations keep their
  explicit `ui_label_key` or `label_key`; only missing keys derive the stable
  `modules.<module_id>.label` convention. This makes module-label localization
  deterministic for catalogs and canvases while preserving the English label
  as a fallback.

- Chromium browser launch now tries the bundled Playwright engine first, then
  supported system Chrome and Edge channels when the caller did not request a
  specific channel. An explicit channel is never replaced. This closes desktop
  template failures on machines where Chrome is installed but the Playwright
  browser cache is absent.

- Core now includes an extensible verified deterministic domain-solver baseline:
  `math.rigid_transform_3d`, `physics.kinematics_constant_acceleration`, and
  `chemistry.ideal_dilution`. Each is dependency-free, offline, bounded to its
  declared model and units, and returns the six-field
  `flyto.execution-verification-receipt.v1` envelope. Its `evidence_sha256` is
  SHA-256 over canonical nested evidence only; separate envelope validation is
  required. This tamper evidence is not a signature, sensor attestation, or
  physical-world proof. The solvers are not complete mathematics, physics, or
  chemistry and have no sensor, hardware, substance identity, reaction,
  laboratory, medical, compatibility, handling, or safety authority.
  Their explicit semantic contracts are registration-validated and projected
  through catalog/search and the hashed capability manifest without inferring
  meaning from display metadata. Legacy providers may continue to omit semantics.
- Local CLI workflow selection now canonicalizes both interactive and
  non-interactive paths and requires an existing regular YAML file before read
  and rechecks the same boundary directly at both execution sinks. A path that
  changes or disappears after its initial read exits through the existing
  invalid-workflow CLI behavior before the runner is called. Absolute paths and
  traversal that resolves to a valid workflow remain supported; no
  repository-root sandbox was added. This is defense-in-depth, with no claim of
  remote exploitability. Rollback is exactly the CLI boundary helper/call
  sites, its focused regression test, and these CHANGELOG/STATE/DECISIONS
  entries. APIs, dependencies, version, module catalog, workflow
  semantics/content, and security policy did not change.
- The repository now declares `flyto.product-contract.v1`: Flyto2 promises to
  turn AI work into verified, replayable procedures, with Core as the standalone
  layer-three package for schema validation, deterministic execution/replay,
  and evidence. AI owns intent/provider governance; Blueprint owns procedure
  learning/scoring and never executes; hosted product/account logic stays out
  of Core.
- Release-wheel discovery excludes `core/tests`, `node_modules`, bytecode, and
  cache trees while explicitly retaining the reverse/deobfuscate and visual
  worker manifests, locks, configuration, and source. Rollback is the
  `pyproject.toml` discovery/data-rule change plus its regression and contract
  files; no runtime API, module, version, dependency, or workflow changed.
- Core extension management is generic and closed to two kinds:
  `flyto-modules-*` into `flyto.modules` and `flyto-plugin-*` into
  `flyto.plugins`, declared once in `EXTENSION_KINDS` and read by every other
  decision. No Core source names an individual extension, so a pack such as
  `flyto-modules-robotics` is managed by the generic path with no Core change.
  Served at `/v1/extensions` (bearer token on all four routes; the two mutating
  routes additionally require `FLYTO_EXTENSIONS_INSTALL_ENABLED=1`). An install
  is reported successful only after entry-point proof; a failed **new** install
  is rolled back, a failed **upgrade** is not; upgrades and uninstalls report
  `restart_required`. Failures carry a stable code and never package-manager
  output. Pinned by `tests/core/api/test_extensions.py` and gated by the
  `lint_extensions` and `extension_management` checks in `.flyto/coding.yaml`.
  **Verified 2026-08-12 — see Last Verification.**
- Both security boundaries are now closed registry-wide and enforced in CI,
  rather than patched per advisory:
  - Filesystem — 95 modules declare a path-shaped parameter; 76 reach
    `validate_path_with_env_config`, 19 are documented as not filesystem paths,
    0 unaccounted. Enforced by `tests/core/test_write_sink_coverage.py`.
  - Outbound network — 72 modules declare a URL/host-shaped parameter; 56 reach
    an SSRF guard, 16 are documented as never reaching the network or as
    validating locally, 0 unaccounted. Enforced by
    `tests/core/test_outbound_guard_coverage.py` (MRO-aware, so inherited
    guards count).
  Exemptions require a written reason and are re-verified each run. The audits
  confined roughly 30 modules that no advisory had named — see CHANGELOG
  `[Unreleased]` and the two 2026-08-08 entries in DECISIONS.md.
- The **2.28.1** security release closes four additional reported boundary
  gaps: sandbox-external image reads, nested test-step permission bypass,
  caller-disabled browser SSRF checks, and unguarded email attachment/SMTP/IMAP
  targets. Security coverage now includes non-stable registry entries.
- Four older private advisories were re-verified and prepared for public
  disclosure on 2026-08-14. Their fixes are already present in the published
  `2.27.0` tag and PyPI artifact, so they do not expand the affected range or
  require another runtime release: raw-host/service SSRF, verify/browser SSRF,
  XML/spec file reads, and visual-comparison file reads/writes.
- Two breaking changes come with that: paths outside `FLYTO_SANDBOX_DIR`
  (default: the process working directory) are refused, and connections to
  private/link-local hosts need `FLYTO_ALLOWED_HOSTS` or
  `FLYTO_ALLOW_PRIVATE_NETWORK=true`. Loopback is unaffected.
- The version on `main` is **2.31.0**, unreleased. It moved because the packaged
  source moved: `2.28.1` was already on PyPI when the Python-floor change landed,
  and a floor change is packaging-visible. `scripts/check_release_drift.py` now
  fails CI whenever a tag `v<version>` exists and the packaged source at HEAD
  differs from it, so a version can no longer keep naming a release that shipped
  other code. The advisory floor is a separate number and stays **2.28.1**:
  `>= 2.28.1` clears every published advisory, `2.31.x` is the line that
  receives new fixes, and `security/advisories.json` is where both are derived
  from rather than restated.
- Package metadata was prepared for the **2.28.1** release. It includes the
  plugin capability contribution point and per-plugin policy scope already on
  `main`, plus the GHSA-gc4h-hj7x-gp5p SSRF fix. The shared IP classifier now
  rejects every IPv4 and IPv6 unspecified-address representation before URL,
  connect-time DNS, raw-host, and port-check callers can use it.
  `SECURITY_STATUS.md` publishes all 33 advisories with the regression test
  covering each, generated from `security/advisories.json` and verified in CI.
- The preceding 2.26.12 security patch release closed the remaining browser
  file-write and SSRF gaps the 2.26.11
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
- The generated catalog currently exposes 479 modules across 88 categories, and
  the bundled recipe inventory contains 41 recipes.
- Catalog search and detail results carry each module's registry-declared
  `provides_capability` and `plugin`; neither is derived from the module ID.
- Plugin discovery is a transaction keyed on what each `register_all()` actually
  registered, held for exactly the span of that call. A forced pass removes
  modules a plugin stopped providing, a failed load restores rows it overwrote
  to their real owner instead of deleting them, and the contribution record is
  replayed only into a registry that began the pass empty. **Verified and
  accepted 2026-08-11** — see Last Verification.
- A registry read is answered from a registry that stood whole at one instant,
  and the answer is a copy rather than a handle. Every public read holds
  `_discovery_lock` for its whole body; `discover_plugins()` and `refresh()`
  return a copied plugin mapping on every path; `PluginInfo` is frozen, closing
  the last route by which a caller could edit registry state through a value it
  was handed. `REGISTRY_VERSION` is 1.4.0. **Verified and accepted 2026-08-11**
  — see Last Verification.
- `flyto.core.capability-manifest.v1` describes what an installation can do,
  derived from the registry and free of timestamps, paths, and host identity, so
  two hosts with the same installed distributions produce byte-identical
  documents. It is served read-only over `GET /v1/capabilities` and the MCP
  `get_capability_manifest` tool; `POST /v1/capabilities/refresh` re-runs
  discovery and requires bearer authentication.
- The manifest cache is ordered by a monotonic registry generation, not by which
  build stored last. `ModuleRegistry.capability_snapshot()` reports
  `generation` under the same lock hold that produced the data, and a build only
  publishes when its generation is at least the cached one. A build that read
  the registry before a refresh and finished after it is therefore rejected
  instead of silently republishing the pre-refresh surface. **Verified
  2026-08-12** — see Last Verification.
- The registry transaction covers the in-process path only. The out-of-process
  `PluginService` / runtime plugin lifecycle (`src/core/api/plugins/service.py`,
  `src/core/plugin/`) is a separate surface: it is outside the transaction and
  outside the coverage kernel, and remains open work. It is not the only open
  plugin surface — the inert `flyto.plugin.v1` manifest/adoption slice is now
  implemented, while `RuntimeInvoker.set_plugin_manager` still has no caller, so
  a workflow step cannot reach a plugin subprocess. Adoption starts, installs,
  loads, downloads, and executes nothing and claims no OS sandbox. Its shared
  pre-canonicalization text boundary rejects C1 controls, bidi/zero-width
  formats, surrogates, private-use, unassigned/noncharacters, and line/paragraph
  separators across values, keys, endpoints, and allowlists without reflecting
  hostile text in errors. Its
  `same_network` endpoint boundary requires a small explicit unique bounded
  ASCII host-authority allowlist and performs exact no-DNS matching. See
  `docs/specs/PLUGIN_MANIFEST_SPEC.md`. Its existing-ID collision input is also
  closed: only an exact list or tuple of at most 256 unique bounded control-free
  ASCII reverse-DNS IDs reaches membership; arbitrary iterables are never
  consumed.
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
- Cryptography uses the patched 48.x line, and the supported Python floor is
  3.10, so Starlette, pip, setuptools and pytest all sit on their patched lines
  with no split branch. The former 3.9 branches are gone: 3.9 could not resolve
  `aiohttp>=3.14.3` and therefore never had a working install, so the
  compatibility they carried protected nothing while holding two dependencies
  below their fixed releases. A `compat` CI job installs and tests 3.10, 3.12
  and 3.13; 3.11 stays covered by the main job.
- The 60% line coverage gate measures the maintained orchestration and
  security-control kernel. Pluggable module implementations and product
  overlays remain covered by catalog, contract, and integration suites.
- Source-backed documentation now covers 966 maintained Python files, 5,686
  declarations, 486 literal module registrations, all CLI/HTTP/environment
  surfaces (28 static HTTP operations, 108 environment names), and all
  maintained recipe/workflow assets. CI rejects drift, missing ownership,
  broken local links, stale naming, and mailbox violations.
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

### 2026-08-12 — capability, extension and runtime closure: VERIFIED

Codex independently reviewed the full working diff and found one additional
policy-alias defect: `database.scan` can route to
`flyto-official/database`, but the gate queried the manifest under the caller's
legacy `database` spelling. The resolved plugin id now drives manifest and
plugin-grant policy before either primary or fallback execution; legacy-first
routes retain that id. A regression test proves the dangerous permission is
denied and the real resolved id is queried.

All repository-pinned checks pass on the current source: project-memory,
compile, four Ruff surfaces, extension management (**81 passed**), runtime
lifecycle (**45 passed**), generated documentation, registry/plugin
(**78 passed**), and the full non-browser/e2e suite at **2785 passed, 11
skipped, 273 deselected**, 63.20% coverage against the 60% floor. Generated
references report 955 source files and 5,631 declarations; the catalog remains
468 modules across 85 categories. After commit `0a353ff`, strict Indexer passed
**19/19** on the clean tree with no warnings or failures, closing the one
pre-commit hygiene finding caused by dirty `.flyto/coding.yaml`.

### 2026-08-11 — generic extension documentation closure: PARTIALLY VERIFIED

Scope: documentation only. No source, test, or config file was changed. This
pass exists to close the one thing the "generic extension management" entry
below recorded as outstanding *and* mechanically fixable — `docs/reference/`
was known stale because the generator had never been run against the extension
surface.

What was executed here, and what it returned:

| Check | Result |
| --- | --- |
| `generate_reference` (declared project action) | exit 0 — 5,631 declarations, 955 source files |
| `generate_catalog` (declared project action) | exit 0 — 468 modules across 85 categories |

`generate_reference` **did** write this working tree: `docs/reference/` now
reports 955 files / 199,204 lines / 5,631 declarations across 808 files, and
`docs/reference/http-api.md` carries all four `/v1/extensions` routes while
`docs/reference/configuration.md` carries `FLYTO_EXTENSIONS_INSTALL_ENABLED`.
`generate_catalog` reported writing `/workspace/docs/TOOL_CATALOG.md` — the
sandbox copy, not this tree — so it is evidence the catalog figures are
unchanged at 468/85, not evidence that this tree's `TOOL_CATALOG.md` was
rewritten. It did not need to be: `src/core/catalog_facts.py` still declares
468/85/41.

Documentation drift found and fixed (the extension surface moved these):

| File | Token | Was | Now (generated) |
| --- | --- | ---: | ---: |
| `ARCHITECTURE.md` | Python files / declarations / HTTP operations | 954 / 5,599 / 24 | 955 / 5,631 / 28 |
| `STATE.md` | Python files / declarations | 954 / 5,599 | 955 / 5,631 |
| `docs/README.md` | Python files / declarations | 954 / 5,599 | 955 / 5,631 |
| `docs/README.md` | environment readers | 93 | 107 |
| `docs/MIGRATION_STATUS.md` | files / lines / declarations / HTTP operations | 954 / 198,471 / 5,599 across 807 / 24 | 955 / 199,204 / 5,631 across 808 / 28 |
| `docs/WHITEPAPER.md` | files / lines / declarations | 954 / 198,471 / 5,599 | 955 / 199,204 / 5,631 |
| `docs/FEATURES.md` | declarations | 5,599 | 5,631 |

`docs/README.md`'s environment-reader count is a *new* find: the 2026-08-11
lifecycle-closure entry corrected that token in `README.md`,
`docs/CONFIGURATION.md` and `docs/MIGRATION_STATUS.md` but missed this file,
which still read 93. It is not covered by `check_current_inventory()`, same
root cause as the six tokens that entry recorded.

Reviewed and found already correct — deliberately not edited: `README.md`,
`docs/API.md`, `docs/CONFIGURATION.md`, `CHANGELOG.md`, and `DECISIONS.md`
already document the generic extension surface. `docs/API.md`'s error table was
checked row by row against `ExtensionErrorCode` and `_STATUS_BY_CODE` and its
ten codes and statuses match, including the transport-level
`extension_management_disabled` → 403 that lives in the router rather than the
loader; its kinds table matches `EXTENSION_KINDS`. The closure rule "no change
is acceptable if already correct" was honored.

**Every command-line gate was again unavailable in this session.**
`.venv/bin/python`, `python3`, `scripts/check_documentation.py`,
`scripts/lint-project-memory.sh`, `scripts/check_brand_identity.py`, `pytest`,
`ruff`, `compileall`, the package build, `npm audit`, and `git` all required an
approval this session could not obtain; the two declared project actions above
were the only execution route. The `flyto-index` CLI and the `flyto-indexer`
MCP verify tools were likewise unavailable, so **strict full-scan Indexer
verification was NOT run**.

The 27 inventory tokens that `check_current_inventory()` pins across the seven
prose files were matched by hand, byte-for-byte, against its exact expected
strings and the regenerated headers. That is a reading, not a run: the
documentation gate itself has **not** been executed against this tree, and it
is the only check that settles whether `docs/reference/` is current. Re-run
`scripts/check_documentation.py` before treating this as closed.

Unchanged by this pass: the extension suite
(`tests/core/api/test_extensions.py`) has still never been executed, so the
generic extension management change remains functionally unverified — see the
entry immediately below. This pass closed its documentation debt only.

No commit, push, or deployment was made.

### 2026-08-11 — generic extension management: NOT VERIFIED (gates skipped)

Scope: `src/core/plugin/loader.py`, `src/core/api/routes/extensions.py`,
`src/core/api/routes/__init__.py`, `src/core/api/server.py`,
`tests/core/api/test_extensions.py`, `.flyto/coding.yaml`, and the prose
surfaces (README, docs/API.md, CHANGELOG, DECISIONS, this file).

**Every executable gate was skipped: command execution was unavailable in the
session that made these edits.** Nothing below has been observed to pass. Treat
the change as unverified until the gates are run.

Skipped, and required before this is releasable:

- `.venv/bin/python -m pytest -p no:cacheprovider --no-cov -q tests/core/api/test_extensions.py`
  (`extension_management`) — the new suite has never been executed.
- `.venv/bin/python -m ruff check` over the five files in `lint_extensions`.
- `.venv/bin/python -m compileall -q src` — no syntax check was run.
- `.venv/bin/python scripts/generate_reference.py` then
  `.venv/bin/python scripts/check_documentation.py`. This change adds four HTTP
  routes and one environment reader (`FLYTO_EXTENSIONS_INSTALL_ENABLED`), so
  `docs/reference/http-api.md`, `docs/reference/configuration.md` and
  `docs/reference/python-api.md` were **known stale** and the documentation gate
  was expected to fail until the generator was re-run.
  **The generator half is now done** — see the documentation-closure entry above,
  which regenerated `docs/reference/` and corrected the prose counts that moved
  with it. `scripts/check_documentation.py` itself is still unrun.
- `bash scripts/lint-project-memory.sh`, `python scripts/check_brand_identity.py`,
  and the offline suite `-m 'not browser and not e2e'` — the last matters because
  `GET /v1/info` now advertises an `extension_management` capability.

Design intent that the suite is written to pin, for whoever runs it: prefix and
entry-point-group admission with no per-extension branch; argv-only pip with a
scrubbed environment; stable error codes with no subprocess output in any
response; entry-point proof; rollback of a failed new install but not of a failed
upgrade; `restart_required` on upgrade; auth on all four routes plus the operator
opt-in on the mutating two. The suite performs no network I/O — pip is
intercepted at `subprocess.run` and entry-point reads are served from a fake
group.

### 2026-08-11 — lifecycle closure re-verification: PARTIALLY VERIFIED

Scope: a read-only closure pass over the lifecycle edits already in
`src/core/runtime/invoke.py`, `src/core/runtime/manager.py`, and
`src/core/runtime/exceptions.py`, plus the prose inventory surfaces. No source
file was changed: the three runtime modules and their suites were re-read
against the three closure claims and found already correct, so the closure rule
"no source change is acceptable if already correct" was honored.

What was re-read and confirmed, by reading rather than by running:

- Malformed manifest shapes fail closed. `_require_sequence` rejects
  string/bytes/mapping before iteration, `_manifest_step_policy` rejects a
  non-step entry and a non-string permission, and every raising path in
  `_policy_denial` (lookup, field read, malformed shape) returns a denial that
  names the plugin and never interpolates the cause.
  `tests/core/test_runtime_policy_gate.py` pins all of these, including the
  no-leak assertions.
- invoke/start/idle-stop/unload/shutdown are race-safe. `_registry_lock` guards
  the registry, `info.lock` serializes lifecycle transitions, `claim`/`release`
  order the timestamp before the count, `_drain` is bounded, and both re-read
  the registry under the lock. `tests/runtime/test_manager.py` pins each
  interleave with events rather than sleeps.
- Docs report 5,599, confirmed by an executed generator, not by reading.

What was executed here, and what it returned:

| Check | Result |
| --- | --- |
| `generate_reference` (declared project action) | exit 0 — 5,599 declarations, 954 source files |

Real gaps found and fixed (documentation only, no source):

Six prose inventory tokens had drifted from the generated reference and are not
covered by `check_current_inventory()`, which is why they went stale unnoticed —
that gate pins module/recipe/declaration/registration counts but not line,
route, or environment totals.

| File | Token | Was | Now (generated) |
| --- | --- | ---: | ---: |
| `docs/WHITEPAPER.md` | maintained Python lines | 197,902 | 198,471 |
| `docs/MIGRATION_STATUS.md` | maintained Python lines | 197,902 | 198,471 |
| `docs/MIGRATION_STATUS.md` | static HTTP operations | 22 | 24 |
| `docs/MIGRATION_STATUS.md` | environment-variable names | 93 | 107 |
| `docs/CONFIGURATION.md` | environment-variable names | 93 | 107 |
| `README.md` | environment readers | 93 | 107 |

The HTTP-operation and environment-name corrections are the same ones the
2026-08-11 stale-refresh entry recorded as applied to `ARCHITECTURE.md`; that
pass missed `docs/MIGRATION_STATUS.md`, `docs/CONFIGURATION.md`, and
`README.md`. All six now match `docs/reference/` as regenerated in this session.

**Strict Indexer post: NOT RUN — blocked on authorization.** The exact target
(`flyto-index verify . --full-scan --strict` over the lifecycle and docs
surfaces) could not be executed. `mcp__flyto-indexer__verify` and
`mcp__flyto-indexer__verify_workspace` are not authorized in this session, and
the `flyto-index` CLI and every other command-line route
(`pytest`, `ruff`, `scripts/check_documentation.py`,
`scripts/check_brand_identity.py`, `scripts/lint-project-memory.sh`, build,
`npm audit`) require an approval this session could not obtain. The declared
project action above was the only execution route available. This entry
therefore remains PARTIALLY VERIFIED: treat the strict Indexer receipt and every
command-line gate as outstanding, and re-run them before this is released.

### 2026-08-11 — plugin runtime lifecycle hardening: PARTIALLY VERIFIED

Scope: the fail-closed manifest-shape check in `src/core/runtime/invoke.py`, the
`PluginManager` lifecycle work in `src/core/runtime/manager.py`, the new
`PluginManagerShutdownError`, the extended suites
(`tests/runtime/test_manager.py`, `tests/core/test_runtime_policy_gate.py`), the
two new required checks in `.flyto/coding.yaml`, and the regenerated
`docs/reference/` plus the six prose inventory surfaces.

What was executed here, and what it returned:

| Check | Result |
| --- | --- |
| `generate_reference` (declared project action) | exit 0 — 5,599 declarations, 954 source files |
| `generate_catalog` (declared project action) | exit 0 — 468 modules across 85 categories |

What was NOT executed, and must be run before this is treated as released:

- `compile`, `lint`, `lint_runtime_invoke`, `lint_runtime_manager`,
  `generated_reference` (`scripts/check_documentation.py`),
  `registry_plugin_contract`, `runtime_manager_lifecycle`, and `tests` — every
  command-line gate. The session running this work could not execute
  `.venv/bin/python`; only the two declared project actions above were
  available.
- `scripts/check_brand_identity.py` and `scripts/lint-project-memory.sh`, for
  the same reason.
- Strict full-scan Flyto2 Indexer verification: the `flyto-indexer` MCP tools
  were not authorized in that session.

The six inventory tokens were matched by hand against
`check_current_inventory()`'s exact expected strings and the regenerated
`docs/reference/python-api.md` header (`**5,599 declarations across 807
files**`). That is a reading, not an execution: the documentation gate itself
has not been run against this tree.

### 2026-08-11 — capability-manifest stale-refresh closure: PARTIALLY VERIFIED

Scope: the capability-manifest cache ordering fix, its regression test, the
regenerated `docs/reference/`, the widened `.flyto/coding.yaml` lint surface,
and the prose inventory tokens. Registry/plugin work and unrelated edits were
left as they stood.

What was executed here, and what it returned:

| Check | Result |
| --- | --- |
| `generate_reference` (declared project action) | exit 0 — 5,584 declarations, 954 source files |
| `generate_catalog` (declared project action) | exit 0 — 468 modules across 85 categories |

Those two are the only commands this session could run. The declared project
actions were the sole execution route available: `pytest`, `ruff`,
`compileall`, `scripts/check_documentation.py` and the Indexer MCP tools were
all denied here, as they were for the sessions that built this change.

**Not run in this session, and therefore not claimed green:** `project_memory`,
`compile`, `lint`, `generated_reference`, `registry_plugin_contract`, and
`tests` — the six pinned checks in `.flyto/coding.yaml` — plus strict Indexer
verification, the package build, and `npm audit`.

The declaration total moved 5,572 → 5,584 across 953 → 954 maintained Python
files (807 of them now carrying declarations, up from 806), which is the
capability-manifest module and the methods added with it. The six prose
inventory files — `ARCHITECTURE.md`, `STATE.md`, `docs/README.md`,
`docs/MIGRATION_STATUS.md`, `docs/WHITEPAPER.md`, `docs/FEATURES.md` — were
updated to those figures, which is what the preceding audit round found stale.
`ARCHITECTURE.md`'s HTTP-operation and environment-name counts were corrected
to the generated 24 and 107 in the same pass.

The regression test for the stale-store race is deterministic by construction —
the interleave is forced with events rather than sleeps — but it has not been
executed here, so it is a written test, not a passing one. Treat every
correctness claim in this entry as read from source, not as a green run.

No commit, push, deployment, or hardware claim is made.

### 2026-08-11 — registry 1.4.0 plugin-load transaction: VERIFIED / ACCEPTED

The registry plugin-load transaction and the return-value closure that followed
it are verified and accepted. This supersedes the "NOT verified" status the
three 2026-08-11 entries below were written under; those entries remain as the
record of how the change was built, not of its current status.

Accepted on branch `main`.

Receipts. The revisions are flyto coding implementation revisions (SHA-256), not
Git commit hashes:

| Covers | Acceptance job ID | Accepted implementation revision (SHA-256) |
| --- | --- | --- |
| Documentation | `job_453f3754aa2041309060b75a` | `ebeb0ebfcab2d56bec576a944dcadd23fa197ff9726c558379df1c76eb12e341` |
| Source and tests | `job_ad0baf4f580e4bc6aaac37de` | `b391189517db77146c4ab51def48ed7ada04fb30308296480e2e083df46bf65c` |
| Generated catalog and tests | `job_8d8d49019afa402a8c503aa0` | `a08df544401cf36a54dfe4f6fc084512cb3035a9febf885442baca5cd8366f15` |

Passed against those receipts: the six pinned checks in `.flyto/coding.yaml`
(`project_memory`, `compile`, `lint`, `generated_reference`,
`registry_plugin_contract`, `tests`), the Core module-contract proof
(`flyto.core.module-contract.v1`), strict Indexer verification, and an
independent replay of 78 registry tests and 25 catalog tests.

`REGISTRY_VERSION` is 1.4.0.

**Provenance of this record.** The acceptance above was produced by the audited
acceptance run against those receipts; it was reported into this session rather
than re-executed here. This session could execute only the two declared project
actions, as prior sessions on this work could: `generate_reference` (exit 0 —
5,572 declarations across 953 files) and `generate_catalog` (exit 0 — 468
modules across 85 categories), both matching the figures already recorded.

**That agreement is weaker evidence than this entry originally claimed, and the
claim is withdrawn.** The declared actions run in the isolated project-action
sandbox, not against this checkout: the 2026-08-11 closure session observed
`generate_catalog` reporting `Generated /workspace/docs/TOOL_CATALOG.md`, and
`git status` was byte-for-byte unchanged after both actions ran. Stable figures
therefore show the generators are deterministic and that the sandbox copy has
the recorded shape; they do **not** establish that `docs/reference/` and
`docs/TOOL_CATALOG.md` *in this working tree* are current. Only the pinned
`generated_reference` check (`scripts/check_documentation.py`) settles that, and
it is unrun here. The six pinned checks, the Core proof and
the Indexer strict run were **not** re-run in this session — `pytest`,
`compileall`, `ruff` and the Indexer MCP tools were all denied here. No commit,
deployment, or hardware claim is made.

Still open, tracked separately: the out-of-process `PluginService` / runtime
plugin lifecycle. That is this change's remaining scope, not a claim that it is
the last open plugin surface — the then-DRAFT `flyto.plugin.v1` manifest and the
uncalled `RuntimeInvoker.set_plugin_manager` were documented open in
`docs/specs/PLUGIN_MANIFEST_SPEC.md` and were neither touched nor assessed here.
The manifest/adoption part of that historical statement is superseded by the
current-state entry above; runtime wiring remains open.

### 2026-08-11 — registry 1.3.0 return-value closure: superseded by the acceptance above

*Status at the time of writing: not verified. Build record only — the change is
now verified and accepted as registry 1.4.0. Do not read the status lines below
as current.*

Closes the two gaps the 1.3.0 audit left in this tree. Like every session on
this work, it could execute only the two declared project actions; no check in
`.flyto/coding.yaml` was available, so the change is unverified.

- `discover_plugins()` returns `_plugins.copy()` on all three paths — the
  reentrant answer to plugin code, the already-initialised fast path, and the
  completed pass — so `refresh()`, which returns `discover_plugins(force=True)`,
  is copied too. `PluginInfo` is frozen, which closes the route the shallow copy
  leaves open: the values in the copy are the registry's own objects, so an edit
  to one was an unlocked write to what the registry says a plugin contains.
- The TOCTOU regression
  (`test_a_forced_pass_waits_for_a_reader_that_is_past_the_fast_path`) now sets
  a `forcer_entered` event immediately before `discover_plugins(force=True)` and
  waits on it before asserting the forced pass is blocked. Without it the
  negative assertion could pass because the forcing thread had not started yet
  rather than because the lock held it.
- Six new tests in `tests/core/test_plugin_policy_scope.py`: no discovery path
  returns the live dict; a caller cannot edit the registry through the mapping;
  a plugin cannot empty the record by clearing what it was handed mid-pass; a
  caller cannot edit it through a `PluginInfo` value; a new pass replaces a
  `PluginInfo` rather than editing one; a retained mapping does not change under
  its caller.
- Ran and passed: `generate_reference` (5,572 declarations across 953 files),
  run after the final source edit, so `docs/reference/python-api.md` and
  `docs/reference/source-modules.md` match the tree as it stands. It imports and
  exercises the modified registry end to end, so the frozen `PluginInfo` and the
  copied returns are import-clean and first-party registration is undisturbed.
  That is the only execution evidence. The declaration total was already 5,572
  in this tree while the six pinned prose tokens still read 5,570; all six —
  `ARCHITECTURE.md`, `STATE.md`, `docs/README.md`, `docs/MIGRATION_STATUS.md`,
  `docs/WHITEPAPER.md`, `docs/FEATURES.md` — now match the generated reference.
- Not run, status unknown: `project_memory`, `compile`, `lint`,
  `generated_reference`, `registry_plugin_contract`, `tests`. Also not run:
  brand identity, npm audit, package build/Twine, and Indexer verification.

### 2026-08-11 — catalog plugin exclusion + serialised discovery: superseded by the acceptance above

*Status at the time of writing: not verified. Build record only — the change is
now verified and accepted as registry 1.4.0. Do not read the status lines below
as current.*

Two defects were closed on top of the plugin-load transaction work below. Like
it, they could not be run: this session also had only the two declared project
actions, and every check in `.flyto/coding.yaml` was unavailable.

- **The host/container catalog disagreement.** `generate_catalog --check` passed
  at 468 modules inside the clean release container and failed on a developer
  host. The catalog is rendered from the live `ModuleRegistry`, which is
  deliberately open to any distribution declaring a `flyto.modules` entry point,
  so a host with a module pack installed generated a catalog carrying that
  pack's modules. `scripts/generate_catalog.py` now skips rows whose registry
  owner is a plugin (`_is_plugin_owned`), so the file is a property of this
  source tree and not of the machine. The generated header says so.
- **First discovery is now serialised.** `_ensure_discovered` answered any
  caller that arrived mid-pass from the half-built registry, so two threads in
  one process could take `RegistrySnapshot`s with different `module_count` and
  `modules_hash` for the same install. A reentrant `_discovery_lock` plus a
  recorded `_discovery_thread` now separate the two callers: the discovering
  thread re-entering through a plugin is still answered from the partial state
  (the only answer that cannot deadlock), and every other thread waits and is
  handed the finished registry. `_ensure_discovered` asks whether a pass is in
  flight *before* whether the registry is initialised: a forced rediscovery
  rebuilds an already-initialised registry and never lowers `_initialized`, so
  the opposite order sent readers past the lock and into the rebuild — which is
  every `refresh()`, not a corner case. `refresh()` also holds the lock across
  `clear()` + rediscover so the empty gap between them is not observable.
  Rollback, ownership and `clear()` semantics are untouched.
- Known residual, deliberately not closed here: a reader releases the lock
  before copying `_modules`, so a forced pass starting inside that window can
  still be observed torn. Closing it means holding the lock across every
  reader's copy, which is a wider change than this fix and is recorded in
  `tasks.md` rather than done silently.
- `REGISTRY_VERSION` moved 1.1.0 → 1.2.0, with the pinned assertion in
  `tests/core/test_plugin_policy_scope.py` moved deliberately alongside it: a
  checkpoint carrying 1.1.0 cannot be assumed to have been matched against a
  complete registry.
- Ran and passed: `generate_catalog` (468 modules / 85 categories — unchanged,
  which is the evidence that the exclusion drops no first-party module) and
  `generate_reference` (5,570 declarations across 953 files). The declaration
  total moved 5,568 → 5,570 for the two added helpers
  (`ModuleRegistry._discover_locked`, `generate_catalog._is_plugin_owned`); all
  six pinned prose inventory tokens were moved with it.
- New tests: nine thread-safety cases in
  `tests/core/test_plugin_policy_scope.py` (reentrancy without deadlock, no
  nested pass, a concurrent read and a concurrent snapshot seeing the whole
  registry, one pass for four concurrent first reads, owner id not leaked, and
  three more that begin from an initialised registry and run a slow *forced*
  pass — the case `_initialized`-first ordering let through), and
  four catalog cases in `tests/core/test_catalog_determinism.py` driven by a
  `sitecustomize` shim that installs a real `flyto.modules` entry point, one of
  which is a guard proving the shim still registers something.
- Not run, status unknown: `project_memory`, `compile`, `lint`,
  `generated_reference`, `registry_plugin_contract`, `tests`. Also not run:
  brand identity, npm audit, package build/Twine, and Indexer verification.

### 2026-08-11 — registry plugin-load transaction: superseded by the acceptance above

*Status at the time of writing: not verified. Build record only — the change is
now verified and accepted as registry 1.4.0. Do not read the status lines below
as current.*

The change to `src/core/modules/registry/core.py` and
`tests/core/test_plugin_policy_scope.py` described under Current State has **not
been run**. Successive sessions on it could execute only the two declared project
actions; every check in `.flyto/coding.yaml` was unavailable to them, including
the pinned `registry_plugin_contract` Core proof. Nothing below is a substitute
for running them, and the change should not be treated as released until they
are.

- Ran and passed: `generate_catalog` (468 modules / 85 categories, unchanged) and
  `generate_reference` (5,568 declarations across 953 files, 806 of them
  declaration-bearing). Both import and exercise the modified registry, so the
  change is import-clean and does not disturb first-party registration or the
  generated catalog.
- The reference was regenerated **after** the final source edit, so
  `docs/reference/python-api.md` and `docs/reference/source-modules.md` match the
  tree as it stands. The declaration total moved 5,567 → 5,568 because the fix
  adds one method (`ModuleRegistry._note_pass_touch`); the six prose inventory
  tokens that `scripts/check_documentation.py` pins to that total —
  `ARCHITECTURE.md`, `STATE.md`, `docs/README.md`, `docs/MIGRATION_STATUS.md`,
  `docs/WHITEPAPER.md`, `docs/FEATURES.md` — were all moved with it.
- `REGISTRY_VERSION` moved 1.0.5 → 1.1.0. It is a contract version carried in
  every `RegistrySnapshot`, and rollback becoming total changed what a caller may
  conclude from a registry that survived a failed load, so a resumed checkpoint
  must be able to tell the two apart.
- `clear()` is now pass-aware, closing an ownership escalation. A plugin whose
  `register_all` called `ModuleRegistry.clear()` had the loading owner reset
  mid-pass, so every module it registered afterwards was stamped with no plugin
  at all — first-party, the one identity the process-global permission grant
  reaches. Inside a pass the owner and the rollback ledger are now kept, and the
  rows the clear drops are banked first, so a pass that wipes the registry and
  then raises is rolled back whole rather than against an empty ledger.
  `_load_plugin` also restores the entire prior `_plugins` map instead of the
  failing entry point's single line, since a wipe takes every plugin's
  `PluginInfo` with it. Outside a pass `clear()` is byte-identical to before.
- Not run, status unknown: `project_memory`, `compile`, `lint`,
  `generated_reference`, `registry_plugin_contract`, `tests`. Also not run:
  brand identity, npm audit, package build/Twine, and Indexer verification.
- The coverage-floor obstacle previously recorded here is resolved: the pinned
  `registry_plugin_contract` argv in `.flyto/coding.yaml` now carries `--no-cov`
  (and `-p no:cacheprovider`), so the check no longer inherits the 60% gate from
  `pyproject.toml` and a non-zero exit is once again a real defect signal rather
  than an artefact of running one file against a whole-suite floor.

Verified locally on 2026-08-08 for the **2.27.0** release candidate — the full
closure in `docs/TESTING.md`, every gate run, none skipped silently:

- documentation contract, brand identity, project-memory lint, generated
  catalog (468 modules / 85 categories), generated reference (5,559
  declarations across 806 files), and the new security-status check
  (24 advisories) all passed;
- audited-surface Ruff (the CI list plus `generate_security_status.py`) passed
  with zero findings;
- 2,467 tests passed, 13 skipped, 273 deselected, with 61.63% coverage against
  the 60% control-kernel gate;
- `requirements.lock` regenerated and unchanged (the only diff was the
  pip-compile generator's Python 3.11 → 3.12 header comment, reverted; no
  dependency moved), `pip-audit` reported no known vulnerabilities, `npm audit`
  reported 0;
- wheel and sdist built and Twine-validated. The wheel was then installed into
  a clean venv and the boundaries were exercised against the **installed**
  package, not the source tree: `/etc/passwd` refused and an in-sandbox path
  accepted; the metadata address, an RFC1918 host, and an IPv4-mapped IPv6
  loopback literal each refused while loopback was accepted; `redis://` to the
  metadata address refused; and end to end, `file.delete` refused `/etc/hosts`
  and `ssh.exec` refused the metadata host. The installed registry reports 468
  modules, matching the committed catalog;
- Flyto2 Indexer strict full scan passed 19/19 checks;
- package and MCP registry metadata both resolve to `2.27.0`.

Not run: browser and E2E suites (require browsers, services, or credentials).
`actionlint` was not re-run — no workflow file changed in this release.

**Environment note**: this machine's venv has `transformers` (via the `vector`
extra), which CI does not install. `huggingface` is an optional module category
(`src/core/modules/atomic/__init__.py:_OPTIONAL_CATEGORIES`), so generating the
catalog here would have advertised 475 modules / 86 categories instead of the
468 / 85 the released package actually exposes. Generated artifacts were
produced with `transformers` hidden so they match CI and the shipped wheel.

### Previous release

Verified locally on 2026-08-07 for the 2.26.12 release candidate:

- documentation, brand, generated catalog/reference (5,558 declarations
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
