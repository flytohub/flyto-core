# Warroom deterministic verification

Date: 2026-06-23 Asia/Taipei

Summary:

- Added deterministic Warroom modules in `flyto-core`:
  - `warroom.discover`
  - `warroom.generate_scenarios`
  - `warroom.run`
  - `warroom.report`
  - `warroom.llm_review`
- Added a shared testing runner so `testing.e2e.run_steps` and
  `testing.scenario.run` execute real module steps and assertions instead of
  returning placeholder success.
- Added `warroom-deterministic-audit` recipe and documentation.

Product intent:

- Warroom is not prompt-first. It captures page structure, action/API graph,
  state hints, deterministic scores, replay YAML, and evidence reports before
  any optional LLM review.
- LLM review is disabled by default and advisory only.

Verification:

```text
python -m pytest tests/modules/test_warroom_modules.py -q --no-cov
ruff check src/core/modules/atomic/warroom src/core/modules/atomic/testing/runner.py src/core/modules/atomic/testing/e2e.py src/core/modules/atomic/testing/scenario.py tests/modules/test_warroom_modules.py
python scripts/lint_modules.py --category warroom --mode ci
```

Residual risk:

- Browser-driven multi-route BFS is not complete in this first cut. V1 provides
  the deterministic graph, generation, replay, report, and redaction contracts
  so a crawler can be added without changing evidence shape.
