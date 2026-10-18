# WoT TD 1.1 admission bound to the official W3C schema (J06)

Owner: claude
Branch: claude/j06-interop (from feat/iot-ecosystem-adapters-20261013, PR #138; 0 commits behind origin/main)
Date: 2026-10-18

## What changed

- `examples/integrations/flyto_ecosystems/schemas/w3c-wot-td-1.1.schema.json`:
  the official TD 1.1 JSON Schema from https://www.w3.org/2022/wot/td-schema/v1.1,
  byte-for-byte (SHA-256 fd44f319...02e0f1), with `NOTICE` (W3C Software and
  Document License) and package-data entries in `pyproject.toml`.
- `flyto_ecosystems/wot.py`: `import_thing_description` and
  `export_thing_description` validate against that schema
  (`_require_td11`); error text names the JSON path and the failed rule, never
  the vendor value. Hand-written type checks the schema now covers were
  removed; Flyto2 policy checks stay (transport allow list, no credentials or
  fragments in form URLs, bounds, declared `security` names, no duplicate
  capability ids). A `writeOnly` property is refused: a property offer is an
  observation and that value cannot be read.
- `jsonschema>=4.18,<5` is now a dependency of the optional package only.
- `tests/test_wot_td11_conformance.py` (21 cases): schema digest pin; a
  15-case corpus asserting admission is never wider than the schema (the
  schema verdict for each case is asserted too, so the corpus cannot drift);
  forward mapping of the Recommendation's Example 1; `@type` annotations
  cannot select a Flyto2 capability; reverse mapping (export validates and
  re-imports to the same offers); export refuses host forms with an `op`
  from another affordance kind.
- `tests/test_wot.py` fixture made schema-valid (it had affordances without
  forms).
- README, CHANGELOG, STATE, ROADMAP.

## Why

The adapter admitted TDs the W3C schema refuses (affordances without forms,
forms without `href`, misordered `@context`, security definitions without
`scheme`, property forms with `invokeaction`). Re-implementing the schema by
hand is what let it drift; the official schema is now the one definition.

## Verified

- Failing first: before the `wot.py` change 11 of 21 conformance tests
  failed (9 corpus cases, write-only refusal, export op check).
- After: `examples/integrations/tests` 74 passed; with
  `tests/core/test_capability_host.py` and `tests/core/test_capability_contract*.py`
  466 passed (Python 3.12 venv).
- `ruff check examples/integrations scripts/generate_reference.py`: pass.
- Wheel built with `--no-deps --no-build-isolation`; it contains the schema
  and NOTICE and declares `jsonschema`.
- `scripts/generate_reference.py`, `check_documentation.py`,
  `check_brand_identity.py`, `lint-project-memory.sh`: pass.
- `flyto-index verify --strict`: 20 pass, 1 fail -- the pre-existing
  `weak_scan_taint/path_traversal` flow `src/core/api/routes/mcp.py` ->
  `src/cli/recipe.py::load_recipe` (fingerprint 66be6a7449f057065a6429e5),
  in files this branch does not touch. Not a green strict gate.

## Not verified

- CI (Actions billing-locked); Python 3.11 not run locally this time.
- No real WoT device, Home Assistant, MQTT broker or physical equipment.
- OPC UA: no adapter exists in any Flyto2 repository, so no mapping tests
  were written. ROS 2 mapping tests live in flyto-robotics on the same branch
  name (`tests/test_ros2_semantic_mapping.py`).

## Follow-ups

- PR #138 needs this branch merged into it (or rebased onto it) and review.
