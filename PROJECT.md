# Flyto Core Project

## Mission

`flyto-core` provides automation modules, recipes, browser control, and workflow
validation used to prove Flyto product loops end to end.

## Product Role

Core turns product expectations into repeatable checks: browser smoke, API
pipelines, YAML recipes, module execution, and validation workflows. It is the
practical bridge between code changes and observable product behavior.

For Flyto2 Warroom, core is the deterministic verification engine: discover the
site graph, generate replay YAML, run module-level assertions, and produce
evidence packs before any optional LLM review.

## Success Criteria

- Maintained recipe bundles stay runnable and tested.
- Browser tests assert real DOM or visual state, not only HTTP success.
- Workflow assets do not contain credentials or hidden environment assumptions.
- Enterprise and airgap validation can be expressed as local recipes where
  possible.
- Warroom checks produce replayable YAML and redacted evidence without relying
  on LLM output for pass/fail decisions.
