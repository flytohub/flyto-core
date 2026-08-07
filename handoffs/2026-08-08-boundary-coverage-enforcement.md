# Boundary Coverage Enforcement

Owner: claude
Branch: `main`

## Baseline

Every arbitrary file read/write and SSRF advisory published against this project
is the same defect: a module takes a caller-supplied path or network target to a
sink without calling the guard. The guards were already centralized in
`core/utils.py` and already correct. What was missing was any check that they
were *called*, so each fix wave closed the modules that had been reported and
left the ones that had not — GHSA-p64w-hgfm-824v says outright that the prior
waves missed `browser.download`.

Two registry-wide audits were run to size the real gap rather than react to the
next report:

- Filesystem: 88 modules declare a path-shaped parameter; 30 reached a sink
  without the guard.
- Outbound network: 57 modules declare a URL/host-shaped parameter; 34 reached
  the network without a guard.

Classification separated genuine gaps from name collisions (JSONPath
expressions, URL path segments, cookie `Path` attributes, remote-host paths,
placeholder implementations).

## Changes

### Filesystem boundary

Confined the caller-supplied path in `testing.visual.compare` (`diff_path` plus
the `expected`/`actual` read paths — this module declares no
`required_permissions`, so the write was unauthenticated), `data.xml.parse`
(the sibling GHSA-wc94-386q-5478 missed), `browser.upload`, `aws.s3.upload` and
`ssh.sftp_upload` (host files shipped to a caller-chosen destination),
`ssh.sftp_download` (the SFTP counterpart of GHSA-hmq9-xw4w-7ppc), `file.delete`
(arbitrary deletion), `file.exists` (filesystem oracle), `git.clone`,
`git.commit`, `git.diff`, `llm.code_fix` (its `'..'` substring check never
blocked an absolute path), `verify.spec`, and — as hardening, since each already
holds broader permissions — `docker.build`, `process.start`,
`sandbox.execute_shell`. Also guarded two public SDK exports with no in-tree
caller: `registry.catalog.export_to_json_file` and
`KnowledgeManager.export_entries`.

### Outbound boundary

Added `enforce_outbound_host` (raw TCP) and `enforce_outbound_service_url`
(`redis://`, `ws://`, proxy URLs) to `core/utils.py`. `validate_url_ssrf` only
understands http(s), so modules taking a bare host or a non-HTTP endpoint had no
guard available to call — the gap was structural, not careless.

Routed through them: `verify.run`, `verify.capture` and `verify.visual_diff`
(raw Playwright `page.goto`, bypassing `BrowserDriver._guard_navigation`; in
`visual_diff`'s case a bare `async_playwright()` browser with no egress guard in
any deployment mode), `browser.connect` (`ws_endpoint` — CDP is remote code
execution by design), `browser.launch` (`proxy` — the egress guard inspects
request URLs, not where the proxy points), `git.clone` (`url` — the existing
validator bounded the transport but never the destination), `cache.*`,
`queue.*`, `db.mysql.query`, `db.redis.get/set`, `notification.email.send`
(which also carries SMTP credentials to whatever answers), `ssh.exec`,
`ssh.sftp_upload`, `ssh.sftp_download`, `network.ping`, `network.port_scan`,
`network.traceroute`, `port.wait`, `browser.emulate`.

Promoted `port.check`'s host resolver to `core.utils.resolve_guard_ip`. It held
the only correct implementation in the codebase — IP literals range-checked
directly so IPv6 transition forms cannot skip the check, fail-closed on
resolution failure — and that is what GHSA-v7q9-pr72-5fmv was about.

Guards that must run before an optional-dependency import (`asyncssh`) were
placed at function entry so they fail closed whether or not the dependency is
installed.

### Enforcement

`tests/core/test_write_sink_coverage.py` and
`tests/core/test_outbound_guard_coverage.py` walk the registry and fail the
build on any unaccounted parameter. The outbound test is MRO-aware because
guards are legitimately inherited (`LLMClientMixin` holds the `ollama_url`
guard for `agent.chain` / `agent.autonomous`); a same-file scan would report
those as unguarded and train readers to ignore the test. To make that possible,
`register_module` now preserves `__module__` and `__wrapped_func__` on
function-style module wrappers instead of reporting `decorators.py`.

Exemptions are verified, not trusted: a module excused as "makes no request"
fails once its source contains a connection call, and one excused for
validating locally fails once the named validator disappears.

## Verification

- Filesystem boundary: 88 path-param modules = 71 guarded + 17 documented + 0
  unaccounted.
- Outbound boundary: 57 network-param modules = 46 guarded + 11 documented + 0
  unaccounted.
- `tests/core` + `tests/modules`: 1,833 passed, 5 skipped.
- `tests/runtime` + `tests/enterprise` + `tests/cli`: 192 passed.
- Both coverage tests were verified to fail when a guard is removed
  (`file.delete`, `ssh.exec`), so they are not passing vacuously.
- `scripts/lint-project-memory.sh`, `scripts/check_documentation.py`,
  `scripts/check_brand_identity.py`: all pass; `docs/reference/` regenerated.

Not run: `tests/modules/test_real_sites.py` (live network), browser E2E, package
build/Twine, npm audit, and the strict full-scan indexer verification from the
release closure in `docs/TESTING.md`. This is not a release.

## Follow-ups

- Two breaking changes need a release note: paths outside `FLYTO_SANDBOX_DIR`
  (default: process working directory) are refused, and connections to
  private/link-local hosts require `FLYTO_ALLOWED_HOSTS` or
  `FLYTO_ALLOW_PRIVATE_NETWORK=true`. Loopback is unaffected, so self-hosted
  Redis/MySQL/SMTP on `localhost` continues to work.
- Whether any of these warrant public advisories is a maintainer decision. The
  strongest candidates are `testing.visual.compare` (unauthenticated arbitrary
  file write, no declared permissions) and `file.delete` (arbitrary deletion);
  the rest read naturally as one hardening entry.
