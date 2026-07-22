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

- Added the source-backed documentation contract, technical whitepaper,
  feature/API/configuration/security/operations/testing guides, generated
  declaration/module/CLI/HTTP/environment references, ownership manifest, and
  deterministic drift/link checks.
- Added a Flyto2 brand and approved-mailbox policy gate for public repository
  content.
- Declared `crypto`, `dns`, and `ai` package extras and aligned contributor
  dependencies with the tested capability set.
- Protected workflow status and evidence reads with the Execution API bearer
  token and added regression coverage.
- Expanded CI from one recipe test to documentation, brand, audited lint,
  non-browser tests, npm audit, package/Twine, and strict Indexer gates.

- Added generic `verification.*` module IDs for deterministic verification
  primitives and kept `warroom.*` as compatibility aliases only; engine-owned
  workflows should compose `verification.*`.
- Renamed the emitted deterministic testing model to the core-owned
  `flyto.core.deterministic_verification.v1` while retaining
  `warroom.automation_test_model.v1` as the legacy schema reference.
- Kept Flyto2 product naming out of core defaults; engine artifacts may attach
  a product contract such as `flyto2.automated_product_testing.v1`.
- Added explicit non-LLM execution policy to automation evidence:
  deterministic evidence is the fact source and gate authority; LLM is only an
  optional evidence reviewer.
- Added event-stream and scheduler-loop summaries to
  `automation_test_model.v1` so Product Verification evidence can distinguish
  callback/SSE contracts and durable scheduler contracts from raw replay facts.
- Added `automation_test_model.v1` to Warroom evidence packs so UI/CI can read
  coverage, scenario synthesis, replay, ghost API, invariant, RBAC, and
  evidence-chain results without interpreting raw JSON.
- Added the 90-point Product Verification evidence gate to `warroom.report`
  with focused tests for pass and blocked paths.
- Split `warroom.run` module success from `replay_ok` product success so failed
  deterministic replay evidence remains available to `warroom.report`.
- Made generated Warroom DOM assertions hydration-aware so SPA pages are not
  scored as blank before body text settles.
- Added a dedicated `flyto-verification` Docker image boundary for full-stack
  Product Verification compose/staging smoke.
- Added operator-controlled SSRF dev-port allowlisting so Product Verification
  can replay local/staging browser targets without turning off the SSRF guard.
- Added deterministic graph/scenario/report modules in `flyto-core`.
- Made e2e/scenario test modules execute real module steps.
- Bootstrapped project memory skeleton and lint gate.
