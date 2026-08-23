# Runtime and module catalog convergence

Owner: codex
Branch: codex/convergence-closure
Date: 2026-08-24

## What changed

- Browser launch falls back from missing bundled Chromium to supported system
  Chrome and Edge channels without overriding an explicit channel.
- Legacy module results with `ok: false` become workflow failures and therefore
  enter the existing retry, error-edge, and `on_error` contract.
- Registry metadata derives a stable label key when a module omitted one.
- `http.response_assert.body_matches` keeps its regex editor without becoming a
  required input.

## Why

Installed browser templates, legacy integrations, translated canvases, and
status-only HTTP assertions all failed at product boundaries even though the
underlying capability existed. These changes make those boundaries truthful
without widening permissions or changing explicit caller choices.

## Verified

- Focused Core coverage: 171 tests passed.
- Full non-browser/non-E2E suite: 3,041 passed, 11 skipped, 273 deselected;
  63.36% coverage passed the 60% gate.
- A real browser launch with an empty Playwright cache used installed Chrome.
- New and modified-line Ruff coverage is clean.
- Generated catalog and source-reference documentation was refreshed.
- Repository and strict Indexer checks are recorded in the final commit checks
  for this branch.

## Not verified

No production worker deployment or third-party website automation was run.
Explicit Edge fallback was unit-tested but not exercised on an Edge-installed
host.

## Follow-ups

Deploy through the normal release pipeline and repeat official template
runtime acceptance against the packaged Desktop artifact.
