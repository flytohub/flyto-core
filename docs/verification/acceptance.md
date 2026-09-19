# Local acceptance evidence

Candidate validation on 2026-09-06:

- Existing verification service tests: 9 passed, including the regression that
  workflow completion without an evidence pack must be blocked.
- New bounded suite runtime contracts: 13 passed.
- Real controlled adapter integration: 1 passed. Two separate runs issued an
  HTTP POST into an isolated PostgreSQL fixture, queried the persisted state in
  a read-only transaction, opened Chromium and asserted the rendered state,
  then deleted only the attempt-namespaced row through the fixture API.
- Both runs preserved an unrelated sentinel row. A provisioned DELETE query
  was rejected by PostgreSQL read-only mode and left that row intact.

Command:

```sh
FLYTO_PV_FIXTURE_PG_URL=<disposable-postgres-dsn> python -m pytest \
  tests/verification/test_local_adapters.py -o addopts='' -q
```

The fixture report is written under pytest's per-test temporary directory and
includes run IDs, version digests, assertions, observations, teardown and timing
receipts.

## Cross-layer browser acceptance

Controlled local acceptance also exercised Code through the real Engine router,
encrypted test credential storage, the dedicated authenticated Core service,
PostgreSQL, and Chromium. Browser actions started a real suite, downloaded its
accepted report, and reran it with a distinct run ID and retained parent ID.
Environment and suite edits saved immutable version 2 without exposing stored
credentials. Desktop, tablet, and phone viewports were inspected.

An intentionally incorrect database assertion remained a failed result and
still cleaned up its attempt data. Browser cancellation acknowledged the
request, interrupted a slow HTTP step, completed cleanup, and persisted a
cancelled result. Every check preserved the unrelated sentinel row.

The full non-browser Core suite passed 4,708 tests with 220 skips and 443
browser-marker exclusions; coverage was 65.66% against the required 60%.
All 32 focused verification tests, Ruff, the strict indexer gate (19 checks),
and task validation passed. Base dependency auditing found no known
vulnerabilities. The canonical Python 3.11 lock regeneration resolves lxml
6.1.3, the version already present in the full-suite test environment.

These are local source and integration results. They do not claim a merged
release, a published package, staging readiness, or production deployment.

## Dedicated Cloud Run deployment

The service image is built from an explicit Core commit with
`Dockerfile.verification`, including the distribution license files. The
verification extra supplies HTTP, PostgreSQL and Chromium dependencies. Deploy
it separately from the legacy `flyto-runner`; `/suite-capabilities` must report
the adapters from this image before Engine is configured to use it.

Cloud Run remains private. A dedicated runtime service account receives access
only to its application secret, and the Engine service identity receives the
Invoker role on this service. Engine sends its Google identity token plus
`X-Internal-Key`. Configure the same Secret Manager version through
`FLYTO_VERIFICATION_SECRET` on both services; never write its value into a
manifest or release report.

Set the service maximum to one instance and keep CPU available between requests:
active suite state is process-local. Engine polls for progress and retains
terminal evidence. A restart remains an observable error/timeout, not a success.
Production deployment does not enable the isolated-fixture development flags
or execute any customer suite by itself.
