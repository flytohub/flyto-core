# Flyto2 Core State

## Current State

- Warroom deterministic verification v1 exists in `flyto-core`: it can build a
  redacted site graph, generate replay scenarios, execute module assertions, and
  emit JSON/Markdown evidence packs. LLM review is disabled by default and
  advisory only.
- The generated catalog currently exposes 452 modules across 84 categories, and
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
- Source-backed documentation now covers 932 maintained Python files, 5,383
  declarations, 467 literal module registrations, all CLI/HTTP/environment
  surfaces, and all maintained recipe/workflow assets. CI rejects drift,
  missing ownership, broken local links, stale naming, and mailbox violations.
- Workflow status and evidence reads now require bearer authentication.
- `crypto`, `dns`, and `ai` extras express tested optional dependency
  boundaries; the development extra supports the complete offline suite.

## Release Blockers

- No repo-specific release blocker is recorded from this audit.
- Cross-repo production readiness still depends on remote CI stability and on
  adding stronger enterprise airgap smoke recipes.
- Browser/E2E integrations that require external services, browsers, or
  credentials remain environment-backed evidence and are not inferred from the
  offline suite.

## Verification Matrix

| Gate | Command | Scope |
| --- | --- | --- |
| Project memory | `bash scripts/lint-project-memory.sh` | Required docs, handoffs, architecture headings, secret-like material |
| Documentation | `python scripts/check_documentation.py` | Generated drift, ownership, catalog, local links |
| Brand | `python scripts/check_brand_identity.py` | Flyto2 naming and approved public aliases |
| Dependencies | `PYTHON=.venv/bin/python bash scripts/lock-deps.sh` plus `pip_audit` | Canonical base lock and vulnerability scan |
| Audited lint | CI Ruff command in `.github/workflows/ci.yml` | Changed maintenance, API security, dependency-boundary surfaces |
| Offline tests | `python -m pytest -m 'not browser and not e2e'` | Full offline suite plus 60% control-kernel coverage gate |
| JS runtime | `npm ci --ignore-scripts && npm run audit` | Locked jsdom runtime and dependency audit |
| Build | `python -m build && twine check dist/*` | Wheel/sdist integrity and metadata rendering |
| Indexer | `flyto-index verify . --full-scan --strict --json` | Repository closure and 90-point docs budget |

## Last Verification

Verified locally on 2026-07-22:

- project memory, documentation, brand, generated catalog/reference, and
  audited Ruff checks passed;
- 2,227 tests passed, 24 skipped, 101 deselected, with 63.27% coverage;
- npm audit reported 0 vulnerabilities;
- pip-audit reported no known vulnerabilities in the base runtime lock;
- wheel and source distribution built, and Twine validated both artifacts;
- Flyto2 Indexer strict full scan passed 18/18 checks with 0 warnings/failures,
  docs score 92, README score 100, 0 secret findings, and 0 high-risk taint
  flows.
