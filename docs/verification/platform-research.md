# Product Verification platform decisions

Research date: 2026-09-06. Candidate source: `fb42fcd4ce0f54f47708a1559ec475725fa0083d`.
The installed validation environment uses Python 3.12, asyncpg 0.31.0 and
Playwright Python 1.62.0. These are observed installed versions, not a claim
that all other versions or protocols are supported.

| User problem | Direct source and version | Adopted contract / acceptance | Limits and rejected alternative |
| --- | --- | --- | --- |
| A screenshot or completed request can hide a failed business condition | [Playwright Python assertions](https://playwright.dev/python/docs/test-assertions), current docs read 2026-09-06 | Required, typed machine assertions; poll Web observations until the assertion deadline; missing fields fail | No AI pass authority; no fixed sleep as success evidence |
| Retrying hides the first failure or contaminates browser state | [Playwright retries](https://playwright.dev/docs/test-retries), [browser-context implementation guide](https://github.com/microsoft/playwright/blob/main/docs/src/browser-contexts.md) | Fresh context for each Web step, unique run/case/attempt identity, retain every attempt; retries require explicit retry-safe declaration | The Python library is not the Playwright Test runner. We implement lifecycle receipts and do not claim its reporter semantics |
| Reports lose evidence from the original failure | [Playwright issue 34588](https://github.com/microsoft/playwright/issues/34588), discussion read 2026-09-06 | Keep initial failure and later attempts separately; compare runs by version and case IDs | Issue is a requirement lead, not proof of a shipped feature. Raw traces can contain secrets; do not automatically publish them |
| Database assertions accidentally change customer data | [PostgreSQL 18 SET TRANSACTION](https://www.postgresql.org/docs/18/sql-set-transaction.html), [asyncpg 0.31.0 transaction source](https://github.com/MagicStack/asyncpg/blob/v0.31.0/asyncpg/transaction.py) | Operator-approved parameterized query IDs, readonly transaction, bounded result rows and deadlines; write rejection must be demonstrated against PostgreSQL | READ ONLY is not a universal side-effect sandbox. Reject arbitrary SQL and use a restricted database principal; SQLite, MySQL and arbitrary stored functions are not supported |
| Cancellation leaks a connection or hangs a run | [asyncpg API](https://magicstack.github.io/asyncpg/current/api/index.html), [issue 547](https://github.com/MagicStack/asyncpg/issues/547), [asyncpg releases](https://github.com/MagicStack/asyncpg/releases) | Close connections in finally with a bounded close timeout; test cancellation and timeout against the installed version | The issue describes 0.20.1 and does not prove a defect in 0.31.0. No shared connection pool in this first adapter |
| Runner logs cannot be connected to a report | [OpenTelemetry CI/CD conventions](https://opentelemetry.io/docs/specs/semconv/cicd/) (Release Candidate when read) | Stable run, suite version, environment version, runner and evidence digest in every report | Keep the Flyto2 result schema versioned. Do not adopt an unstable external enum as our public contract or add a telemetry backend to this module |

## UX consequences

The module navigation follows suites, runs, environments/connections, runners,
and reports. Adapter selection belongs in the case editor. A failed assertion
shows its source step, expected value and redacted observation. A rerun retains
its parent reference and never overwrites the previous evidence. A transport
success only means the runner accepted the work.

## Initial capability envelope

- HTTP/HTTPS JSON observations, with guarded DNS resolution and no redirects.
- PostgreSQL queries selected from operator-provisioned connection bindings.
  The endpoint is a literal IP address and port; the credential DSN must match
  both and cannot override them through query options. Non-isolated connections
  require TLS certificate verification against the approved IP. Hostname-only
  database targets are blocked until a resolver can preserve both address
  pinning and certificate hostname verification. Private targets require the
  trusted host's explicit isolated binding; metadata addresses remain denied.
- Chromium Web observations against isolated IP-bound fixtures. DNS-named Web
  environments require a production egress proxy before they can be admitted.
- Cross-layer flows compose those same adapters; no additional task system.
- API writes require an isolated connection and the attempt namespace in the
  request. Cleanup uses the same restriction.

Every capability above remains a candidate until its acceptance evidence is
recorded in the handoff. A library's documented support is not Flyto2 support.

## Runner packaging and lifecycle

Install `flyto-core[verification]` for the HTTP, PostgreSQL and Chromium service.
The service reports each installed adapter separately; missing dependencies or
Chromium produce degraded readiness. Four active tasks and 1,000 retained
records bound the process registry. Terminal records expire after an hour.
The Engine persists terminal evidence independently and converts an unavailable
execution into a bounded error/timeout; a process restart is never a pass.
