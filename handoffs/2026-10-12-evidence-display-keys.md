# Evidence display keys in the capability contract (2.40.0)

Owner: claude
Branch: claude/evidence-display-keys
Date: 2026-10-12

## What changed

- `src/core/capability_contract.py`: an evidence spec admits three optional
  display keys, each validated by its own check in one declarative table
  (`_EVIDENCE_DISPLAY_CHECKS`) and kept verbatim in the normalized spec:
  - `label`: a dict of 1..8 language tags (`EVIDENCE_LABEL_PATTERN`,
    `^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$`, e.g. `en`, `zh-TW`, `und`) to
    printable text of 1..64 characters;
  - `unit`: printable text of 0..16 characters (`""` for counts and states);
  - `channel`: a telemetry channel id (`TELEMETRY_CHANNEL_PATTERN`,
    `^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$`).
  The bounds match flyto-cloud's presentation `localized` schema and its
  live-channels `telemetry_channel` pattern. `judge` never reads them. Every
  other unknown evidence key (e.g. `display_name`, `precision`) is still
  refused.
- Published names: `EVIDENCE_DISPLAY_FIELDS` (feature test:
  `"label" in EVIDENCE_DISPLAY_FIELDS`), `EVIDENCE_LABEL_PATTERN`,
  `EVIDENCE_LABEL_LANGS_MAX`, `EVIDENCE_LABEL_MAX`, `EVIDENCE_UNIT_MAX`,
  `TELEMETRY_CHANNEL_PATTERN`.
- `docs/CAPABILITY_CONTRACT.md`: evidence table rows and the normalized form.
- Version 2.40.0 (pyproject, server.json, SECURITY*.md, CHANGELOG, STATE);
  regenerated `docs/reference/` and inventory counts.

## Why

Device packs (flyto-modules-automotive `d1b7f19`) state what a reading is on
the evidence spec so flyto-cloud's scoped HMI (PR #543,
`services/hmi/readings.py`) can label checks in the provider's words. 2.39.0
refused the keys as unknown, so the pack's feature detection
(`core_evidence_keys`, which probes `validate_evidence` per key) dropped them
and Cloud's check rows carried a unit only. Precision stays on the telemetry
channel, not on the spec.

## Verified

- Failing first: on b7663dec, `validate_evidence` refused each of `label`,
  `unit`, `channel` with "evidence has unknown keys"; the new test module could
  not import the published names.
- `pytest tests/core/test_capability_contract*.py test_capability_host.py
  test_capability_manifest.py test_capability_invoke_module.py tests/core/pack
  tests/test_documentation_generators.py` (worktree `src` on PYTHONPATH): 533
  passed.
- ruff on the touched files; `check_documentation.py`,
  `check_brand_identity.py`, `lint-project-memory.sh`: pass.

## Not verified

- Locally skipped (the machine is the live demo host, CPU-capped): the full
  non-browser suite and strict full-scan Indexer verify; CI runs both.
  `tests/test_version_identity.py` fails locally only because the shared venv
  has the 2.39.0 metadata installed.
- No live Cloud HMI check against a pack carrying the keys.

## Follow-ups

- flyto-cloud bumps its flyto-core pin to the merge commit (requirements*.txt,
  requirements-ce.lock, module_catalog.json, test.yml, mcp-closed-loop.yml) so
  the execution host admits the keys.
