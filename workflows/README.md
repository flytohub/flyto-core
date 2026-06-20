# Workflows

`workflows/` contains checked-in workflow assets used as regression fixtures,
operator demos, and product-loop validation. These workflows are part of the
closed-loop contract between flyto-code, flyto-engine, and flyto-core.

## Expectations

- YAML should be runnable by `flyto recipe` or the recipe bundle tests.
- Credentials must be passed as runtime inputs or environment variables.
- Security workflows should make scope and consent explicit before active tests.
- Browser validation workflows should assert rendered state, not only HTTP 200s.

## Product Loops

Keep workflow names aligned with the platform loop registry where possible:
footprint to pentest, darkweb to footprint seed, compliance export, score
refresh, operations health, and AI branch guard flows.
