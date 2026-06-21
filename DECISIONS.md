# Decisions

## 2026-06-21 - Project memory is release-controlled

Decision: keep root project memory files, workflow docs, and handoff registry in
the repository and validate them in CI.

Reason: flyto-core is used to prove product loops. Its own workflow expectations
must be durable, visible, and checked.

## 2026-06-21 - Recipes are product contracts

Decision: maintained recipes should represent executable contracts for product
flows and release smoke, not only demos.

Reason: Flyto needs closed-loop verification from UI and API behavior back to
backend state, evidence, and release readiness.
