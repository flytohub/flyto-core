# Product Verification 90-Point Evidence Gate

Date: 2026-06-23
Status: Active

## Context

Flyto2 Product Verification needs a deterministic release gate that reflects
replayable evidence, not a vanity health score. `warroom.report` now includes
the `warroom.evidence_pack.v1` gate fields consumed by flyto-engine and
flyto-code.

## Contract

- `gate_verdict`: `pass` only when score is at least 90 and there are no
  blockers.
- `gate_score`: 0-100 release summary.
- `score_breakdown`: reachable route coverage, intent/state/API graph,
  replay reliability, scope/authz safety, live operation loop, and public
  GEO/AI crawler gate.
- `artifact_completeness`: required screenshot, DOM snapshot, and network log.
- `gate_blockers`: fail-closed reasons such as P0/P1 findings, weak coverage,
  weak replay, missing artifacts, or dry-run evidence.

## Verification

- `/opt/homebrew/bin/python3.11 -m pytest --no-cov tests/modules/test_warroom_modules.py tests/test_verification_service.py -q`
- Result: 22 passed, 1 warning.

## Follow-Up

Live production readiness still requires non-dry-run staging or production
evidence, plus the external public AI crawler/GEO gate.
