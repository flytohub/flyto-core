# Flyto2 Core State

## Current State

- Warroom deterministic verification v1 exists in `flyto-core`: it can build a
  redacted site graph, generate replay scenarios, execute module assertions, and
  emit JSON/Markdown evidence packs. LLM review is disabled by default and
  advisory only.
- The generated catalog currently exposes 451 modules across 84 categories, and
  the bundled recipe inventory contains 41 recipes.
- Project memory structure has been bootstrapped for repeatable workflow and
  validation handoffs.
- The repository already contains workflow assets and CI for maintained recipe
  bundle tests.
- Core is positioned as the validation layer for frontend, engine, admin, and
  enterprise deployment smoke loops.
- Python runtime code and tests use one canonical package identity, `core`.
  The suite rejects `src.core` imports because duplicate module identities can
  split auth, registry, and security state inside one process.
- Security-sensitive test exceptions are fixture-scoped. Collection-time
  private-network and verification-auth overrides are rejected by contract.
- The browser-contract JavaScript runtime is declared and locked in
  `package.json` / `package-lock.json`; `npm audit` is part of local closure.
- The 60% line coverage gate measures the maintained orchestration and
  security-control kernel. Pluggable module implementations and product
  overlays remain covered by catalog, contract, and integration suites.

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
| Full tests | `python3.11 -m pytest -q` | Full suite plus 60% control-kernel coverage gate |
| JS runtime | `npm ci --ignore-scripts && npm run audit` | Locked jsdom runtime and dependency audit |
| Build | `python -m build` | Package integrity |
| Indexer | `flyto-index verify . --json` | Repository closure |
