# Connector packs: a provider's HTTP API declared as data

Owner: claude
Branch: lane/pack-connector (on origin/feat/unified-platform-integration-20261018 at 4c18197)
Date: 2026-10-19

## What changed

This change implements the `connector` section from
`provider-packs-entitlements-and-tenancy.md` §4 and the "Validate" step of
§11. Entitlements, scope, roles and quotas are left to later lanes. Their
declared fields are validated for shape and kept readable on the normalized
operation.

- `src/core/pack/connector.py`: the schema. A `connector` section has
  `base_url`, `auth[]` (`api_token`, `oauth2_client_credentials`,
  `oauth2_authorization_code`, each with a `credential` name), `rate_limit`
  and `operations[]`. An operation has `id`, `method`, `path` with
  `{params}`, `inputs`, `consequence`, `result_scope`, `sensitive`,
  `requires.features`, `consumes` and `paginate`. `CONSEQUENCES` lists the
  five levels. `CONSEQUENCE_CONTRACTS` maps each level to a capability
  contract (safety class plus effect class), so a host can grade the level
  from the contract alone. `operation_rows` produces one module row per
  operation, with id `<namespace>.<operation id>`. A connector pack has
  exactly one namespace.
- `src/core/pack/jsonpath.py`: the strict JSONPath subset (`$`, `.name`,
  `['name']`, `[n]`, `[*]`), parsed at validation time.
- `src/core/pack/manifest.py`: adds the `connector` binding (loadable). A
  connector pack declares no `modules`; they are derived from the
  operations. `PackManifestError` gains `operation`. Refusals include
  `CONSEQUENCE_MISSING`/`_UNKNOWN`, `PATH_PARAM_UNDECLARED`, `INLINE_SECRET`,
  `UNKNOWN_AUTH_KIND`, `INVALID_JSONPATH`, `INVALID_PAGINATION`,
  `CONNECTOR_REQUIRED`, `CONNECTOR_BINDING` and `MODULES_DERIVED`.
- `src/core/pack/connector_runtime.py`: the one runtime that runs every
  operation.
  - It resolves the credential by name from the execution context's
    `secrets` layer. If the credential is absent, it fails with
    `CREDENTIAL_MISSING` before any request.
  - It builds the request. Each path parameter is encoded as one segment.
    Other inputs go in the query or the JSON body.
  - It uses one shared `RateLimiter` (the existing
    `modules/integrations/base/rate_limiter.py`).
  - It paginates with the `http.paginate` shapes.
  - Requests go through the SSRF guard and follow no redirects. A
    Link-header page must stay on the pack's origin.
  - HTTP failures come back as typed `PROVIDER_*` failures with
    `http_status` (and `retry_after_s` on a 429). A failure on any page fails
    the whole call.
- `src/core/pack/host.py`: adds `ConnectorModule`. The binding chooses the
  module class through `_MODULE_CLASSES`, which also gives each class its
  parsed `sensitive` paths.
- `src/core/modules/base.py`, `src/core/engine/redaction.py` and
  `src/core/engine/step_executor/executor.py`: add
  `BaseModule.sensitive_result_paths(result)`, the result-side twin of
  `sensitive_paths`, and `redact_step_result`. The post-execute hooks and
  the trace get a redacted copy. The workflow context and the caller get the
  original.
- `src/core/pack/openapi.py` and `flyto pack import-openapi`
  (`src/cli/pack.py`): turn an OpenAPI 3 document into a draft `connector`
  plus an `unmapped` list. The draft never sets `consequence`.
- `src/core/pack/compatibility.py`: adds a manifest-level feature,
  `pack.connector`, since 2.41.0. `conformance.py` installs a connector pack
  and reports `operations_called` as `not_applicable`, because the offline
  suite never calls the provider.
- `examples/packs/ratings-connector/`: a neutral read-only example with
  three operations: company rating, findings (offset pagination,
  `sensitive: $.items[*].assets`) and portfolio.
  `tests/core/pack/fixtures/connector_recorded.json` holds the recorded-shape
  responses. Only this fixture mentions the provider the operations were
  modeled on. The model was read from
  `/Users/chester/Projects/bitsight-mcp-server/src/api.ts` and
  `src/tools.ts` (read-only).
- Docs: `docs/specs/PACK_MANIFEST_SPEC.md` (new `connector` section),
  `docs/specs/ADAPTER_COMPATIBILITY_MATRIX.md`, `CHANGELOG.md` (2.41.0),
  `STATE.md`, `DECISIONS.md`, `docs/README.md`, regenerated
  `docs/reference/`, and inventory tokens.

## Why

A provider should be able to ship its API as signed data and get typed,
consequence-graded, credential-safe modules, with no code per provider in
core or Cloud. The consequence is a decision about effect, so nothing infers
it from the HTTP method. The importer leaves it unset, and validation
refuses the draft until a person sets it.

Rejected alternatives:

- Generating module files per operation.
- A second credential resolver.
- `${secrets.NAME}` interpolation. Core has no such resolver, and the
  context `secrets` layer is the one modules already read.
- Reusing `http.paginate`'s loop functions. They never inspect a status
  code, so a 500 would become an empty success.

## Verified

- Failing first, on the base code with the tests added:
  - `test_connector_runtime.py`: 23 failed, 0 passed (the binding was
    unknown).
  - `test_connector_manifest.py` and `test_connector_openapi.py`: collection
    errors (`core.pack.connector`/`openapi` absent).
  - `test_step_result_redaction.py` with the engine changes stashed: 3/3
    failed. One was a behavioural failure: the address reached the
    post-execute hook unredacted.
- After the change:
  - New tests: 78 passed (manifest 45, runtime 23, OpenAPI 7, result
    redaction 3).
  - `tests/core/pack` together with the redaction suites: 246 passed.
  - Broader run, `tests/core tests/cli test_module_sensitivity_contract
    test_browser_fill_form -m "not browser and not e2e"`: 2604 passed, 13
    deselected.
- `scripts/generate_reference.py` regenerated the reference.
  `check_documentation.py` PASS (188 Markdown files, 243 local links).
  `check_brand_identity.py` PASS (1282 files). `lint-project-memory.sh` PASS.
- Ruff: the new and changed pack, CLI and test files are clean. In
  `executor.py` and `base.py`, the 12 findings that remain were there before
  this change; their count is unchanged.
- `flyto-index verify --strict`: 20 pass, 1 fail. The failure is
  `weak_scan_taint`: the pre-existing `mcp_post -> run_recipe ->
  load_recipe` path_traversal finding recorded in earlier handoffs.
- `flyto-index task validate`: failed for environmental reasons. It runs
  ruff across the whole repo, which has pre-existing example findings, and
  runs a pytest without pytest-cov.

## Not verified

- No real provider API was called. No real credential was used.
- Cloud does not yet put credentials into the execution context's `secrets`
  for connector modules. The Cloud secretRef hook resolves params, not this
  layer.
- `requires`, `consumes`, `scope` and `result_scope` are not enforced, and
  AI-egress withholding of `sensitive` is not implemented. These belong to
  later lanes.
- CI, release and a full suite run have not been done.

## Follow-ups

- Cloud: populate `context["secrets"]` by credential name from the
  credential store for connector modules, and treat the derived contract as
  the level source.
- Entitlement, scope and quota lanes: read `connector.operations[]`
  `requires`, `consumes`, `inputs.*.scope` and `result_scope` from the
  normalized manifest.
- Recorded-response development mode (§11 "Develop").
