# Testing And Release Gates

## Test Layers

| Layer | Scope | Typical command |
|---|---|---|
| Unit/contract | Modules, engine, validation, policy, redaction | `.venv/bin/python -m pytest -m 'not browser and not e2e'` |
| API security | Bearer auth, MCP mediation, bind policy, evidence access | `.venv/bin/python -m pytest tests/core/api -o addopts=''` |
| Recipe bundles | Packaged deterministic verification recipes | `.venv/bin/python -m pytest tests/core/test_recipe_bundles.py -o addopts='' -q` |
| Browser | Real Playwright browser behavior | `.venv/bin/python -m pytest -m browser` |
| E2E | Cross-component workflows and optional external services | `.venv/bin/python -m pytest -m e2e` |
| Documentation | Generated references, catalog, ownership, links | `.venv/bin/python scripts/check_documentation.py` |
| Brand | Flyto2 naming and approved public mailboxes | `.venv/bin/python scripts/check_brand_identity.py` |
| Dependency contract | Base lock, compatibility installers, vulnerability audit | `PYTHON=.venv/bin/python bash scripts/lock-deps.sh && git diff --exit-code -- requirements.lock && .venv/bin/python -m pip_audit -r requirements.lock` |
| Package | Wheel and source distribution | `.venv/bin/python -m build` |
| Repository | Scan, security, docs, policy, CI closure | `flyto-index verify . --full-scan --strict --json` |

## Normal Local Closure

```bash
.venv/bin/python scripts/check_documentation.py
.venv/bin/python scripts/check_brand_identity.py
PYTHON=.venv/bin/python bash scripts/lock-deps.sh
git diff --exit-code -- requirements.lock
.venv/bin/python -m pip_audit -r requirements.lock
ruff check scripts/generate_catalog.py scripts/generate_reference.py \
  scripts/check_documentation.py scripts/check_brand_identity.py \
  src/cli/__init__.py src/cli/config.py src/core/constants.py \
  src/core/api/routes/workflows.py \
  src/core/modules/atomic/crypto/encrypt.py \
  src/core/modules/atomic/crypto/decrypt.py \
  src/core/modules/atomic/crypto/jwt_create.py \
  src/core/modules/atomic/crypto/jwt_verify.py \
  src/core/modules/atomic/dns/lookup.py \
  src/core/capability_manifest.py src/core/api/routes/modules.py \
  src/core/modules/registry/core.py src/core/mcp_handler.py \
  tests/conftest.py tests/test_documentation_generators.py \
  tests/test_version_identity.py tests/core/api/test_routes.py \
  tests/core/test_capability_manifest.py tests/core/api/test_capability_surface.py \
  tests/core/api/test_mcp_transport.py tests/core/test_mcp_real.py \
  tests/core/test_plugin_policy_scope.py
ruff check src/core/runtime/invoke.py src/core/runtime/routing.py \
  src/core/runtime/exceptions.py tests/core/test_runtime_policy_gate.py \
  tests/core/runtime/test_routing.py tests/core/runtime/test_invoke.py
ruff check src/core/runtime/manager.py tests/runtime/test_manager.py
ruff check src/core/plugin/loader.py src/core/api/routes/extensions.py \
  src/core/api/routes/__init__.py src/core/api/server.py \
  tests/core/api/test_extensions.py
.venv/bin/python -m pytest -m 'not browser and not e2e'
.venv/bin/python -m build
npm audit --audit-level=high
flyto-index verify . --full-scan --strict --json
```

Run browser and E2E suites when the required browsers, services, or credentials
exist. A skipped environment-backed suite is not proof of that integration.

## Coverage

`pyproject.toml` configures a 60% line-coverage floor for the maintained control
kernel. The project also uses catalog/schema checks for the broad module corpus.
Coverage percentage is not a substitute for auth, SSRF, path-sandbox, replay,
redaction, and policy assertions.

## AI Demo Collection

`tests/test_agent_loop.py`, `tests/test_real_agent.py`, and
`tests/test_smart_agent.py` are historical executable demos. They contain no
pytest test functions and require the optional OpenAI SDK and credentials.
`tests/conftest.py` excludes them from normal collection; credential-backed
manual execution remains explicit.

## Generated Documentation

Run:

```bash
.venv/bin/python scripts/generate_catalog.py
.venv/bin/python scripts/generate_reference.py
```

The check variants compare exact output and fail on drift. Generated references
must be committed with the source change that altered them.

## Test Data Rules

- Use registered `@flyto2.com` aliases in public examples.
- Never commit working credentials or reachable private endpoints.
- Private-network exceptions must be fixture-scoped.
- A test that depends on a provider must skip with a clear reason when its
  optional dependency or credential is absent.
- Security regression tests must assert that the protected handler is never
  reached, not only that an error body was returned later.
