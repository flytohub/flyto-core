# Automated Product Testing Model Evidence

Date: 2026-06-23
Status: Active

## Context

The Warroom product surface produced replay evidence packs, but UI and CI consumers had to
interpret raw `site_graph`, `scenarios`, `run`, and artifact JSON to understand
whether the automation-testing feature was strong.

## Change

Core now exposes the deterministic verification primitives through generic
module IDs:

- `verification.discover`
- `verification.generate_scenarios`
- `verification.run`
- `verification.report`

The existing `warroom.*` module IDs remain compatibility aliases for old
recipes and evidence. Do not add new product-specific behavior to those aliases.
New product workflows should be composed by flyto-engine using `verification.*`.

`warroom.report` now emits `automation_test_model` with schema
`flyto.core.deterministic_verification.v1`. The legacy schema reference remains
`warroom.automation_test_model.v1` for compatibility.

Core does not own Flyto2 product naming. Engine-owned artifacts may attach
`product_contract=flyto2.automated_product_testing.v1`,
`product_surface=warroom`, and `capability=automated_product_testing` when this
runtime is used inside the Warroom Automated Product Testing feature.

The model summarizes:

- observed / reachable / expected coverage and blocked paths
- intent graph count and top intents
- scenario synthesis contract and replayable step count
- replay pass/fail/reliability and step results
- ghost API type A/B/C counts and samples
- business invariant / state contradiction count
- RBAC matrix status, roles, tenant pairs, fail-closed state, and violations
- event stream status, transport, endpoint, expected events, observed events,
  and fail-closed state
- scheduler loop status, scanner/job id, authority, dispatch source, durable
  job status, and run/failure counts
- screenshot / DOM snapshot / network log evidence-chain completeness
- gate score, verdict, and blockers
- deterministic engine mode:
  `llm_required=false`, `llm_role=optional_evidence_reviewer`, and
  `gate_authority=deterministic_evidence_gate`

This remains deterministic. No LLM is involved in producing facts.

## Verification

- `/opt/homebrew/bin/python3.11 -m pytest --no-cov tests/modules/test_warroom_modules.py tests/test_verification_service.py -q`

## Follow-Up

- Expand discovery to feed `expected_paths` from router/sitemap/menu sources.
- Feed real multi-role RBAC matrix results from engine into `site_graph`.
- Feed observed scheduler runs and long-lived SSE delivery observations into
  evidence packs when those are collected outside the runner.
- Add multi-intent scenario synthesis beyond page-level replay.
