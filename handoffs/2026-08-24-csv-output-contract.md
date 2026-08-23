# JSON-to-CSV output and input-error contract

Owner: codex
Branch: codex/runtime-catalog-truth
Date: 2026-08-24

## What changed

- `data.json_to_csv` resolves its relative default output inside the configured
  sandbox and keeps explicit absolute paths behind the existing sandbox guard.
- Missing, malformed, empty, and non-object inputs raise typed parameter errors.
- Base module resilience does not retry deterministic validation, type, value,
  or range errors.
- The real Juice Shop E2E fixture now confirms the service identity instead of
  treating any process listening on port 3000 as the vulnerable test target.

## Why

The previous `/tmp/output.csv` default was rejected by the runtime's own
filesystem sandbox, and missing input leaked a retried Python `KeyError` instead
of telling an author what to fix.

## Verified

- Focused Core runtime coverage passed 109 tests.
- Full non-browser/non-E2E coverage passed 3,101 tests with 11 expected skips
  and 273 marker deselections; total measured coverage was 63.50% against the
  60% gate.
- The Juice Shop E2E test correctly skipped when Flyto2 Cloud, rather than Juice
  Shop, occupied local port 3000.
- Ruff passed on the changed Core source and regression test.
- Strict Indexer verification passed 19 of 19 checks.
- Source distribution and wheel built successfully; Twine accepted every
  artifact currently in `dist/`.
- A real Cloud lightweight workflow reported the typed missing-parameter error
  on its failing step while retaining the completed first step's output.

## Not verified

No packaged Desktop artifact or deployed worker was exercised in this change.
The Indexer task runner used a separate environment without pytest-cov and
could not execute its embedded pytest command; the repository's own venv ran
the full suite and the separate strict Indexer gate passed.

## Follow-ups

Repeat official-template acceptance after the next packaged Core release.
