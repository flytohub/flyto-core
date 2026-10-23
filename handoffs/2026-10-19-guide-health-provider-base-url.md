# The guide's standalone health check runs against a reachable provider

Owner: claude
Branch: lane/guide-health (on the core integration tip cb72749)
Date: 2026-10-19

## What changed

After 01ef7b5, `flyto pack health` reads the entitlements probe from the
provider. The build-a-pack guide ran health against the manifest's
`base_url` (`https://api.provider.example`). No provider is reachable there,
so the guide test failed with `PROVIDER_ENTITLEMENT_UNREADABLE`, and the
probe made a real outbound attempt in the process. There was no supported
way to point a standalone run at a local provider, so this change adds one.

- `src/core/pack/standalone.py`:
  - `admit_provider_base_url` admits a loopback host, or a host already in
    `FLYTO_ALLOWED_HOSTS`. Anything else is refused with
    `PROVIDER_BASE_URL_REFUSED`, before install.
  - The connector scheme rules apply: https, or http to loopback only
    (`INVALID_BASE_URL`). A URL with userinfo or a token is refused with
    `INLINE_SECRET`.
  - `load_standalone(..., provider_base_url=)` and `health(...)` apply it
    after install, through `ConnectorTransport.point_at`.
  - A loopback origin is opened in the SSRF guard for that one host and port
    while the pack is open, and closed in `StandalonePack.close()`.
  - `health` reports `provider_base_url`, and `run` logs the override.
- `src/core/pack/connector_runtime.py`:
  - `ConnectorTransport.point_at` moves `base_url` to the new URL, moves
    token and authorize URLs to the same origin with their paths kept, and
    clears the token and entitlement caches.
  - `loopback_origin_allowed` is the one scoped SSRF opening. It moved here
    from `recorded.py`, which now uses it.
- `src/core/pack/recorded.py`:
  - New `serve_fixtures(pack_dir, port=)`: the same recorded fake as
    `pack test`, standing alone.
  - Customer identities are computed from a transport built from the
    manifest, so nothing is installed.
- `src/cli/pack.py`:
  - `--provider-base-url` on `run` and `health`.
  - New `flyto pack serve-fixtures DIR [--port N]`.
- `src/core/pack/doctor.py` adds a `PROVIDER_BASE_URL_REFUSED` row.
- Guide step 5 now runs, in order:
  - `serve-fixtures items-pack --port 8799 &`
  - `export` of the fixture customer's test credential
  - `health ... --provider-base-url http://127.0.0.1:8799`, which still
    promises exit 0
  - `run ...` with the same flag
- `tests/core/pack/test_build_a_pack_guide.py`:
  - Runs a `&` line as a background process that must print that it is
    serving, and stops it when the page is done.
  - Asserts the standalone server lists both tools, which proves the probe
    was read from the stand-in.
- New `tests/core/pack/test_provider_base_url.py` (12 tests).
- Docs: the spec (a local-testing section and the CLI lines), `docs/CLI.md`,
  `CHANGELOG.md`, `DECISIONS.md`, the regenerated reference and the
  inventory tokens.

## Why

A provider has to be able to run its built zip before any real account
exists, and the guide's commands must run as written without the network.
`handoffs/2026-10-19-portable-packs-and-bundles.md` rejected a run-time
`--base-url` because it changes where the credential goes without a new
signed manifest. This narrows that override instead of reopening it: loopback
or allow-listed only, scoped to the run, and reported.

Rejected:

- An environment variable. It persists, and a later run would silently send
  the credential elsewhere.
- Rewriting the manifest, which breaks its signature.
- Changing the guide's expected exit code to 1.

## Verified

- Failing first (`scratchpad/round7/guide-health-evidence/failing-first.txt`):
  the guide test failed on cb72749 (health exited 1,
  `PROVIDER_ENTITLEMENT_UNREADABLE`). `test_provider_base_url.py` failed at
  collection (`serve_fixtures` absent).
- Mutation check: with the flag dropped from the guide's health line, the
  guide test fails again.
- New tests: 12 passed; guide test: 4 passed; pack and CLI suites: 667
  passed.
- Full non-browser suite: 5975 passed, 0 failed, 174 skipped, 508
  deselected, 4 warnings (asyncio unraisable-exception warnings from tests
  this change does not touch).
- `check_documentation.py` PASS (196 Markdown files, 249 local links);
  `check_brand_identity.py` PASS (1306 files); `lint-project-memory.sh`
  PASS; ruff on every changed file: all checks passed.
- `flyto-index verify --strict`: Status PASS, 21 pass, 0 warn, 0 fail.

## Not verified

- No real provider or network was used.
- One mutation check (dropping the flag from the guide's health line, then
  restoring it) let the probe attempt the manifest's
  `https://api.provider.example`. That is one outbound DNS attempt for a
  reserved `.example` name. The same attempt happened in every guide run on
  cb72749 before this fix.
- The guide's port is fixed at 8799. A run fails clearly, but does fail, if
  that port is already taken.
- An allow-listed non-loopback override was only validated, never called.
- Windows, CI and release were not run.
