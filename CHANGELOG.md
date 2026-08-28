# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.31.1]

### Security

- Closed a module-policy bypass in `verify.spec` (GHSA-wmwj-g59x-c8px). The
  spec runner picks its child modules out of the caller's own ruleset —
  `rules[].source.module` / `rules[].target.module` with free-form params — and
  dispatched them with `instance.execute()`. Both locks live in
  `BaseModule.run()`, so a caller who had been restricted to `verify.spec`
  (`FLYTO_MODULE_ALLOWLIST=verify.spec`, no `FLYTO_GRANTED_PERMISSIONS`) could
  name `shell.exec` in a rule and run host commands as the service account,
  with neither the module filter nor the `shell.execute` grant consulted. The
  dispatcher now calls the policy-gated `run()`, a denied child raises instead
  of being reported as an ordinary failed rule, and `POST /v1/execute` gained
  the nested-module pre-flight the MCP transport already had, so the ruleset is
  refused before `verify.spec` does any work. `_execute_with_resilience` no
  longer retries or repackages a `ModulePolicyError` — a blocked module now
  reads as blocked rather than broken. A registry-wide test fails on any future
  code that resolves a module by a caller-supplied id and calls `execute()`
  directly.

### Changed

- `crypto.totp` says when `min_remaining` makes it wait. A code that would
  expire sooner than the caller allows blocks for most of a rotation period,
  and an unexplained pause in an automated sign-in cannot be told apart from a
  hang. The log line names the remaining validity and the period; neither the
  secret nor the generated code appears in it.

### Fixed

- `browser.click` now captures a tab or window opened by the clicked element,
  adopts it as the current browser page, and refreshes hints from that page.
  Live preview and following browser nodes no longer remain attached to the
  opener, and `browser.tab(index=1)` can see the newly created page immediately.
- `browser.click` button/link mode now resolves visible accessible names instead
  of translating Element Picker text into CSS `:has-text()`. Icon-only links,
  ARIA-named controls, and hidden duplicate text now obey the same contract in
  the picker and executor; configured click timeouts and post-click navigation
  detection are also honoured.
- Workflow validation now treats `template.invoke` as the open input boundary
  it is at runtime. Child-template inputs are forwarded dynamically and no
  longer produce false `UNKNOWN_PARAM` warnings against the invoker's four
  static control fields.
- Nested `template.invoke` steps now reuse the caller's authenticated browser
  without letting child cleanup close it, so the caller's next browser node can
  continue the same session.
- Module-emitted error events now follow normal retry, error-edge, and
  `on_error` behavior instead of being recorded as successful step output.
- Visible browser waits now accept any visible selector match even when an
  earlier duplicate in the DOM is hidden.
- Verified with 3,210 offline tests plus 107 focused browser/template tests;
  package build, Twine checks, and Python/Node dependency audits passed.

## [2.31.0]

### Security

- Closed the SSRF gap between the two HTTP clients. Every `httpx.AsyncClient`
  call site sat behind `try: import httpx / except ImportError:` with a guarded
  aiohttp fallback, so which SSRF posture a deployment ran was decided by whether
  another package had pulled httpx in - an environment with `openai` installed
  took twelve unguarded call sites, one without took the guarded twin, and
  nothing said so. `core.utils.guarded_httpx_client` is the httpx twin of
  `guarded_client_session`: it resolves under the same policy and pins the
  approved address into the request while preserving `Host` and TLS SNI, which
  closes the same resolve-then-connect window `ssrf_guarded_connector` closes for
  aiohttp. All twelve sites now use it, `httpx` is declared in the `ai` extra
  instead of inherited, and `tests/core/test_outbound_transport_guard.py` fails
  on any `httpx.AsyncClient(` constructed outside `core/utils.py`.

- Fixed `ai.local_ollama.chat` under `FLYTO_ALLOW_REMOTE_OLLAMA=true`. The module
  carried an outbound-guard exemption reading "restricts to loopback inline,
  which is stricter than the shared guard" - true only while the flag was unset.
  With the documented flag on, `validate_params` returned with no check at all
  and `execute` opened a bare `aiohttp.ClientSession`, so a caller-supplied
  `ollama_url` reached cloud metadata (169.254.169.254) and any RFC1918 address
  with the response body handed back. The agent path already refused the same
  input. The flag now widens the host under the ordinary shared guard rather than
  removing it, Ollama's own port - and only that port - is added to the operator's
  port policy so a real remote host stays reachable, the request goes through
  `guarded_client_session`, and the exemption is deleted so the module is covered
  by the ordinary rule.

### Added

- Added an extensible verified deterministic domain-solver baseline with three
  bounded modules: a proper 3D rigid point transform, SI-only 1D
  constant-acceleration kinematics, and ideal dilution arithmetic. Results carry
  canonical tamper-evident receipts; catalog and capability surfaces expose
  source-declared semantic contracts without physical-world validation claims.

- Added `crypto.totp`, an RFC 6238 time-based one-time password generator built
  on the standard library alone. A secret may be supplied as the Base32 setup
  key an authenticator displays, in any of the renderings it displays it in
  (lowercase, space-grouped, unpadded), or as the whole `otpauth://totp/` URI
  its enrolment QR code encodes; the URI's `digits`, `period`, and `algorithm`
  are honoured so an entry can be imported without transcribing its settings.
  `min_remaining` waits out the current window when a code would rotate while
  the form carrying it is still in flight, which is the ordinary reason an
  otherwise correct automated sign-in is rejected. Correctness is pinned to the
  published RFC 6238 and RFC 4226 vectors across SHA1, SHA256, and SHA512
  rather than to the implementation's own output. This closes the last gap
  between flyto-core and a site whose second factor lives only in a browser
  login flow; `workflows/totp_login_action.yaml` is the end-to-end template.

### Fixed

- A failed browser launch now reports why. Each channel and mode is tried in
  turn and every exception was caught so the next candidate could run, which
  left `No browser engine available` as the whole of what a caller saw whether
  the download was missing, the profile was locked, or the sandbox refused.
  The attempts and their first-line reasons are appended to the error, so a
  missing `playwright install chromium` no longer looks the same as a stale
  `SingletonLock`.

## [2.30.0]

### Added

- The `integration.*` family is registered. Seven Jira, Salesforce and Slack
  modules were fully implemented, listed in the generated module reference,
  named in the landing-page module catalog and translated into every locale,
  while `execute_module` answered "Module not found" for all of them — nothing
  imported their subpackages, so their `@register_module` decorators never ran.
  `utility.not` was in the same state for a different reason: it lives in
  `not.py`, and `from .not import *` is a SyntaxError because `not` is a
  keyword, so no package `__init__` could ever have reached it. The catalog goes
  from 468 modules across 85 categories to 476 across 86.
- `tests/core/test_module_registration_coverage.py`, so that state cannot recur:
  every `@register_module` in the source must be live in the registry, gated on
  a named optional dependency whose guard is verified to still exist, or
  recorded as deliberately not shipped — and that last entry fails the moment
  the module goes live, so "not shipped" cannot quietly become "shipped".
  `ai.tool_template` is the one recorded entry: it is complete in source but no
  locale defines its label key, so registering it would put a raw translation
  key in the node palette.
- The same test now checks `core/catalog_facts.py` against the generated
  catalog, the registry and the packaged recipes. Those constants are what
  `mcp_handler`, `quickstart` and the API server tell a user the catalog holds,
  they were hand-maintained, and nothing compared them to it — they said 468
  while the registry held 476.

### Fixed

- `data.json_to_csv` now resolves its default `output.csv` inside
  `FLYTO_SANDBOX_DIR` instead of pointing at `/tmp`, and invalid inputs produce
  typed, user-facing parameter errors without three identical retries or raw
  `KeyError` details.
- `integration.slack.*` reported failure as success. Slack answers HTTP 200 with
  the real outcome in the body, and the shared client derived `ok` from the
  status alone, so a rejected token produced `ok: True` with every field null.
  `BaseIntegration` grows a `_response_is_ok` hook for APIs that work this way
  and Slack overrides it; the module's own `upload_file` had always read the
  body flag, and every other call had not.

### Security

- Enabling `integration.*` was gated on the guards added in 2.29.0 for
  GHSA-4346-4gqg-59f9, and those guards were verified through real MCP dispatch
  before the family was wired: an operator credential is refused for any host
  the operator did not configure, the metadata endpoint is refused on the
  caller-credential path where only the SSRF guard stands, and a request to the
  operator's own configured host still goes out.

## [2.29.0]

The version moves because the packaged source did. `2.28.1` was already
published when the changes below landed on `main`, so leaving the number alone
would have meant the wheel named `2.28.1` no longer contained what this
repository described — and the Python floor change is packaging-visible, not
cosmetic. `scripts/check_release_drift.py` now refuses that state in CI.

### Security

- Closes the five reports of 2026-08-18/19. Four distinct sinks —
  GHSA-f9q4-fp8j-r5h7 and GHSA-pp5w-w9c3-qfv2 are two reporters on the same
  parameter. `BaseIntegration._request` (GHSA-4346-4gqg-59f9) is the outbound
  sink for the whole `integration.*` family and had neither an egress guard nor
  any restraint on where an operator credential could travel; the three
  `cloud.*.upload` modules (GHSA-45hf-2fmj-q442) read a caller-supplied
  `file_path` while their download twins confined theirs; `llm.agent`
  (GHSA-f9q4-fp8j-r5h7, GHSA-pp5w-w9c3-qfv2) fetched a caller-supplied
  `base_url` unchecked, unlike `llm.chat` and `ai.model`; and the three `db.*`
  connectors (GHSA-9x26-9vhm-2qhw) connected to whatever host a
  `connection_string` named, unlike `db.mysql.query`. `FLYTO_TRUSTED_INTEGRATION_HOSTS`
  is the new operator allowlist for the credential-target guard.
- Both registry-wide coverage gates missed all five, so both were widened.
  `assert_env_credential_endpoint_allowed` no longer counts as an SSRF guard —
  it answers a different question and no-ops for a caller-supplied key, which is
  what let `llm.agent` read as guarded. `connection_string`, `dsn` and `domain`
  became outbound parameter names, because a DSN is a whole target packed into
  one string. The `integration.*` families are now imported into the sweep;
  nothing else imports them, so a family sharing one unguarded sink was
  invisible. The filesystem sweep reads the registered handler rather than the
  whole file, so a guarded twin can no longer vouch for its sibling — which is
  precisely how `aws_s3_upload` passed on `aws_s3_download`'s guard.
- Tightening that last gate found three more of the same shape that no report
  had named, fixed here: `image.qrcode_generate` opened `logo_path` and embedded
  its pixels in the returned image, `verify.annotate` opened `image_path` and
  drew it into an output that was itself confined, and `load_ruleset` still
  carried the `'..'` denylist that GHSA-p34x-fmph-9fjx had already found
  insufficient, while its `save_ruleset` twin had moved to the shared helper.

### Added

- `scripts/check_release_drift.py`, wired into CI: if a tag `v<version>` exists,
  the packaged source at HEAD must match it. An unreleased version passes, so
  this asks for a correct version number rather than a release. Every package in
  this stack had drifted this way at once; nothing caught it because every check
  ran against the working tree, which was correct the whole time.

### Changed

- Legacy single-mode modules that return `ok: false` now fail the workflow step
  instead of being recorded as successful. The existing retry and `on_error`
  policies remain authoritative; `on_error: continue` still exposes a failure
  result to downstream steps.
- Browser launch now falls back from Playwright's bundled Chromium to installed
  Chrome and Edge channels when no channel was requested. Explicit channel
  selection remains authoritative, and the failure message no longer tells an
  operator to install Chrome after the runtime already tried it.
- Registered modules that omit both label-key spellings now expose the
  deterministic fallback `modules.<module_id>.label`. Explicit translation
  keys remain authoritative, so catalog consumers can use one resolver without
  losing compatibility with intentional aliases.
- `http.response_assert` now treats `body_matches` as optional registry
  metadata. The assertion module keeps its regex editor preset without making
  the parameter required for status-only or header-only assertions.

- `tests/test_version_identity.py` now compares the runtime versions against the
  version declared in `pyproject.toml`, not against the metadata they are read
  from. The original assertion compared `importlib.metadata` to itself and could
  only fail by accident — which it did, once, when the wheel-boundary test
  regenerated `egg-info` mid-session on a working copy whose editable install was
  stale. The condition behind that accident is real: an editable install whose
  metadata has fallen behind `pyproject.toml` makes every version-dependent
  result in the suite describe a package that is not the one being edited.
- Raised the supported Python floor from 3.9 to 3.10, because 3.9 never worked.
  `requires-python` advertised 3.9 while the base dependency `aiohttp>=3.14.3`
  requires 3.10, so pip accepted the package on 3.9 and then failed to find a
  distribution. CI only ever ran 3.11, so no run could catch it. The classifier
  list, the `python_version < '3.10'` branches in the build requirements and the
  `api` extra, the Black target list, the mypy target, the plugin template and
  the plugin manifest's default `python_version` now all say the same thing.
  `pytest` moves to `>= 9.0.3`, the line carrying the GHSA-6w46 fix, which was
  previously unreachable only because of the 3.9 floor.
- Added a `compat` CI job that installs the package and runs the non-browser
  suite on 3.10, 3.12 and 3.13. The heavy 3.11 job (documentation, brand, npm
  audits, build, verify gate) is unchanged and still runs once: repeating it per
  interpreter would not make it more truthful. What needed repeating was the
  interpreter range itself, which had drifted into a claim no run tested.
- Corrected the `register_module` / `register_composite` display fields that were
  commented as deprecated. `label`, `label_key`, `description`,
  `description_key`, `icon` and `color` have roughly 1540, 1530, 1780, 900, 500
  and 500 call sites in this repository against 4 or fewer for their `ui_`
  counterparts, nothing warns on them and nothing removes them. The resolution
  order (`ui_label or label or module_id`) is unchanged; only the comments are,
  so a deprecation marker here means something again.
- Stopped tracking two captured run artifacts under `out/` and added `out/` to
  `.gitignore` beside the existing `output/`.
- Pinned the CI checkout of `flytohub/flyto-indexer` to an exact revision. The
  strict full-scan verify gate is only reproducible if the tool running it is;
  unpinned, an unrelated Indexer commit could flip this repository red or green
  with nothing changed here.
- Made the wheel-boundary packaging test build from a clean `build/lib`.
  setuptools never prunes that tree, so on a working copy where `npm ci` had
  run, the test reported the developer's build history instead of the packaging
  rules — and passed in CI only because CI installs those `node_modules` in a
  later step. Released wheels build on a fresh checkout and were never affected;
  `CONTRIBUTING.md` now documents `rm -rf build dist` before a local build.

- Declared Core's exact Flyto2 product role in a deterministic repo-local
  contract and aligned public/project documentation: Core is the independently
  usable schema-validation, deterministic execution/replay, and evidence layer;
  AI owns intent/provider governance, Blueprint owns procedure learning/scoring
  and never executes, and hosted product/account logic remains outside Core.
- Tightened wheel discovery so release artifacts omit `node_modules`,
  `core/tests`, cache directories, and bytecode while retaining both declared
  Node/TypeScript worker manifests, lockfiles, configuration, and source.

### Security

- Added defense-in-depth validation at the local CLI workflow-selection
  boundary: interactive and non-interactive selections are canonicalized and
  must resolve to an existing regular `.yaml` or `.yml` file before Core reads
  them, then are rechecked immediately before the execution sink. A file that
  changes or disappears between selection and execution is rejected with the
  existing CLI error behavior. Valid workflows remain usable by relative or
  absolute path, including outside the current directory. This does not assert
  remote exploitability and is not a CVE or advisory.
- Published and catalogued four historical advisories whose fixes have shipped
  since `2.27.0`: the registry-wide raw-host/service SSRF boundary, SSRF guards
  for `verify.*` and browser connection/proxy targets, sandbox confinement for
  `data.xml.parse`/`verify.spec`, and sandbox confinement for
  `testing.visual.compare`. This disclosure adds no newly affected version and
  requires no release beyond the already-supported `2.28.1`.
- Added direct regression coverage for both local input branches of
  `testing.visual.compare` and for `verify.spec` ruleset confinement. The public
  security-status generator now describes the enforced registry-wide gates
  without embedding module counts that can become stale as the catalog grows.

## [2.28.1] - 2026-08-14

### Added

- The first customer-grade `flyto.plugin.v1` manifest/adoption slice: strict
  closed, recursively canonical and bounded validation, including typed schema
  keywords and Unicode-safe values and keys, rejecting C1, bidi, zero-width,
  surrogate, private-use, unassigned/noncharacter, and line/paragraph separator
  code points before canonicalization or error projection;
  namespace/capability/module ownership rules,
  exact dangerous-permission and parameter-schema controls, local artifact
  SHA-256 verification through a descriptor-bound nofollow regular-file read
  with a race-safe portable fallback and an unraiseable hard byte cap; derived
  endpoint/token environment names, endpoint locality checks with a small
  unique bounded ASCII host-authority allowlist for `same_network`, and detached
  immutable adoption results. Existing adopted IDs are prevalidated as an exact
  list or tuple of at most 256 unique bounded control-free ASCII reverse-DNS IDs
  before membership, without consuming arbitrary iterables. Adoption is inert
  and provides no process or OS sandboxing. Endpoint and allowlist text use the
  same gate; stable errors never reflect hostile or secret-bearing text.

### Security

- Confined local image reads in `vision.analyze`, `vision.compare`, and
  `ai.vision.analyze` to `FLYTO_SANDBOX_DIR`, closing
  GHSA-jpmx-7xh3-vq6v.
- Routed nested `warroom.run` test steps through the same module policy
  chokepoint as direct execution, so modules requiring dangerous permissions
  cannot be smuggled through scenario steps (GHSA-675h-j4qg-m52x).
- Removed the caller-controlled browser SSRF opt-out. `browser.goto` and new
  `browser.tab` navigations now follow the operator-controlled outbound policy
  even when a client sends `ssrf_protection=false`
  (GHSA-r3jp-qf98-23v8).
- Confined `email.send` attachments and applied the shared outbound-host guard
  to caller-selected SMTP and IMAP targets in `email.send` and `email.read`
  (GHSA-x2qh-79wh-6w7j).
- Extended registry-wide filesystem and outbound coverage checks to include
  beta modules, preset-defined host fields, and list-valued attachment paths;
  the expanded audit also closes previously hidden Redis/database target gaps
  and verifies that reverse/training URL fields do not initiate requests.

## [2.28.0] - 2026-08-13

### Added

- Generic Core extension management. Two kinds are supported and the pair is the
  whole contract: `flyto-modules-*` publishing into `flyto.modules`, and
  `flyto-plugin-*` publishing into `flyto.plugins`. Admission is by prefix and
  entry-point group, driven off one table, so a pack such as
  `flyto-modules-robotics` is managed by the generic path the day it is
  published — no Core source names an extension and none has to change for one.
  A bare name is refused rather than completed, because `robotics` is ambiguous
  between the kinds and guessing would install a package nobody asked for.
- `GET /v1/extensions`, `GET /v1/extensions/kinds`, `POST /v1/extensions/install`
  and `POST /v1/extensions/uninstall`. All four require the bearer token; the two
  mutating routes additionally require `FLYTO_EXTENSIONS_INSTALL_ENABLED=1`.
  Installing a package runs its build hooks as host code, and the token that is
  auto-minted for local clients authorises module execution, not arbitrary code
  installation — so it is not on its own sufficient reason to install anything.
- Entry-point proof. pip will install any project whose name matches the prefix,
  including a typosquat, an empty placeholder, or a package that forgot its
  `[project.entry-points]` block; each of those previously left Core with a
  package it would never load and a caller who was told the install succeeded.
  An install is now reported successful only once the installed distribution is
  read back and shown to declare at least one entry point in its kind's group.
- Rollback of a failed *new* install. A package that installs but fails the proof
  is uninstalled again, because the only thing on disk is something Core cannot
  use and did not have before. A failed *upgrade* is deliberately not rolled
  back: undoing it would uninstall the working version the operator already had,
  turning a bad upgrade into no extension at all.
- `restart_required` in install/uninstall responses. An upgrade replaces code the
  interpreter has already imported and Python does not un-import, so the registry
  refresh updates what Core reports while only a restart changes what it runs.
  A first install sets it false; uninstall always sets it true.

### Changed

- Extension discovery now scans both supported prefixes rather than
  `flyto-plugin-` alone, so module packs appear in the loader's manifests, and a
  successful install/uninstall refreshes both the manifests and — for the kind
  whose entry-point group the module registry reads — the module registry
  itself. Refreshing only the manifests left `/v1/extensions` reporting a module
  pack `/v1/modules` had never heard of. Which kind touches the registry is
  decided by comparing entry-point groups with the registry, not by naming a
  kind.
- Every package-manager invocation goes through one argv-only, scrubbed-env
  path, including the update check that previously inherited the full host
  environment. `--no-input` and `--disable-pip-version-check` are always passed:
  a pip that pauses for a prompt inside a request handler is a hung request.
- Extension failures now carry a stable machine-readable code with a fixed
  message. Package-manager stdout/stderr is logged locally and never returned —
  it carries interpreter paths, index URLs, and sometimes credentials embedded
  in an index URL.
- `PluginLoader.install_plugin` / `uninstall_plugin` keep their names, bare-name
  resolution and bool returns, and now delegate to the generic implementation
  rather than keeping a second, weaker installer beside it.

### Fixed

- Runtime policy now checks the manifest of the plugin identity resolved by
  routing, not the caller's legacy module spelling. A call such as
  `database.scan` can resolve to `flyto-official/database`; looking up
  `database` previously found no manifest and could omit the routed plugin's
  `required_permissions`. Legacy-first routes also retain the plugin id so the
  same check covers a later plugin fallback.
- The out-of-process plugin policy gate no longer treats a manifest it cannot
  parse as a manifest that declared nothing. `steps: "scan"` and
  `permissions: "shell.execute"` are iterable, so the step walk read their
  characters, matched nothing dangerous and allowed the step; a permission that
  was not a string was stringified into something the dangerous-permission set
  could never contain, with the same result. Shape is now checked before
  content: a steps or permissions declaration that is a scalar, a mapping, or
  not a sequence, a step entry that is not a step object, and a permission that
  is not a string each deny the invocation. The caller gets the same generic
  "capability policy could not be checked" denial used for an unreadable
  manifest — it never names the offending value, which is plugin-supplied and
  may not even be renderable — and the operator gets the structural reason from
  the server log, keyed by plugin and step.
- `PluginManager` lifecycle transitions no longer race each other.
  - Idle reclaim measures from `time.monotonic()`, not the event loop clock it
    compared against a `time.time()` deadline, and honours the configured
    `idleTimeoutSeconds`; the setting was read at construction and then ignored
    in favour of a hardcoded five minutes. A non-positive value disables
    reclaim, and a plugin that has never been invoked is never swept.
  - Idle reclaim calls the new `stop_plugin()`, which stops the process and
    keeps the plugin registered so `invoke` restarts it lazily. `_check_idle`
    previously called a `stop_plugin` that did not exist, so every sweep raised
    `AttributeError` and no plugin was ever reclaimed.
  - `invoke` holds a per-plugin lock across the lazy start and re-checks the
    registry under it, so concurrent first invokes start one process rather
    than one each, and a start that was queued behind an unload cannot
    resurrect the plugin. `load_plugin` is serialized for the same reason.
  - `unload_plugin` deregisters immediately, then drains accepted work before
    stopping the process, bounded by the new `drainTimeoutSeconds` (default 30)
    so shutdown never depends on plugin cooperation. `stop_plugin` and the idle
    sweep refuse a plugin with work in flight.
  - `start_health_checks`/`start_idle_checks` are idempotent and return whether
    they started a sweeper; a second call used to overwrite the task handle and
    leave the running task unreferenced and therefore uncancellable. A sweep
    that raises no longer ends the loop, `shutdown` is idempotent and safe
    against concurrent callers, and a sweeper cannot be started after it.
  - `PluginUnhealthyError`'s cooldown is computed against the same clock the
    deadline was set on; it previously reported roughly "seconds since the
    epoch" as the retry-after.

- A capability-manifest refresh can no longer be undone by a slower concurrent
  build. Manifests are built outside the cache lock, so two builds can finish in
  either order; with an unconditional store, a build that read the registry
  before a refresh and stored after it republished the pre-refresh capability
  surface, and nothing corrected it — `POST /v1/capabilities/refresh` appeared to
  succeed while `GET /v1/capabilities` kept serving an installation that no
  longer existed, under a hash that named it. `ModuleRegistry` now carries a
  monotonic generation counter, reported by `capability_snapshot()` under the
  same lock hold that produced the data, and the cache publishes a build only
  when its generation is at least the cached one. The counter is process-local
  and is deliberately absent from the document, so manifests stay byte-identical
  across hosts with the same installed distributions.
- A registry read is now whole at a single instant, and what it hands back is an
  answer rather than a handle on registry state. `REGISTRY_VERSION` moves
  1.2.0 → 1.3.0.
  - Every public read holds `_discovery_lock` for its whole body. 1.2.0
    serialised the *decision* to discover, but the reader released the lock
    before it copied `_modules`/`_metadata`, so a forced pass starting in that
    window rewrote the dicts under a read already in progress — half a registry
    from before the rebuild and half from after, or a `RuntimeError: dictionary
    changed size during iteration` on a bad interleave. A checkpoint carrying
    1.2.0 was matched against a registry that was complete when the check ran;
    one carrying 1.3.0 was matched against a registry that stood whole at a
    single instant.
  - `discover_plugins()` and `refresh()` return a copy of the plugin mapping on
    every path, as `get_plugins()` already did. They returned `_plugins` itself,
    so a caller that kept the result held a live view of process-global state:
    it gained and lost plugins on somebody else's schedule — the same torn read,
    smuggled out past the lock inside the return value — and a write to it
    edited the registry's record of what is installed without calling
    `register()` or holding the lock.
  - `PluginInfo` is now a frozen dataclass. The copy above is shallow and shares
    its values with the registry deliberately, which left one route to the same
    unlocked write: editing what a plugin *says* about itself — `module_count`,
    `version`, `entry_point` — through a value the caller was handed. Registry
    code never mutated one either; a pass that changes a plugin's contents
    replaces the whole entry. No caller in this repository mutates one, so this
    is a breaking change only for external code that did.
- `docs/TOOL_CATALOG.md` no longer varies with the plugins a machine has
  installed. The catalog is rendered from the live `ModuleRegistry`, which any
  distribution declaring a `flyto.modules` entry point may contribute to, so a
  checkout with a module pack installed generated a catalog carrying that pack's
  modules: `generate_catalog --check` passed inside the clean release container
  and failed on a developer host over a difference nobody had made. The
  generator now excludes rows the registry attributes to a plugin, and the
  generated header states that its counts are flyto-core only. Module and
  category totals are unchanged (468 / 85), which is the evidence that no
  first-party module was dropped with them.
- The first plugin discovery is serialised, so a concurrent reader can no longer
  observe a half-built registry. `capabilities()`, `list_all()`,
  `get_catalog()` and `get_snapshot()` all trigger discovery on first use, and a
  call arriving from another thread mid-pass was answered from whatever had
  registered so far — two threads in one process could therefore record
  `RegistrySnapshot`s with different `module_count` and `modules_hash` for the
  same install. Such a caller now waits for the pass and is handed the complete
  registry. Re-entry from the discovering thread itself — a plugin's
  `register_all` reading the catalog — is still answered from the partial state,
  which is the only answer that cannot deadlock, and still does not start a
  second pass. A reader asks whether a pass is running *before* whether the
  registry is initialised, because a forced rediscovery — every `refresh()` —
  rebuilds an already-initialised registry and never lowers that flag, so the
  opposite order let readers past the lock and into the rebuild. `refresh()`
  also holds the lock across its clear and rediscover so the empty gap between
  them is not observable. Rollback, ownership and `clear()` semantics are
  unchanged. `REGISTRY_VERSION` moves 1.1.0 → 1.2.0.
- Plugin discovery is now a transaction over the registry, keyed on what a
  plugin's `register_all()` actually registered rather than on what the registry
  happens to own afterwards. Ownership metadata says who owns a row now, not
  whether the current pass put it there, so it could not tell a module a plugin
  still provides from one left over from an earlier pass, nor a row the plugin
  created from one it overwrote. Three consequences are corrected:
  - `discover_plugins(force=True)` now removes modules a plugin has stopped
    providing. A plugin that re-registers and does not mention a module it used
    to provide has withdrawn it; the row no longer lingers as a module nothing
    installed still vouches for, and no longer counts toward that plugin's
    `module_count`. The withdrawal reaches the contribution record, so the next
    clear/discover cycle does not replay the retired module.
  - A failed plugin load now restores rows it overwrote instead of deleting
    them. A registration that runs before the failure is stamped with the
    loading plugin's name, so dropping everything the plugin appeared to own
    destroyed flyto-core's own module — or another plugin's — rather than
    returning it to its owner. Rollback now replays each displaced row exactly
    and deletes only ids that held nothing beforehand.
  - The contribution record is replayed only into a registry that began the pass
    empty, which is what `clear()` looks like from discovery. A no-op
    `register_all()` on a live registry says nothing about what the plugin
    provides, so a plugin that legitimately provides nothing is no longer handed
    an earlier pass's modules.

  `REGISTRY_VERSION` moves 1.3.0 → 1.4.0. Accepted 2026-08-11 on branch `main`:
  the six pinned checks in `.flyto/coding.yaml`, the Core module-contract proof,
  strict Indexer verification, and an independent replay of 78 registry and 25
  catalog tests all passed. Accepted against these flyto coding implementation
  revisions (SHA-256, not Git commit hashes):
  - Documentation — job `job_453f3754aa2041309060b75a`, revision
    `ebeb0ebfcab2d56bec576a944dcadd23fa197ff9726c558379df1c76eb12e341`.
  - Source and tests — job `job_ad0baf4f580e4bc6aaac37de`, revision
    `b391189517db77146c4ab51def48ed7ada04fb30308296480e2e083df46bf65c`.
  - Generated catalog and tests — job `job_8d8d49019afa402a8c503aa0`, revision
    `a08df544401cf36a54dfe4f6fc084512cb3035a9febf885442baca5cd8366f15`.

  The in-process registry transaction is closed. The out-of-process
  `PluginService` / runtime plugin lifecycle is a separate surface and remains
  outside it, as do the DRAFT `flyto.plugin.v1` manifest and the still-uncalled
  `RuntimeInvoker.set_plugin_manager` (`docs/specs/PLUGIN_MANIFEST_SPEC.md`).

### Documentation

- `docs/specs/PLUGIN_MANIFEST_SPEC.md` — DRAFT specification of the
  language-neutral plugin manifest, with an implementation-status table
  separating what the code enforces from what is only specified. Records that
  the out-of-process plugin path currently has no policy gate and no caller
  wiring it to workflow execution.

### Security

- Rejected IPv4 and IPv6 unspecified addresses in the shared SSRF classifier,
  including every textual representation of `::`. This closes
  GHSA-gc4h-hj7x-gp5p, where `http://[::]:8080/` passed validation and reached
  services listening on IPv6 loopback. Regression coverage exercises both the
  address classifier and the complete URL guard.
- Policy is now scoped per plugin. A plugin's modules are checked against
  `FLYTO_PLUGIN_GRANTS` (`plugin:permission`) rather than the process-global
  `FLYTO_GRANTED_PERMISSIONS`, so a plugin declaring a dangerous permission can
  no longer reach a grant the operator made for flyto-core itself.
  `FLYTO_PLUGIN_DENYLIST` / `FLYTO_PLUGIN_ALLOWLIST` govern which plugins may
  run at all. The global module filter still runs first, so the plugin dimension
  can only narrow. Ownership is stamped by the registry and cannot be claimed by
  a module.
- The out-of-process plugin path now passes the same gate. `RuntimeInvoker.invoke`
  calls `enforce_module_policy` on the resolved module id before routing, so the
  plugin path and the legacy fallback are covered alike, and a step naming an id
  the registry does not know can no longer reach a subprocess that the chokepoint
  never sees. A refusal returns `MODULE_POLICY_DENIED`; a manifest that cannot be
  read does not open the gate.

### Added

- `register_module(provides_capability=...)` lets a module declare the capability
  it provides, and `ModuleRegistry.capabilities()` returns them grouped by
  capability. This is how a host discovers that installing a package made a
  capability available, instead of an operator hand-typing the name into a
  command elsewhere. Optional; unset for every existing module. Serves plugins
  arriving through the Python `flyto.modules` entry point — one binding, not a
  language-neutral plugin contract.

## [2.27.0] - 2026-08-08

Minor rather than patch: the two boundary changes below refuse inputs that
previous releases accepted, so this is not a drop-in upgrade for every caller.
Read the **Changed** section before upgrading.

### Security
- Closed the filesystem sandbox boundary across the whole module registry
  rather than one report at a time. A registry-wide audit found every
  remaining module that took a caller-supplied path to a filesystem sink
  without `validate_path_with_env_config`, and confined all of them:
  `testing.visual.compare` (`diff_path`, and the `expected`/`actual` read
  paths — this module declares no `required_permissions`, so the write was
  unauthenticated), `data.xml.parse` (`file_path`, the sibling
  GHSA-wc94-386q-5478 missed), `browser.upload` and `aws.s3.upload`
  (`file_path` — host files shipped to a remote origin), `ssh.sftp_upload`
  and `ssh.sftp_download` (`local_path`, the SFTP counterpart of
  GHSA-hmq9-xw4w-7ppc), `file.delete` (`file_path` — arbitrary file
  deletion), `file.exists` (`path` — filesystem oracle), `git.clone`
  (`destination`), `git.commit`/`git.diff` (`repo_path`), `llm.code_fix`
  (`source_files`, where the previous `'..'` substring check let absolute
  paths through), `verify.spec` (`ruleset_path`), plus `docker.build`,
  `process.start` and `sandbox.execute_shell` as hardening. None of these
  were reported; they are the same CWE-22 shape as the published advisories.
- Closed the outbound network boundary across the registry on the same basis.
  Added `enforce_outbound_host` and `enforce_outbound_service_url` to
  `core/utils.py` — the raw-TCP and non-HTTP-scheme counterparts of
  `enforce_outbound_url`, which only understands http(s) — and routed every
  module that reaches the network from a caller-supplied target through one of
  them: `verify.run`, `verify.capture` and `verify.visual_diff` (raw
  Playwright `page.goto` bypassing `BrowserDriver._guard_navigation`, and in
  `visual_diff`'s case a bare playwright browser with no egress guard in any
  mode), `browser.connect` (`ws_endpoint` — CDP is remote code execution by
  design), `browser.launch` (`proxy` — the egress guard inspects request URLs,
  not where the proxy points), `git.clone` (`url` — the existing validator
  bounded the transport but never the destination), `cache.*` and `queue.*`
  (`redis_url`), `db.mysql.query`, `db.redis.get/set`, `notification.email.send`
  (`smtp_server`, which also carries SMTP credentials to whatever answers),
  `ssh.exec`/`ssh.sftp_upload`/`ssh.sftp_download` (`host`), `network.ping`,
  `network.port_scan`, `network.traceroute`, `port.wait`, and `browser.emulate`.
- Deduplicated the host resolver that GHSA-v7q9-pr72-5fmv was about.
  `port.check` carried the only correct implementation (IP literals
  range-checked directly so IPv6 transition forms cannot skip the check, and
  fail-closed on resolution failure); it now lives in `core/utils.py` as
  `resolve_guard_ip` and backs every host-taking module.
- Added `tests/core/test_write_sink_coverage.py` and
  `tests/core/test_outbound_guard_coverage.py`, which walk the module registry
  and fail the build if any module declares a path- or network-shaped parameter
  without reaching the corresponding guard. The outbound test is MRO-aware, so
  a guard inherited from a mixin (`LLMClientMixin` for `agent.chain` /
  `agent.autonomous`) counts. Exemptions must state what the value really
  addresses and are re-verified each run: a module excused as "makes no
  request" fails once it opens a connection, and one excused for validating
  locally fails once that validation is deleted. Guard coverage is now a CI
  property instead of something an author has to remember.

- Published `SECURITY_STATUS.md`: every advisory with its severity, affected
  range, fixed-in version and the regression test that covers it. It is
  generated from `security/advisories.json` by
  `scripts/generate_security_status.py` and verified in CI —
  `tests/core/test_security_status.py` asserts that every test it names
  resolves to a collectable node, so the coverage column cannot drift into
  fiction, and `scripts/check_documentation.py` fails on a stale page.
- Wrote regression tests for three advisory fixes that shipped without one.
  Building the status page required naming a test per advisory and found that
  GHSA-hr7p-wg7r-hg9m (`${env.VAR}` interpolation bypassing the `env.get`
  denylist), GHSA-qq9q-xgm3-xv9g (environment API keys sent to a
  caller-supplied `base_url`) and GHSA-mxcc-cr6x-2mvr (MCP `run_recipe`
  loading workflows outside the bundled directory) had none. The fixes were
  present and correct, but nothing would have caught their removal.

### Changed
- **Breaking for callers relying on the old permissiveness.** Modules listed
  above now reject paths outside `FLYTO_SANDBOX_DIR`, which defaults to the
  process working directory. Workflows that passed absolute paths such as
  `/tmp/repo` to `git.clone` or `data.xml.parse` must set
  `FLYTO_SANDBOX_DIR` to a directory covering them. Tests needing real files
  outside the working directory can use the new `sandboxed_tmp_path` fixture.
- **Breaking for workflows targeting private hosts.** Modules that connect to
  a caller-supplied host now reject private and link-local targets unless the
  operator sets `FLYTO_ALLOWED_HOSTS` or `FLYTO_ALLOW_PRIVATE_NETWORK=true`.
  Loopback is unaffected, so self-hosted Redis/MySQL/SMTP on `localhost`
  continues to work; a Redis at `10.0.0.5`, an SMTP relay on the LAN, or
  `network.ping` against an internal host now needs an explicit allowlist
  entry. Unresolvable hosts are refused rather than attempted.
- `register_module` now preserves the defining module on function-style
  module wrappers (`__module__`, `__wrapped_func__`) instead of reporting
  `decorators.py`, so registry-wide static checks can resolve real sources.

### Fixed
- `SECURITY.md` advertised support for the 1.x line, which has not existed
  since well before the 2.26 series. It now names the supported range, the
  current secure release, and documents the two environment variables that
  define the filesystem trust boundary.

## [2.26.12] - 2026-08-07

### Fixed
- Confined `browser.download`'s `save_path` to the configured filesystem
  sandbox before the directory is created or the downloaded bytes are
  written, closing the gap the 2026-07 file-write hardening waves left in
  `browser.download`, `browser.screenshot`, and `browser.pdf`.
- Escaped caller- and page-derived values in the `verify.report` HTML
  report and confined its `output_dir`/`name`-derived destination, the
  `warroom.report` `output_path`, `verify.visual_diff` and `verify.run`
  `output_dir`, `browser.launch`'s `record_video_dir`, and `data.dedup`'s
  `hash_file` to the same sandbox boundary — the same unvalidated-path
  pattern found while auditing the `browser.download` report.
- Revalidated the www-toggled retry host in `browser.goto` against the SSRF
  guard before navigating, closing a bypass where the submitted host passed
  validation, navigation failed, and the toggled host (equally attacker-
  controlled) was never checked. Added the same guard as defense in depth
  inside the browser driver's `goto()` so a future caller that derives a new
  navigation target and forgets to revalidate is still covered.
- Rejected tar archive members that are symlinks, hardlinks, or other
  special types before extraction in `archive.tar_extract`, closing a Tar
  Slip where a symlink member pointing outside the sandbox let a following
  member write through it on Python runtimes without `tarfile` `filter=`
  support. Hardened the post-extraction path check (both `tar_extract` and
  `zip_extract`) to compare resolved real paths against an `os.sep`-bounded
  base instead of a lexical prefix match.
- Made `port.check`'s SSRF guard fail closed: an unresolvable host (rather
  than only a resolved private IP) is now treated as unsafe, closing a
  bypass via IPv6 transition literals (e.g. `::ffff:127.0.0.1`) that raised
  `gaierror` and fell through a bare `pass`.
- Replaced stdlib `re` with the interruptible `regex` engine (native
  per-call timeout) in the `regex.*` modules, so a catastrophic
  backtracking pattern is abandoned within a bounded wall-clock budget
  instead of freezing the event loop for every other in-flight request.

## [2.26.11] - 2026-08-03

### Fixed
- Confined caller-supplied paths for CSV/YAML/Excel/PDF/image readers and
  browser/document file writers to the configured filesystem sandbox before
  any read, directory creation, provider call, or write can occur.
- Restricted agent Ollama endpoints to loopback by default. Operator-enabled
  remote endpoints now pass the shared SSRF policy, connect-time DNS pinning,
  redirect revalidation, and response-body redaction controls.
- Raised patched dependency floors for cryptography and, on Python 3.10+,
  Starlette and the Python build/install toolchain. Python 3.9 retains its
  compatible API and build-tool lines where upstream no longer publishes a
  patched release.
- Closed the open plugin-runtime path-injection chain by validating caller
  plugin IDs at the manager boundary, selecting plugin directories only from
  the validated discovery map, and rejecting discovered symlinks that resolve
  outside the configured plugin root.
- Stopped MCP HTTP header-decoding failures from reflecting exception details
  to remote callers; malformed `Mcp-Name` values now receive a stable generic
  protocol error.
- Replaced URL-prefix assertions in the Warroom bundle regression with parsed
  HTTPS origin checks, and updated the pinned PyPI publishing action to
  `pypa/gh-action-pypi-publish` v1.14.2.

### Added
- Updated the STDIO and Streamable HTTP MCP surfaces to the 2026-07-28
  protocol. Modern clients can discover the server without a setup handshake,
  send independent requests without sticky protocol sessions, and safely
  cache discovery and tool-list results. Required request metadata and HTTP
  header mirrors are validated before tool execution. Existing
  handshake-based clients remain supported through MCP 2025-11-25.
- Added `reverse.deobfuscate`, delivering Phase 4 of the `reverse.*` toolkit:
  real semantic JavaScript deobfuscation (control-flow-flattening reversal,
  string-array decoding, self-defending/debug-protection bypass, webpack/
  browserify unpacking) via the `webcrack` npm package, run in a dedicated
  Node.js sidecar worker (`deobfuscate_worker/worker.mjs`) spawned and killed
  per invocation — not the generic JSON-RPC plugin runtime
  (`src/core/runtime/manager.py`), which was found to have unenforced
  resource limits and no kill-on-timeout, nor Playwright's private/fragile
  bundled Node, both already rejected in DECISIONS.md for exactly this
  reason. Unlike `reverse.code`, webcrack's own pipeline unconditionally
  evaluates the input inside an `isolated-vm` sandbox, so this module is
  gated behind a new deny-by-default `code.execute` permission. Requires a
  system-installed Node.js 22 or 24 plus a one-time `npm install` in the
  worker directory — this module does not attempt to auto-install or bundle
  Node.js itself. The `restringer` npm package was deliberately left out of
  this first version: its published package is maintained by an unofficial
  fork whose dependency tree has silently dropped the `isolated-vm` sandbox
  the canonical `HumanSecurity/restringer` project still declares — not
  something to build on without further verification. Reconciled the
  generated catalog to 468 modules across 85 categories.
- Added `reverse.request_breakpoint` (set/remove/list), strengthening the
  `reverse.*` toolkit: pauses execution when an XHR/fetch request URL
  contains a given substring, via CDP's DOMDebugger domain (the same
  mechanism behind Chrome DevTools' Sources > XHR/Fetch Breakpoints panel).
  A hit surfaces through the same `Debugger.paused` event as a script
  breakpoint, so `reverse.wait_paused`/`reverse.resume`/
  `reverse.get_call_frames`/`reverse.evaluate_on_call_frame` all apply
  unchanged — no new pause/resume mechanism was needed. Also added
  session-snapshot reuse to `reverse.attach`: reattaching to a page that
  already has an enabled debugger session now returns that session's
  existing snapshot (script cache, breakpoints, request breakpoints, hooks)
  instead of always detaching and rebuilding from scratch; pass
  `force_new: true` to opt back into the old always-fresh behavior.
  Reconciled the generated catalog to 467 modules across 85 categories.
- Added a `reverse.*` module category (Phase 1 of the reverse-engineering
  roadmap): a CDP-based interactive JavaScript debugger. `reverse.attach` /
  `reverse.detach` manage a `ReverseSession` CDP Debugger session;
  `reverse.scripts` lists/fetches/searches loaded scripts; `reverse.breakpoint`
  sets/removes breakpoints; `reverse.wait_paused`, `reverse.resume`, and
  `reverse.step` control execution; `reverse.get_call_frames` and
  `reverse.evaluate_on_call_frame` inspect paused state, including in-memory
  locals/closures. All nine modules require the new `browser.debug` permission,
  which is deny-by-default (added to `_DANGEROUS_PERMISSIONS`) since a paused
  debugger can read secrets held in page memory and freezes the page's JS.
  Reconciled the generated catalog to 461 modules across 85 categories.
- Added Phase 2 of the `reverse.*` toolkit: `reverse.hook`
  (install/remove/list/get_records) wraps a JS function via CDP's
  `Page.addScriptToEvaluateOnNewDocument` so calls, arguments, and return
  values are recorded without a paused breakpoint; `reverse.network`
  (start/stop/list/get_initiator) traces which JS call stack triggered a
  given HTTP request via CDP's Network domain; `reverse.websocket`
  (start/stop/list/get_frames) captures WebSocket connections and frames.
  All three extend the same `ReverseSession`/CDP session `reverse.attach`
  already creates rather than a second session type — Debugger stays enabled
  so initiator stacks stay rich, and no new transport-wiring was needed since
  the existing `debugger_session` registry already covers any `reverse.*` id.
  Reconciled the generated catalog to 464 modules across 85 categories.
- Added Phase 3 of the `reverse.*` toolkit: `reverse.code`
  (beautify/list_functions/list_strings/find_calls) beautifies minified
  JavaScript (`jsbeautifier`) and searches its AST for function declarations,
  string literals, and call sites (`tree-sitter` + `tree-sitter-javascript`).
  Pure Python — no Node.js involved, no new CI surface — added as an
  optional `jsast` extra. Unlike every other `reverse.*` module, `reverse.code`
  requires no permission: it never touches a browser/CDP session and never
  executes the code it analyzes, only parses and reformats a JS string.
  True semantic deobfuscation (control-flow-flattening reversal, string-array
  decoding) remains a separate, deferred Phase 4 — it needs an actual JS
  execution engine, which depends on solving the Node.js-invocation
  reliability problem this phase's research surfaced (Playwright's bundled
  Node is a private/undocumented API already known to be fragile under
  PyInstaller, and the `~/.flyto/node/` fallback has no downloader built).
  Reconciled the generated catalog to 465 modules across 85 categories.
- Added `reverse.sourcemap` (resolve/list_sources/get_original_source),
  strengthening the `reverse.*` toolkit: resolves a generated (minified/
  bundled) code location to its original source file/line/column/name via
  a hand-rolled Source Map v3 VLQ decoder (no pip dependency — the one
  plausible package, `sourcemap` on PyPI, has had no release since 2017).
  Session-independent and permission-free like `reverse.code`: takes the
  source map JSON (or a `data:` URI) as a plain parameter — `sourceMapURL`
  was already captured and exposed by `reverse.scripts` (action=list), and
  this module never fetches an external `.map` file itself; that's a normal
  `http.get` step in the calling workflow, already SSRF-guarded, so no new
  security-sensitive fetch code was written. Reconciled the generated
  catalog to 466 modules across 85 categories.

### Fixed
- Hardened all core API, OAuth2 token, and Slack/Discord/Teams webhook HTTP
  emitters with connect-time DNS pinning and per-redirect URL validation.
  OAuth2 failures no longer reflect token-endpoint response bodies.
- Confined Azure, GCS, and both S3 download implementations to the configured
  filesystem sandbox before provider SDKs create directories or write files.

## [2.26.10] - 2026-07-23

### Added
- Added a source-backed documentation system covering all maintained Python
  files/declarations, literal module registrations, CLI parsers, HTTP routes,
  environment readers, recipes, bundles, and workflow assets.
- Added technical whitepaper, feature, API, configuration, security, testing,
  operations, and migration guides plus CI-enforced documentation ownership,
  generated drift, local-link, Flyto2 naming, and public-mailbox checks.
- Added `crypto`, `dns`, and `ai` package extras and aligned the development
  extra with the non-browser test suite.
- Made `pyproject.toml` the single dependency source, converted legacy
  requirements files to extra delegates, and regenerated the base runtime lock.
- Added a locked jsdom test runtime and dependency audit for browser-contract
  tests.
- Added import and test-isolation contracts that reject duplicate `src.core`
  package identities and collection-time security overrides.
- Added an architecture-aware coverage profile for the maintained control
  kernel while preserving adapter catalog and integration suites.

### Changed
- Published the generated 452-module package description, current Flyto2 links,
  and Apache 2.0 metadata to replace the 451-module PyPI listing from 2.26.9.
- Reconciled public package, registry, documentation, and demo metadata to the
  generated 452-module catalog after adding `core.api.tavily_search`.
- Made the Python reference generator discover declarations nested in control
  flow and explicitly scoped API coverage away from test-only functions.
- Migrated the HTTP API shutdown hook to FastAPI lifespan handling and made
  browser-session cleanup observable on failure.
- Updated async plugin tests for current event-loop ownership and isolated
  Cloud verdict test stubs from process-wide FastAPI/Pydantic modules.
- Scoped local HTTP test access to explicit hosts and ports and declared the
  `e2e` marker.
- Migrated package licensing to PEP 639 SPDX metadata and removed stale
  manifest globs so maintained build backends produce warning-free artifacts.
- Made Indexer policy enforceable on the security-control kernel, replaced its
  broad API catches with explicit exception families, and removed the final
  dynamic `__import__` call from the Gmail adapter.

### Security
- Protected workflow status and evidence reads with bearer authentication and
  added unauthenticated-access regression tests.
- Kept the default gitleaks rules active while narrowly documenting historical
  JWT test vectors and generating current test keys without secret-shaped
  literals, so remote history and directory scans remain actionable.
- Explicitly named workflow ports now fail closed instead of silently binding
  to the only available port when the requested ID is invalid.
- Removed test-order paths that could leave localhost/private-network access or
  verification API auth disabled for later security tests.

## [2.26.9] - 2026-07-19

### Changed
- Synced MseeP/MCP registry-facing metadata: `server.json` now matches
  `pyproject.toml` version 2.26.9, and public descriptions use the verified
  the then-current Flyto2 Core 451-module positioning.
- Prepared a metadata-only PyPI patch release so live registry backlinks,
  project URLs, and the then-current 451-module package description can replace the
  stale 412-module listing.

### Added
- **Captcha: CaptchaAI provider** — `CaptchaSolver` now accepts
  `provider='captchaai'`. CaptchaAI is 2Captcha-API-compatible (in.php/res.php),
  so it reuses the existing 2Captcha submit/poll path against
  `https://ocr.captchaai.com` (reCAPTCHA v2/v3, Cloudflare Turnstile). Also
  added to the `browser.challenge` captcha-solver dropdown.
- Added generic `verification.discover`, `verification.generate_scenarios`,
  `verification.run`, and `verification.report` module IDs as the forward path
  for deterministic verification primitives. Existing `warroom.*` modules stay
  as compatibility aliases; product workflows should be composed by
  flyto-engine.
- `warroom.report` now emits `flyto.core.deterministic_verification.v1`, a deterministic
  automation-testing summary for coverage, intent graph, scenario synthesis,
  replay reliability, ghost API type A/B/C, business invariants, RBAC matrix,
  event-stream contract, scheduler-loop contract, and screenshot/DOM/network
  evidence chain.
- Automation evidence now declares `engine_mode.llm_required=false`,
  `llm_role=optional_evidence_reviewer`, and
  `gate_authority=deterministic_evidence_gate`. Product naming is injected by
  engine artifacts; core remains the deterministic verification runtime.
- `warroom.report` now emits a 90-point Product Verification evidence gate
  (`gate_verdict`, `gate_score`, score breakdown, artifact completeness, and
  blockers) so release readiness is tied to reproducible screenshots, DOM,
  network logs, replay reliability, reachable coverage, and live/non-dry-run
  evidence instead of a standalone score.
- `warroom.run` now separates module execution `ok` from product replay
  `replay_ok`, preserving failed replay results for downstream evidence packs
  instead of letting workflow normalization collapse them into a generic error.
- `Dockerfile.verification` for the dedicated `flyto-verification` runner
  microservice. It installs browser/API extras, bundles Chromium, exposes
  `:8344`, and serves `/health` for engine/compose readiness checks.
- `flyto-verification` runner service entrypoint for deterministic Warroom
  Product Verification dispatches. The service validates engine-computed
  target scope, executes server-owned workflow YAML, and emits runner callback
  payloads with evidence signatures.
- `flyto-verification` now converts `browser.screenshot` module outputs
  (`filepath`/`path`) into screenshot callback artifacts, so engine can persist
  previewable Product Verification evidence.
- Operator-controlled `FLYTO_HTTP_ALLOWED_PORTS` support for the SSRF guard, so
  dev/staging verification can allow a specific local browser target port
  without disabling private-host protection or broadening production defaults.
- Deterministic Warroom verification modules: `warroom.discover`,
  `warroom.generate_scenarios`, `warroom.run`, `warroom.report`, and
  `warroom.llm_review`.
- `warroom-deterministic-audit` recipe and Warroom verification docs.
- `warroom.public_site_verify` and the `flyto2-public-site-verification` recipe
  to evaluate DNS/TLS/route/browser/SEO-GEO evidence without LLM judgment.

### Changed
- Documentation and package metadata reflected that release's registry inventory:
  451 modules across 84 catalog categories, 41 built-in recipes, and Flyto2
  website/documentation URLs.
- `testing.e2e.run_steps` and `testing.scenario.run` now execute real module
  steps and assertions instead of placeholder success.
- `warroom.generate_scenarios` DOM assertions now wait up to five seconds for
  SPA body text before flagging an empty page as P0, preventing hydration races
  from reducing replay reliability while still failing true blank screens.
- `Dockerfile.verification` packaging now keeps the root `README.md` in the
  Docker build context while continuing to exclude bulk markdown/docs content.
  This fixes local compose builds of the Product Verification runner image.
- `Dockerfile.verification` now forces `HEADLESS=true` and
  `DEPLOYMENT_MODE=worker`, so Product Verification browser replay works in
  containerized runner environments without an X server.
- `warroom-deterministic-audit` now composes the generic `verification.*`
  modules while preserving the existing recipe name for compatibility.

## [2.26.8] - 2026-07-11

### Security
- **GHSA-p34x-fmph-9fjx (Critical) — arbitrary file write via unguarded
  `data.*`/`file.*` write modules (incomplete fix of GHSA-2956).** The GHSA-2956
  remediation routed only a hand-picked module list through
  `validate_path_with_env_config()`; the `data.*`/`file.*` families stayed
  unconfined — `data.csv.write` used a `'..'` substring denylist that misses
  absolute paths, and `data.json_to_csv` / `file.copy` / `file.move` had no path
  check at all, so a client-controlled absolute path was an arbitrary-write
  primitive escaping `FLYTO_SANDBOX_DIR`. Every file-writing module that takes a
  caller-controlled path now confines through `validate_path_with_env_config()`:
  `data.csv.write`, `data.json_to_csv`, `file.copy`, `file.move`, plus
  `browser.record`, `meta.update_docs`, `verify.annotate`, and `verify.ruleset`
  found in the same audit.
- **GHSA-2mr3-rxrq-238c (High) — second-order SSRF in `http.paginate`.**
  `paginate` validated only the initial `base_url`, then followed the
  server-supplied `Link: rel="next"` URL with no revalidation, so an attacker's
  page-1 response could point `next` at internal/metadata space and aggregate
  the internal body into the returned items. The Link-header next-page URL is
  now re-run through the SSRF guard before being followed (offset/page/cursor
  strategies stay on the already-validated base host); a blocked follow-up
  returns `SSRF_BLOCKED`. Regression test added.
- **GHSA-mxcc-cr6x-2mvr (Medium) — path traversal in MCP `run_recipe`.**
  `load_recipe()` concatenated the caller-controlled `recipe_name` into
  `RECIPES_DIR / f"{recipe_name}.yaml"`, so `../` segments loaded workflows
  outside the bundled recipes directory (which `list_recipes` never discloses).
  `load_recipe()` now resolves the path and confines it to `RECIPES_DIR`,
  returning None for anything outside it.
- **GHSA-pfg2-w999-497v (High) / GHSA-6pm8-6f34-9v3g (Medium) — DNS-rebinding
  SSRF (resolve-then-connect TOCTOU).** `validate_url_ssrf` resolved the host,
  checked the IP, then returned the *hostname*, so aiohttp performed an
  independent second DNS lookup at connect time — an attacker controlling DNS
  (TTL 0) could answer public for the guard and private for the connection.
  Outbound HTTP modules now build their session via `guarded_client_session()`,
  whose connector uses an `_SSRFGuardedResolver` that resolves once and rejects
  private/blocked IPs at resolve time, so the address validated is the address
  connected to. Wired into all outbound-guarded modules (`http.get/request/
  batch/paginate/session`, `graphql.query/mutation`, `monitor.http_check`,
  `notification.send`, `communication.slack_send/webhook_trigger`,
  `ai.vision_analyze`, `image.download`, `llm.chat`). Operator-approved private
  access via `FLYTO_ALLOW_PRIVATE_NETWORK` / `FLYTO_ALLOWED_HOSTS` is preserved.

## [2.26.7] - 2026-07-08

### Security
- **GHSA-jx74-cqjv-2c67 (Critical) — flyto-verification `/run` unauth SSRF +
  runner-secret exfil.** `/run` was unauthenticated (Dockerfile binds
  `0.0.0.0:8344`) and forwarded a caller-controlled `callback_url` verbatim with
  `X-Internal-Key: $FLYTO_RUNNER_SECRET` attached. `/run` now requires a shared
  secret (`X-Internal-Key`; `FLYTO_VERIFICATION_API_KEY`, fallback
  `FLYTO_RUNNER_SECRET`) and **fails closed** when none is configured;
  `post_callback` runs `callback_url` through the SSRF guard and only attaches
  the internal key for trusted hosts (`FLYTO_ENGINE_URL` /
  `FLYTO_TRUSTED_CALLBACK_HOSTS`).
- **GHSA-pgwh-4jj4-qm8v (High) — HTTP modules missing the SSRF guard.** Many
  HTTP-emitting modules fetched client-controlled URLs without the SSRF guard
  their siblings apply. New `enforce_outbound_url()` is now called before the
  outbound request in `core.api.http_get`/`http_post`,
  `graphql.query`/`mutation`, `monitor.http_check`, `slack_send`,
  `notification.{slack,discord,teams}.send_message`, `ai.vision_analyze`
  (Anthropic image download), `verify.visual_diff`, and `browser.proxy_rotate`.
- **GHSA-c9hr-64h3-gxpc (High) — redirect SSRF on the guarded HTTP modules.**
  `http.get`/`http.request`/`http.batch` validated only the initial URL then
  followed 30x redirects with no revalidation. New `guarded_aiohttp_request()`
  disables auto-redirect and revalidates every `Location` hop through the SSRF
  guard before following it.

## [2.26.6] - 2026-07-07

### Security
- **GHSA-2956-977x-2w3r (Critical) — arbitrary file write.** Every file-writing
  module now routes its output path through the central
  `validate_path_with_env_config()` guard, confining writes to
  `FLYTO_SANDBOX_DIR`; the caller can no longer supply the base its target is
  checked against. Affects `image.download`/`convert`/`resize`/`crop`/
  `compress`/`rotate`/`watermark`/`qrcode_generate`,
  `document.excel_write`/`pdf_fill_form`/`word_to_pdf`/`pdf_to_word`, and the
  `browser.pagination` checkpoint.
- **GHSA-hr7p-wg7r-hg9m (High) — `${env.*}` secret exfil.** `${env.VAR}`
  interpolation in the workflow resolver is now gated by the same policy as the
  `env.get` module (new `is_env_var_allowed()`): deny-by-default, opt-in via
  `env.get` being allowed or an explicit `FLYTO_ENV_VAR_ALLOWLIST`.
- **GHSA-qq9q-xgm3-xv9g (High) — LLM/API key leak to attacker `base_url`.** An
  environment-derived provider key is now only attached to the provider's
  official endpoint or a host on `FLYTO_TRUSTED_LLM_HOSTS` (new
  `assert_env_credential_endpoint_allowed()`), across `llm.chat`, `ai.model`,
  `llm.agent` and `vector.connector`; also adds the missing SSRF check to
  `ai.model`.

## [2.26.3] - 2026-05-30

### Security
- **SSRF guard bypass via IPv6 transition addresses** (GHSA-794r-5rp2-fpg8). `is_private_ip()` only range-checked the literal address, so IPv6 transition forms embedding a private/loopback IPv4 — IPv4-mapped (`::ffff:127.0.0.1`), IPv4-compatible (`::a.b.c.d`), 6to4 (`2002::/16`), and NAT64 (`64:ff9b::a9fe:a9fe`, encoding the `169.254.169.254` cloud-metadata endpoint) — were classified non-private and bypassed the SSRF allow/deny guard on 6to4/NAT64-enabled hosts. `is_private_ip()` now unwraps these transition forms via `_extract_embedded_ipv4()` and range-checks the embedded IPv4 in addition to the outer address. Public IPv4 embedded in a transition form stays allowed. Regression tests added in `tests/core/test_ssrf_ipv6_transition.py`.

## [2.27.0] - 2026-04-30

### Added
- **HTTP Batch module** (`http.batch`) — execute N HTTP requests in sequence or parallel, capturing per-request status, body, headers, duration, and label. Designed for pentest blueprints that need baseline vs. payload comparison (SQL injection, XSS reflected, auth bypass).
- **Assert Status module** (`testing.assert_status`) — compare HTTP probe results against a baseline and produce a verdict string (`exploitable` / `sanitized` / `unreachable`). Powers closed-loop pentest verdicts.
- **Assert Timing module** (`testing.assert_timing`) — detect timing-based side channels by comparing response durations across baseline and payload probes.
- **Assert Contains enhancement** (`testing.assert_contains`) — extended to support multi-pattern matching and negation for pentest output validation.
- **LLM Agent: per-direction token accounting** — `_run_tools_loop` now tracks `input_tokens`, `output_tokens`, and `cached_input_tokens` separately. Result includes OpenAI-compatible `usage` dict for cost reporting by runner.

### Changed
- **LLM chat models** — `_interfaces.py` and `_chat_models.py` updated to surface `input_tokens`, `output_tokens`, `cached_input_tokens` on response objects.

### Tests
- **E2E closed-loop roundtrip** (`test_closed_loop_roundtrip.py`) — full scan → verify → verdict pipeline test.
- **Engine YAML integration** (`test_engine_yaml_integration.py`) — 605-line E2E covering YAML workflow execution against the engine.
- **Real Juice Shop** (`test_real_juice_shop.py`) — live OWASP Juice Shop integration test for pentest workflows.
- **Closed-loop module unit tests** (`test_closed_loop_modules.py`) — 428 lines covering batch, assert_status, assert_timing, assert_contains.

## [2.26.0] - 2026-04-20

### Added
- **Pentest workflow library** — 12 ready-to-run YAML workflows in `workflows/pentests/`, one per OWASP category: `access_control`, `sql_injection`, `code_injection`, `client_side`, `auth_session`, `ssrf`, `llm_injection`, `business_logic`, `deserialization`, `file_misconfig`, `secrets_crypto`, `hardening`.
- **Pentest registry** — central index with OWASP category mapping and per-workflow requirements so orchestrators can select tests by coverage area instead of by filename.

## [2.23.0] - 2026-03-19

### Added
- **Browser: Resource filtering** — `BrowserDriver.block_resources(['image', 'stylesheet', 'font'])` blocks specified resource types via `page.route()` to speed up scraping (50-70% bandwidth savings). `unblock_resources()` removes all blocking rules.
- **Browser: Deterministic fingerprint seeding** — GPU/hardware profile randomization now uses a seeded LCG (`_fpRand()`) instead of `Math.random()`, ensuring consistent fingerprints within a persistent context session. Prevents cookie + GPU mismatch detection.
- **Browser Pool: Health check & auto-relaunch** — `BrowserPool.acquire()` runs `page.evaluate('1')` with 3s timeout. Dead drivers are automatically relaunched with original parameters.
- **Browser Pool: PoolTaskError** — `pool.map()` returns structured `PoolTaskError(error, retryable)` instead of plain dicts, enabling callers to distinguish retryable failures from permanent ones.
- **Login: MFA/2FA auto-detection** — After form submission, scans for OTP inputs (`autocomplete="one-time-code"`, `inputmode="numeric" maxlength="6"`) and MFA text patterns. On detection, creates a breakpoint so users can complete verification in the browser, then workflow resumes. Excludes password reset flows to avoid false positives.
- **Dedup: Context storage mode** — `data.dedup` now supports `storage='context'` to persist hashes in the execution context (for cloud/stateless workers) instead of local disk.
- **Checkpoint: JSONL streaming** — `PaginationCheckpoint` stores items in a separate `.jsonl` file (append-only) instead of embedding all items in the metadata JSON. Metadata stays small regardless of item count. `load_items()` reads the JSONL file. `VERSION=2` (old checkpoints safely ignored).
- **Pagination: Direct URL resume** — Checkpoint resume now uses `goto(last_url)` directly instead of re-navigating through all previously processed pages. Falls back to sequential navigation if direct goto fails.
- **Interact: Input validation** — Action whitelist (`click`/`type`/`select`/`toggle`), selector length cap (500 chars), and injection pattern rejection (`javascript:`, `eval(`, `{}<>`).

### Changed
- **Captcha: API key no longer in URL** — 2Captcha submit and poll now use POST body instead of URL query string. `_http_post()` auto-detects form-encoded (2Captcha) vs JSON (CapSolver).
- **Captcha: Detection priority** — hCaptcha (`.h-captcha` class) is now checked before reCAPTCHA v2 (`.g-recaptcha`) to prevent ambiguous `[data-sitekey]` matches. reCAPTCHA v2 selector narrowed to `.g-recaptcha` only.
- **Dedup: Ordered eviction** — Hash storage changed from `set` to `dict` (Python 3.7+ insertion order), ensuring `max_hashes` eviction correctly removes oldest entries first.
- **Humanize: before_type delay** — Fixed `before_type()` to use `type_delay * 0.3-0.6` instead of `click_delay` for focus delay timing.
- **Proxy rotate: Persistent context honesty** — `rotate_proxy()` no longer pretends to succeed in persistent context mode. Returns `None` without updating `_current_proxy`, so callers know rotation didn't happen.
- **Stealth: chrome.loadTimes() jitter** — Replaced fixed time offsets with randomized 20-100ms jitter to prevent timing pattern detection.

### Fixed
- **Proxy rotate: Global state isolation** — Removed module-level `_proxy_pool`, `_proxy_index`, `_dead_proxies` globals. State is now stored in `self.context['_proxy_pool']` per execution, preventing cross-workflow contamination.
- **Throttle: Global state isolation** — Removed module-level `_domain_last_request` global and `global` keyword. Per-domain `RateLimiter` instances are stored in execution context.
- **ProxyPool: Thread-safety documentation** — Added docstring explaining why `threading.Lock` is correct (microsecond CPU-only critical sections, safe for both sync and async callers).

## [2.18.6] - 2026-03-12

### Changed
- **Unified connection validation** — Merged dual validation paths into single entry point `validate_connection()`. Context compatibility check (from `connection_rules/validation.py`) and data type compatibility matrix (from `types/data_types.py`) are now integrated into the main validation flow.
- **Data type compatibility matrix** — `_validate_port_compatibility()` now uses `DATA_TYPE_COMPATIBILITY` matrix for type checking instead of simple string equality. Types like `string→json`, `image→file` are now correctly recognized as compatible.

### Removed
- **Deleted `connection_rules/validation.py`** — Redundant supplementary validation module. `can_connect()`, `validate_edge()`, and `validate_workflow_connections()` are no longer needed; their logic is consolidated into `validation/connection.py`.
- **Cleaned up `modules/__init__.py`** — Removed exports of deleted functions (`can_connect`, `validate_workflow_connections`).

### Fixed
- **Context compatibility in main validation path** — AI/data modules connecting to browser/element modules are now correctly rejected at validation time (was previously only checked in the unused supplementary path).

## [2.18.5] - 2026-03-12

### Fixed
- **Browser Hints: CSS selector injection** — `stampSelector` now uses `CSS.escape()` for name attributes instead of manual quote escaping, preventing malformed selectors when names contain `]` or other special characters.
- **Browser Hints: aria-labelledby in Shadow DOM** — `resolveName` now uses `el.getRootNode().getElementById()` so `aria-labelledby` resolves correctly inside shadow roots.
- **Browser Hints: fieldset detection across Shadow DOM** — Added `closestAcrossShadow()` helper so fieldset legend context works for inputs inside shadow roots.
- **Browser Hints: isVisible improvements** — Added `aria-hidden="true"` and `visibility: collapse` checks.
- **Browser Hints: innerText reflow** — Changed `body.innerText` to `body.textContent` to avoid triggering layout reflow on large pages.
- **Browser Hints: click.py force consistency** — Post-click `get_hints()` now uses `force=True` consistent with type/select modules.
- **Browser Hints: stamp clearing optimization** — Merged two `querySelectorAll` passes in `invalidate_hints(clear_stamps=True)` into a single DOM traversal.
- **Browser Hints: extract_element_hints logging** — Silent exception catch now logs at debug level.

### Added
- **Browser Hints: file input detection** — `<input type="file">` elements now appear as `file_inputs` category with selector and label.
- **Browser Hints: range slider detection** — `<input type="range">` added to recognized input types.

## [2.18.4] - 2026-03-12

### Added
- **Browser Hint System: Shadow DOM support** — `deepQSA()` discovers all open shadow roots upfront and queries across them. Elements inside shadow DOM are automatically stamped with `data-flyto-hint` (Playwright CSS auto-pierces open shadow roots).
- **Browser Hint System: contenteditable detection** — Rich text editors (Tiptap, ProseMirror, Slate.js) using `[contenteditable="true"]` are now detected as inputs with `type: 'contenteditable'`. Deduplicates against `[role="textbox"]`.
- **Browser Hint System: Portal-rendered dropdown fallback** — When walk-up search fails, performs global search for `[role="listbox"]`/`[role="menu"]` via `aria-controls` ID cross-check, then `aria-label` matching. Only binds if exactly one candidate matches (ambiguous = stays lazy).
- **Radio group merging** — Radio buttons with the same `name` attribute are merged into a single hint group with selectable options.
- **Fieldset context** — Hints inside `<fieldset>` elements inherit the `<legend>` text as contextual label.
- **Custom dropdown stable selectors** — Improved selector stability for custom dropdown components (MUI, Ant Design, etc.).

### Changed
- **Browser Hint System: enhanced isVisible** — Now filters `opacity: 0`, `clip-path: inset(100%)`, and zero-size + `overflow: hidden` elements in addition to `display: none` and `visibility: hidden`.
- **Browser Hint System: combobox visibility check** — `[role="combobox"]` and `[aria-haspopup]` elements now go through `isVisible()` before being added as dropdown triggers (was missing before).
- **Browser Hint System: deepQSA fast path** — When no shadow roots exist on the page (99% of sites), `deepQSA()` falls back to plain `document.querySelectorAll` with zero overhead.
- **Browser Driver: Shadow DOM stamp clearing** — `invalidate_hints(clear_stamps=True)` now recursively clears `data-flyto-hint` attributes inside shadow roots.
- **Browser Driver: hint extraction error logging** — Silent exception swallow replaced with `logger.debug("Failed to extract element hints", exc_info=True)`.
- **Module registry refactoring** — Extracted `_resolve_module_config()` for cleaner module registration logic.
- **CLI runner refactoring** — Extracted `_show_completion()`, `_save_results()`, `_handle_execution_error()` helpers.
- **Connection validation** — Added VueFlow port alias mapping and `_find_port()` helper for robust frontend↔backend port matching.
- **Removed `headless_manager.py`** — Unused headless browser manager module.
- **Removed `auto_fixer.py`** — Unused audit auto-fixer module.

### Changed
- **Loop Module Consolidation** - Simplified loop module registrations
  - Consolidated from 4 IDs (`core.flow.loop`, `flow.loop`, `loop`, `foreach`) to 2 clear modules
  - `flow.loop` - Repeat N times (params: `times`, `target`)
  - `flow.foreach` - Iterate over list (params: `items`, `steps`)

### Added
- **Execution Environment Safety System** (Security Feature)
  - `ExecutionEnvironment` enum: `LOCAL` | `CLOUD` | `ALL`
  - `LOCAL_ONLY_CATEGORIES` set for automatic environment detection
  - `MODULE_ENVIRONMENT_OVERRIDES` dict for per-module overrides
  - `get_module_environment()` function to determine module environment
  - `is_module_allowed_in_environment()` function for runtime checks
  - **LOCAL_ONLY Categories** (blocked in cloud deployment):
    - `browser.*` - Browser automation (security risk, resource heavy)
    - `page.*` - Browser page operations
    - `scraper.*` - Web scraping operations
    - `element.*` - DOM element operations
    - `file.*` - Local filesystem access
    - `desktop.*`, `app.*` - Desktop automation (future)
  - **Specific LOCAL_ONLY Modules** (in otherwise cloud-safe categories):
    - `database.sqlite_query`, `database.sqlite_execute` - Local SQLite
    - `image.read_local` - Local file image reading
    - `utility.shell_exec`, `utility.run_command` - Shell execution

- **P2 Feature Modules** (9 new modules)
  - `image.resize` - Resize images with multiple algorithms (lanczos, bilinear, bicubic, nearest)
  - `image.compress` - Compress images with quality control and target file size
  - `pdf.generate` - Generate PDF from HTML or text content using reportlab
  - `word.parse` - Parse Word documents (docx) to extract text, tables, images, metadata
  - `email.read` - Read emails via IMAP with folder/filter support
  - `slack.send` - Send Slack messages via incoming webhook with blocks/attachments
  - `webhook.trigger` - Send HTTP requests to webhook endpoints (GET/POST/PUT/PATCH/DELETE)
  - `database.insert` - Insert data into database tables (PostgreSQL, MySQL, SQLite)
  - `database.update` - Update data in database tables with WHERE conditions

- **P1 Feature Modules** (7 new modules)
  - `image.download` - Download images from URL with custom headers
  - `image.convert` - Convert images between formats (PNG, JPEG, WEBP, etc.)
  - `pdf.parse` - Extract text and metadata from PDF files
  - `excel.read` - Read data from Excel files (xlsx, xls)
  - `excel.write` - Write data to Excel files with auto-width columns
  - `email.send` - Send emails via SMTP with attachments support
  - `database.query` - Execute SQL queries on PostgreSQL, MySQL, SQLite

- **Module Tiered Architecture** (ADR-001)
  - `UIVisibility` enum for module UI visibility control (DEFAULT/EXPERT/HIDDEN)
  - `ContextType` enum for module context requirements (browser/page/file/data/api_response)
  - `requires_context` and `provides_context` fields in `@register_module`
  - `ui_visibility`, `ui_label`, `ui_description`, `ui_group`, `ui_icon`, `ui_color` fields
  - `ui_params_schema` for automatic UI form generation in composites
  - `ConnectionValidator` class for workflow validation
  - `can_connect()` and `validate_workflow()` helper functions
  - `DEFAULT_CONTEXT_REQUIREMENTS` and `DEFAULT_CONTEXT_PROVISIONS` for category-based defaults

- **Smart UI Visibility Auto-Detection**
  - `DEFAULT_VISIBILITY_CATEGORIES` mapping in `types.py` for category-based visibility
  - `get_default_visibility(category)` helper function
  - Categories automatically classified:
    - **DEFAULT** (shown to all users): `ai`, `agent`, `notification`, `communication`, `api`, `browser`, `cloud`, `database`, `db`, `productivity`, `payment`, `image`
    - **EXPERT** (advanced users): `string`, `text`, `array`, `object`, `math`, `datetime`, `file`, `element`, `flow`, `data`, `utility`, `meta`, `test`, `atomic`

- **Architecture Documentation**
  - `docs/architecture/ADR_001_MODULE_TIERED_ARCHITECTURE.md`

### Changed
- `@register_module` decorator now supports context-based connection validation
- `@register_module` decorator now auto-detects `ui_visibility` based on category when not specified
- `@register_composite` decorator now supports UI form generation via `ui_params_schema`
- `ModuleLevel` enum extended with COMPOSITE, TEMPLATE, PATTERN levels
- Composite modules now default to `ui_visibility=DEFAULT` (visible to normal users)
- Atomic modules visibility now depends on category (see Smart UI Visibility above)

### Deprecated
- Legacy `label`, `description`, `icon`, `color` fields in favor of `ui_*` prefixed versions

### Important Notes for Module Developers

**UI Visibility Classification:**

When creating new modules, the `ui_visibility` is now auto-detected based on category:

```python
# These categories will show in the main module list (DEFAULT):
# ai, agent, notification, api, browser, cloud, database, productivity, payment, image

@register_module(
    module_id="ai.my_new_model",
    category="ai",
    # ui_visibility auto-detected as DEFAULT (user-facing)
)

# These categories will show in Expert Mode only (EXPERT):
# string, array, object, math, datetime, file, element, flow, data, utility, meta, test

@register_module(
    module_id="string.custom_parser",
    category="string",
    # ui_visibility auto-detected as EXPERT (programming primitive)
)

# To override auto-detection:
@register_module(
    module_id="browser.internal_helper",
    category="browser",
    ui_visibility=UIVisibility.HIDDEN,  # Explicitly hide from UI
)
```

**Visibility Guidelines:**
- **DEFAULT**: Complete, standalone features users can use directly (e.g., "Send Slack Message", "Generate Image with DALL-E")
- **EXPERT**: Low-level operations requiring programming knowledge (e.g., "Split String", "Filter Array", "Click Element")
- **HIDDEN**: Internal system modules not meant for direct user access

---

## [1.5.0] - 2025-12-04

### Added
- **Level 4: Advanced Patterns** - Enterprise-grade execution patterns (`src/core/modules/patterns/`)
  - `BasePattern` base class for all patterns
  - `PatternRegistry` for managing patterns
  - `PatternExecutor` for unified pattern execution
  - `@register_pattern` decorator for easy registration
  - `PatternResult` and `PatternState` for execution tracking

- **Retry Patterns**
  - `pattern.retry.exponential_backoff` - Exponential backoff with jitter
  - `pattern.retry.linear_backoff` - Linear delay increase

- **Parallel Patterns**
  - `pattern.parallel.map` - Parallel execution with concurrency control
  - `pattern.parallel.race` - Execute multiple functions, return first success

- **Resilience Patterns**
  - `pattern.circuit_breaker` - Circuit breaker with CLOSED/OPEN/HALF_OPEN states

- **Rate Limiting Patterns**
  - `pattern.rate_limiter.token_bucket` - Token bucket algorithm
  - `pattern.rate_limiter.sliding_window` - Sliding window algorithm

- **Batch Patterns**
  - `pattern.batch.processor` - Batch processing with chunking
  - `pattern.batch.aggregator` - Aggregate items and flush on threshold

### Changed
- Four-Level Module Architecture now complete:
  - Level 1: Workflow Templates (6 templates)
  - Level 2: Atomic Modules (150+ modules)
  - Level 3: Composite Modules (7 modules)
  - Level 4: Advanced Patterns (9 patterns)

---

## [1.4.0] - 2025-12-04

### Added
- **Four-Level Module Architecture Implementation**
  - Level 3: Composite Modules (7 modules across 4 categories)
  - Level 1: Workflow Templates (6 marketplace-ready templates)

- **Composite Module System** (`src/core/modules/composite/`)
  - `CompositeModule` base class for high-level workflows
  - `CompositeRegistry` for managing composite modules
  - `CompositeExecutor` for executing composite workflows
  - `@register_composite` decorator for easy module registration

- **Browser Composites**
  - `composite.browser.search_and_notify` - Web search with notification
  - `composite.browser.scrape_to_json` - Web scraping to JSON
  - `composite.browser.screenshot_and_save` - Screenshot capture

- **Developer Composites**
  - `composite.developer.github_daily_digest` - GitHub repo monitoring
  - `composite.developer.api_to_notification` - API to notification pipeline

- **Notification Composites**
  - `composite.notification.multi_channel_alert` - Multi-channel alerts
  - `composite.notification.scheduled_report` - Scheduled report delivery

- **Data Composites**
  - `composite.data.csv_to_json` - CSV to JSON conversion
  - `composite.data.json_transform_notify` - JSON transform with notification

- **Level 1 Workflow Templates** (`workflows/templates/`)
  - `google_search_to_slack.yaml` - Google search to Slack
  - `github_repo_monitor.yaml` - GitHub repository monitoring
  - `webpage_screenshot.yaml` - Webpage screenshot capture
  - `multi_channel_alert.yaml` - Multi-channel alert system
  - `web_scraper.yaml` - Web scraping workflow
  - `api_monitor.yaml` - API health monitoring

### Changed
- Updated `composite/__init__.py` to export all composite modules
- Composite modules now support variable resolution with `${params.*}`, `${steps.*}`, `${env.*}`

---

## [1.3.0] - 2025-12-04

### Added
- New constants for AI models: `DEFAULT_ANTHROPIC_MODEL`, `DEFAULT_GEMINI_MODEL`
- Environment variable constants: `GOOGLE_AI_API_KEY`, `SLACK_WEBHOOK_URL`, `DISCORD_WEBHOOK_URL`, `TELEGRAM_BOT_TOKEN`
- Logging to all third-party integration modules

### Changed
- **third_party/ai/agents.py**: Use `OLLAMA_DEFAULT_URL`, `APIEndpoints.DEFAULT_OPENAI_MODEL`, `EnvVars.OPENAI_API_KEY`, `DEFAULT_LLM_MAX_TOKENS`
- **third_party/ai/local_ollama.py**: Use `OLLAMA_DEFAULT_URL` instead of hardcoded URL
- **third_party/ai/openai_integration.py**: Use `APIEndpoints.DEFAULT_OPENAI_MODEL`, `EnvVars.OPENAI_API_KEY`
- **third_party/ai/services.py**: Use centralized API endpoints for Anthropic and Google Gemini
- **third_party/communication/twilio.py**: Use `APIEndpoints.twilio_messages()`, `EnvVars.TWILIO_*`
- **third_party/communication/messaging.py**: Use `EnvVars` for Slack, Discord, Telegram
- **third_party/developer/github.py**: Use `APIEndpoints.github_*()`, `EnvVars.GITHUB_TOKEN`
- **third_party/payment/stripe.py**: Use `APIEndpoints.STRIPE_*`, `EnvVars.STRIPE_API_KEY`
- **third_party/productivity/airtable.py**: Use `APIEndpoints.airtable_table()`, `EnvVars.AIRTABLE_API_KEY`
- **third_party/productivity/tools.py**: Use `APIEndpoints.notion_*()`, `EnvVars.NOTION_API_KEY`
- Moved all inline `import os` statements to file-level imports
- All error messages now use f-strings with constant names for clarity

### Fixed
- Removed duplicate `import json` statements
- Consistent logging pattern across all modules

---

## [1.2.0] - 2025-12-04

### Added
- Browser constants: `DEFAULT_BROWSER_TIMEOUT_MS`, `DEFAULT_VIEWPORT_WIDTH`, `DEFAULT_VIEWPORT_HEIGHT`, `DEFAULT_USER_AGENT`
- LLM constants: `DEFAULT_LLM_MAX_TOKENS`, `OLLAMA_DEFAULT_URL`, `OLLAMA_EMBEDDINGS_ENDPOINT`
- Validation constants: `MIN_DESCRIPTION_LENGTH`, `MAX_DESCRIPTION_LENGTH`, `MAX_TIMEOUT_LIMIT`, `MAX_RETRIES_LIMIT`
- Extended `APIEndpoints` class with Anthropic, Notion, Twilio, OpenAI endpoints
- Extended `EnvVars` class with database and cloud storage variables
- New utility functions: `truncate_string()`, `ensure_list()`, `ensure_dict()`, `safe_execute()`, `log_execution()`

### Changed
- **browser/driver.py**: Use constants instead of hardcoded timeouts and viewport sizes
- **vector/auto_archive.py**: Replace `print()` with `logger.debug()`/`logger.error()`
- **vector/embeddings.py**: Use constants and improved exception handling
- **string/*.py**: Convert absolute imports to relative imports
- **cli/main.py**: Extract constants, use logging, remove `os.system()`

### Fixed
- **utility/not.py**: Implement complete logical negation (was TODO placeholder)
- Security issue: Replaced `os.system('clear')` with ANSI escape sequence

---

## [1.1.0] - 2025-12-04

### Added
- `src/core/constants.py` - Centralized constants management
  - `DEFAULT_MAX_RETRIES`, `DEFAULT_RETRY_DELAY_MS`, `DEFAULT_TIMEOUT_SECONDS`
  - `EXPONENTIAL_BACKOFF_BASE`, `MAX_LOG_RESULT_LENGTH`
  - `WorkflowStatus` enum class
  - `APIEndpoints` class for API URL management
  - `EnvVars` class for environment variable names
  - `ErrorMessages` class for error message templates
- `src/core/utils.py` - Shared utility functions
  - `get_api_key()` - Retrieve API keys from environment
  - `validate_api_key()` - Validate API key presence
  - `validate_required_param()` - Validate required parameters
  - `get_param()` - Get parameter with default value
  - `auto_convert_type()` - Automatic type conversion

### Changed
- **base.py**: Added `get_param()` and `require_param()` methods
- **workflow_engine.py**: Use constants and relative imports
- **registry.py**: Use logger instead of print statements
- All hardcoded magic numbers moved to constants
- Unified relative import paths across modules

---

## [1.0.0] - 2025-12-04

### Added
- Initial release of Flyto2 Core
- YAML workflow automation engine
- 127+ atomic modules across categories:
  - `string.*` - Text manipulation (8 modules)
  - `array.*` - Array operations (10 modules)
  - `object.*` - Object manipulation (5 modules)
  - `file.*` - File system operations (6 modules)
  - `datetime.*` - Date/time operations (4 modules)
  - `math.*` - Mathematical operations (7 modules)
  - `data.*` - Data parsing (5 modules)
  - `browser.*` - Browser automation (9 modules)
  - `utility.*` - Utilities (7 modules)
  - `ai.*` - AI integrations (4 modules)
- CLI interface with interactive mode
- Variable resolution with `${step_id.field}` syntax
- Error handling with retry support
- Internationalization (en, zh, ja)
- Playwright integration for browser automation
- Third-party integrations:
  - AI: OpenAI, Anthropic, Ollama
  - Communication: Twilio, Slack, Discord, Telegram
  - Developer: GitHub, HTTP APIs
  - Payment: Stripe
  - Productivity: Notion, Airtable, Google Sheets

---

## Version History Summary

| Version | Date | Highlights |
|---------|------|------------|
| 2.26.12 | 2026-08-07 | Closed remaining browser file-write and SSRF gaps (download/screenshot/pdf/report/launch/dedup, goto www-toggle), Tar Slip, port.check IPv6 SSRF, regex ReDoS |
| 2.26.11 | 2026-08-03 | Security boundary hardening for filesystems, outbound HTTP, plugins, MCP headers, and Ollama |
| 2.26.10 | 2026-07-23 | 452-module catalog, Tavily search, source-backed docs, deterministic verification |
| 2.26.9 | 2026-07-19 | Registry metadata and PyPI backlink refresh |
| 1.5.0 | 2025-12-04 | Level 4 Advanced Patterns (Enterprise) |
| 1.4.0 | 2025-12-04 | Level 3 Composite Modules + Level 1 Templates |
| 1.3.0 | 2025-12-04 | Third-party module refactoring |
| 1.2.0 | 2025-12-04 | Browser/LLM constants, utility functions |
| 1.1.0 | 2025-12-04 | Constants and utils infrastructure |
| 1.0.0 | 2025-12-04 | Initial release |

---

[Unreleased]: https://github.com/flytohub/flyto-core/compare/v2.26.12...HEAD
[2.26.12]: https://github.com/flytohub/flyto-core/compare/v2.26.11...v2.26.12
[2.26.11]: https://github.com/flytohub/flyto-core/compare/v2.26.10...v2.26.11
[2.26.10]: https://github.com/flytohub/flyto-core/compare/v2.26.9...v2.26.10
[2.26.9]: https://github.com/flytohub/flyto-core/compare/v2.26.8...v2.26.9
[1.5.0]: https://github.com/flytohub/flyto-core/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/flytohub/flyto-core/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/flytohub/flyto-core/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/flytohub/flyto-core/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/flytohub/flyto-core/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/flytohub/flyto-core/releases/tag/v1.0.0
