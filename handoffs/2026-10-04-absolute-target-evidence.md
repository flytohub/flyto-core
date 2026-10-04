# Absolute-target contract evidence (2.38.0)

Owner: claude
Branch: claude/contract-distance-to
Date: 2026-10-04

## What changed

- `src/core/capability_contract.py`: two measure ops, `distance_to` (1..3
  fields; `expect: {"arguments": {field: parameter}}`) and `angle_to` (one
  field; `expect: {"argument": parameter[, "optional": true]}`), listed in
  `MEASURE_OPS` and the new `ABSOLUTE_OPS`. They compare the last declared
  phase with a target from the call's arguments. They require `after` (not
  `before`) and `tolerance.relative` 0. Optional `measure.frame`: every
  observed phase must carry that `frame`, else unusable. An omitted optional
  `angle_to` target is a usable verdict with nothing measured. Contracts that
  use neither normalize and hash as on 2.37.
- `docs/CAPABILITY_CONTRACT.md`: schema rows, an "Absolute targets" section,
  the arithmetic, the missing-data order (frame is rule 3), a worked example of
  a reported arrival 0.63 short, and the lift example now proves its floor.
- `tests/core/vectors/capability_contract_absolute_targets.json`: 20 judge
  vectors (spec, arguments, observations, full verdict). Flyto2 Cloud's port
  must reproduce them exactly.
- `tests/core/test_capability_contract_absolute_targets.py`: validation rules,
  the vectors, and the generic capability host judging an arrival from
  `map_pose` (0.63 m short -> not verified; 0.1 m -> verified).
- Version 2.38.0 (pyproject, server.json, SECURITY*.md, CHANGELOG).

## Why

A `motion.navigate` that Nav2 reported SUCCEEDED while the robot stopped 0.63 m
short was accepted as arrived: v1 measures could only compare phases, so no
contract could state "it ended at the asked place". The arrival belongs in the
provider's contract, judged by the host, not in host code.

## Verified

- `pytest tests/core/test_capability_contract_absolute_targets.py` 55 passed;
  the file fails to collect against the pre-change module.
- Contract suites (`test_capability_contract*.py`, `test_capability_host.py`)
  pass; full non-browser suite: see the PR.
- `scripts/check_documentation.py`, `check_brand_identity.py`,
  `check_release_drift.py`, `lint-project-memory.sh`, ruff on touched files.

## Not verified

- No live run against a robot or the twin from Core.

## Follow-ups

- flyto-modules-robotics declares navigate's arrival with these ops (1.2.0).
- flyto-cloud ports the ops into `contract_verification.py` with these vectors.
- Tag and release 2.38.0.
