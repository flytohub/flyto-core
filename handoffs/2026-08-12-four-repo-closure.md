# Four-repository capability closure

- Date: 2026-08-12
- Owner: Codex
- Status: source and repository gates pass; clean-tree Indexer receipt pending commit

## Scope

This closes the flyto-core side of the shared capability chain used by
flyto-ai and flyto-blueprint: deterministic capability manifests, generic
extension management, transactional registry refresh, runtime plugin policy,
and process lifecycle safety. No individual extension or product is hardcoded.

## Independent audit finding

Routing aliases were evaluated after policy. A legacy request such as
`database.scan` could resolve to `flyto-official/database` while policy queried
`database`, found no manifest, and omitted the actual plugin's declared
permissions. Routing now resolves first and policy uses the actual handler id
before execution. Legacy-first routes also retain the plugin id so a later
fallback is covered by the same gate.

## Evidence

- All configured lint, compile, memory and generated-documentation checks pass.
- Extension management: 81 passed.
- Runtime lifecycle: 45 passed.
- Registry/plugin contract: 78 passed.
- Full non-browser/e2e suite: 2785 passed, 11 skipped, 273 deselected;
  coverage 63.20% (floor 60%).
- Catalog/reference generation: 468 modules / 85 categories; 955 source files /
  5,631 declarations.
- Strict Indexer pre-commit: 18 pass, 0 warn, 1 hygiene failure solely because
  the tracked `.flyto/coding.yaml` control file is dirty. Re-run on the clean
  committed tree before marking this handoff complete.
