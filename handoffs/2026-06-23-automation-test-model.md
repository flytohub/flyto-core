# Automation Test Model Evidence

Date: 2026-06-23
Status: Active

## Context

The Warroom replay loop produced evidence packs, but UI and CI consumers had to
interpret raw `site_graph`, `scenarios`, `run`, and artifact JSON to understand
whether the automation-testing feature was strong.

## Change

`warroom.report` now emits `automation_test_model` with schema
`warroom.automation_test_model.v1`.

The model summarizes:

- observed / reachable / expected coverage and blocked paths
- intent graph count and top intents
- scenario synthesis contract and replayable step count
- replay pass/fail/reliability and step results
- ghost API type A/B/C counts and samples
- business invariant / state contradiction count
- RBAC matrix status, roles, tenant pairs, fail-closed state, and violations
- screenshot / DOM snapshot / network log evidence-chain completeness
- gate score, verdict, and blockers

This remains deterministic. No LLM is involved in producing facts.

## Verification

- `/opt/homebrew/bin/python3.11 -m pytest --no-cov tests/modules/test_warroom_modules.py tests/test_verification_service.py -q`

## Follow-Up

- Expand discovery to feed `expected_paths` from router/sitemap/menu sources.
- Feed real multi-role RBAC matrix results from engine into `site_graph`.
- Add multi-intent scenario synthesis beyond page-level replay.
