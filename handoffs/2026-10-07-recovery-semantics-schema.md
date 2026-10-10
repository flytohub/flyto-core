# Recovery semantics in the capability contract (2.39.0)

Owner: claude
Branch: claude/recovery-declaration
Date: 2026-10-07

## What changed

- `src/core/capability_contract.py`: the `recovery` block admits `on`
  (`RECOVERY_STOP_FAMILIES`: obstruction / no_passage / stopped_short),
  `alternatives` (1..8 roles, order kept), `preserves` (`destination` /
  `target`), `resource_scope` (`same_resource` only) and `fills` (1..8 roles).
  Roles match `RECOVERY_ROLE_PATTERN` (identifier grammar, at most 96
  characters). `capabilities` is optional; the block must declare at least one
  of `capabilities`, `alternatives` or `fills`. Coherence: `on` and
  `alternatives` together, `alternatives` requires `resource_scope`,
  `preserves` / `resource_scope` without `alternatives` are refused. Unknown
  keys (including bounds such as `max_rounds`) are refused. Keys appear in the
  normalized block only when declared.
- `RECOVERY_FIELDS` is the feature test (`"fills" in RECOVERY_FIELDS`).
- `docs/CAPABILITY_CONTRACT.md`: "Recovery semantics (2.39.0)" section; the
  `recovery` row says `capabilities` is optional from 2.39.0.
- Tests: `tests/core/test_capability_contract_recovery_semantics.py` and
  `tests/core/vectors/capability_contract_recovery_semantics.json`; one
  existing refusal row now expects the new message.
- Version 2.39.0 (pyproject, server.json, SECURITY*.md, CHANGELOG, STATE).

## Why

Flyto2 Cloud (`claude/recovery-semantics`) reads a way round from roles in the
contract instead of a table keyed by capability names. The closed 2.38 schema
required `capabilities` and refused every semantic key, so no pack could
register the declaration. Core checks shape only; trusting a declaration is
the host's review.

## Compatibility

Blocks valid on 2.38 validate, normalize and hash unchanged (test pins the
normalized form by hand). Every contract registered by this repository's
modules and the pack example re-validates to itself. A provider that also
loads on 2.38 must feature-detect `RECOVERY_FIELDS` and drop the semantic keys
there.

## Verified / not verified

See the PR description for the commands run and their results.
