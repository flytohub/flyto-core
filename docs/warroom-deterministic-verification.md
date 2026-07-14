# Warroom Deterministic Verification

Flyto2 Warroom verification should behave like an instrument, not a prompt.
The first pass is deterministic: capture observable page structure, actions,
API edges, state hints, screenshots, console errors, and replayable YAML. LLM
review is optional and advisory only.

## Pipeline

1. `warroom.discover` builds a redacted site graph from a browser page or
   supplied page observations.
2. `warroom.generate_scenarios` turns the graph into replayable Flyto2 YAML.
3. `warroom.run` replays scenarios through the real module runner.
4. `warroom.report` creates JSON or Markdown evidence packs.
5. `warroom.llm_review` prepares redacted evidence only when a human enables it.

## Evidence Signals

- `exploration_coverage`: discovered and exercised pages/actions/API edges.
- `replay_reliability`: stable replayed steps over total replayed steps.
- `state_model_confidence`: observed page state coverage.
- `api_ui_consistency`: browser-observed API status consistency.
- `business_logic_confidence`: combined deterministic confidence signal.
- `visual_integrity`: blank/error/overflow penalty signal.

P0/P1 findings fail deterministically. LLM output cannot pass a failing gate
without supporting deterministic evidence.

## Safety Contract

- Credentials, cookies, tokens, headers, URL query strings, and response bodies
  must not be stored in YAML or committed reports.
- Browser screenshots and DOM snapshots are evidence, not secret stores.
- New site support starts with generated YAML, then humans may refine scenarios.
- Clean output means no qualifying signal was observed, not that the site is
  universally safe.

## V1 Scope

V1 dogfoods Flyto2 first. General arbitrary-site discovery comes after the
site graph, scenario generation, replay, report, and redaction contracts are
stable.
