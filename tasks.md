# Tasks

## Open

- Add multi-route BFS crawler for arbitrary sites.
- Connect Warroom evidence packs into Flyto2 Cloud UI.
- Add enterprise airgap smoke recipes for no-egress browser/API checks.
- Add recipe fixtures for capability states and report/export flows.
- Keep maintained recipe bundle tests aligned with product-loop contracts.

## Watch

- Recipes that depend on local credentials or machine-specific paths.
- Browser checks that pass without asserting real page state.
- Module parameter drift that is not reflected in examples or tests.

## Done

- Added the 90-point Product Verification evidence gate to `warroom.report`
  with focused tests for pass and blocked paths.
- Split `warroom.run` module success from `replay_ok` product success so failed
  deterministic replay evidence remains available to `warroom.report`.
- Added a dedicated `flyto-verification` Docker image boundary for full-stack
  Product Verification compose/staging smoke.
- Added operator-controlled SSRF dev-port allowlisting so Product Verification
  can replay local/staging browser targets without turning off the SSRF guard.
- Added deterministic graph/scenario/report modules in `flyto-core`.
- Made e2e/scenario test modules execute real module steps.
- Bootstrapped project memory skeleton and lint gate.
