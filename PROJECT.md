# Flyto2 Core Project

## Mission

Flyto2 turns AI work into verified, replayable procedures. Its proof line is:
"AI said it finished. Flyto2 shows the proof."

## Product Role

Flyto2 has three independently usable packages. `flyto-ai` understands, routes,
and governs new work and providers. `flyto-blueprint` stores, learns from, and
scores reusable procedures but never executes them. Layer-three `flyto-core`
validates schemas, executes and replays deterministically, and emits evidence.
Core works standalone; it does not require AI or Blueprint for those duties.

For Flyto2 Warroom, core is the deterministic verification engine: discover the
site graph, generate replay YAML, run module-level assertions, and produce
evidence packs before any optional LLM review.

The current registry inventory is 468 modules across 85 generated catalog
categories, with 41 maintained built-in recipes exposed through the CLI.

## Success Criteria

- Maintained recipe bundles stay runnable and tested.
- Browser tests assert real DOM or visual state, not only HTTP success.
- Workflow assets do not contain credentials or hidden environment assumptions.
- Enterprise and airgap validation can be expressed as local recipes where
  possible.
- Warroom checks produce replayable YAML and redacted evidence without relying
  on LLM output for pass/fail decisions.
- Public documentation and package metadata stay aligned with the generated
  module catalog and recipe inventory.
- Every maintained Python file and declaration is discoverable through the
  generated source reference, while narrative docs explain each owned source
  area, public runtime surface, security boundary, and operator workflow.
- Optional capabilities declare installable extras and fail with an actionable
  package-level installation command when their dependency is absent.

## Owned Surfaces

- Python package `core`, workflow engine, registry, policy, trace, evidence,
  replay, state, metering, browser control, and provider adapters.
- CLI entry points `flyto`, `flyto-serve`, and `flyto-verification`.
- MCP stdio, authenticated MCP HTTP, Execution API, and verification service.
- Packaged recipes, workflow fixtures, plugin protocol, package metadata,
  generated module/source references, and release verification automation.

## Non-Goals

- Intent routing or provider governance owned by `flyto-ai`.
- Procedure learning or scoring owned by `flyto-blueprint`.
- Hosted account, billing, team, or marketplace business logic owned by Cloud.
- Product UI behavior owned by Console, App, Admin, or the public websites.
- Treating optional provider availability or LLM output as deterministic proof.
