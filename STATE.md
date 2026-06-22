# Flyto Core State

## Current State

- Warroom deterministic verification v1 exists in `flyto-core`: it can build a
  redacted site graph, generate replay scenarios, execute module assertions, and
  emit JSON/Markdown evidence packs. LLM review is disabled by default and
  advisory only.
- Project memory structure has been bootstrapped for repeatable workflow and
  validation handoffs.
- The repository already contains workflow assets and CI for maintained recipe
  bundle tests.
- Core is positioned as the validation layer for frontend, engine, admin, and
  enterprise deployment smoke loops.

## Release Blockers

- No repo-specific blocker is recorded from this docs bootstrap.
- Cross-repo production readiness still depends on remote CI stability and on
  adding stronger enterprise airgap smoke recipes.

## Verification Matrix

| Gate | Command | Scope |
| --- | --- | --- |
| Project memory | `bash scripts/lint-project-memory.sh` | Required docs, handoffs, architecture headings, secret-like material |
| Recipe lint | `ruff check src/core/recipe_bundles.py tests/core/test_recipe_bundles.py` | Maintained recipe bundle lint |
| Focused tests | `pytest tests/core/test_recipe_bundles.py -o addopts="" -q` | Recipe bundle behavior |
| Build | `python -m build` | Package integrity |
| Indexer | `flyto-index verify . --json` | Repository closure |
