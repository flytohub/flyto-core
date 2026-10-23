# Connector pre-check: entitlements read from the provider, quota, data scope

Owner: claude
Branch: lane/entitlements (on origin/feat/unified-platform-integration-20261018 at c7c60b6)
Date: 2026-10-19

## What changed

This is step 3 of `provider-packs-entitlements-and-tenancy.md` §15 (Cloud
repo). It enforces the fields the connector lane validated and kept.

- `src/core/pack/connector.py` adds `validate_provider_sections`. It
  validates two top-level sections a connector pack may declare:
  - `entitlements`: `probe`, which must be an ungated observe operation;
    `features.keys` and `features.path`; `meters` (name to JSONPath);
    `max_age_s` (default 900, range 1..86,400).
  - `scopes`: `[{key, resolve?}]`.

  It binds both to the operations. Any feature, meter or dimension an
  operation names must be declared. `result_scope` is now normalized to
  `{dimension, path}`; the text form is shorthand only when the pack
  declares exactly one dimension. The new refusals are
  `ENTITLEMENTS_REQUIRED`, `FEATURE_UNDECLARED`, `METER_UNDECLARED`,
  `SCOPE_UNDECLARED`, `RESULT_SCOPE_DIMENSION_REQUIRED`, `PROBE_UNKNOWN`,
  `PROBE_NOT_OBSERVE`, `RESOLVE_UNKNOWN`, `INVALID_ENTITLEMENTS` and
  `INVALID_SCOPES`. `manifest.py` admits the two top-level keys only on the
  connector binding (`CONNECTOR_BINDING` otherwise). It adds them to the
  normalized manifest only when they are declared, so packs without them
  normalize and sign exactly as before.
- `src/core/pack/connector_gate.py` (new) is the one gate. `admit()` runs
  for every operation before its request, in this order:
  1. Features: `FEATURE_NOT_ENTITLED`, with `missing_features`.
  2. Scope: `SCOPE_GRANT_MISSING`, then `OUT_OF_SCOPE` for each scoped
     input.
  3. Quota: `QUOTA_EXHAUSTED`, with `meter`, `remaining` and `amount`.

  The module also holds:
  - `read_answer()` (probe body to `EntitlementAnswer`; any other shape is
    `PROVIDER_ENTITLEMENT_UNREADABLE`);
  - `EntitlementCache` (per credential, keyed by a digest of the credential
    name and value);
  - `filter_result()` (items under the last `[*]`; out-of-grant items are
    dropped and counted; an item without exactly one scalar scope value
    gives `RESULT_SCOPE_UNREADABLE`; a non-list result outside the grant
    gives `OUT_OF_SCOPE`, never an empty result);
  - `ScopeGrants`: the host-made, validated, immutable grant carrier. A
    plain mapping under `scope_grants` is no grant.
- `src/core/pack/connector_runtime.py`: `ConnectorTransport.call(...,
  scope_grants)` runs the pre-check and then the call, then filters the
  result.
  - Cache rules: a read may use the cache. A write, a quota-consuming call,
    and any call on a credential after a provider HTTP error read the probe
    again. A failed read drops the cached answer and refuses.
  - For quota use, the probe is read again after the call. The result's
    `metadata.precheck.meter` holds `{meter, amount, before, after,
    matches}`.
  - Pre-checked results carry `metadata.precheck`.
  - HTTP 402 is `PROVIDER_QUOTA_REFUSED`.
  - `effective_module_ids(secrets)` lists the entitled operations. A
    cached answer may serve it.
  - The credential lookup is refactored into `_headers` (headers plus
    cache key).
- `src/core/pack/host.py`: `ConnectorModule` passes only `secrets` and
  `scope_grants` from the context. New `effective_module_ids(pack_id,
  secrets)`. The transport gets the pack's `entitlements`.
- `src/core/pack/compatibility.py` adds the feature `pack.entitlements`,
  since 2.41.0. Matrix row in `docs/specs/ADAPTER_COMPATIBILITY_MATRIX.md`.
- `examples/packs/ratings-connector/flyto-pack.json` gains:
  - the probe operation `account.entitlements`;
  - `requires: [ratings]` on the three reads;
  - `portfolio.add` (external_write, `requires: [monitoring]`, consumes
    one `monitoring_slots`);
  - `entitlements` and `scopes: [company]`.

  The README is updated. `tests/core/pack/fixtures/connector_recorded.json`
  gains two customers (`ratings_only`, and `ratings_and_monitoring` with
  2 slots).
- Tests:
  - New: `tests/core/pack/test_connector_entitlements.py`, against a
    loopback fake provider with two credentials.
  - `test_connector_runtime.py` installs the example `ungated()`, so it
    keeps testing the transport alone.
  - `test_connector_manifest.py` follows the new normalized shape.
- Docs: `docs/specs/PACK_MANIFEST_SPEC.md` (new "pre-check" section, with
  "the provider is the source of truth"), `CHANGELOG.md` (2.41.0),
  `STATE.md`, `DECISIONS.md`, the regenerated `docs/reference/`, and the
  inventory tokens.
  - The `spm` product name is removed from the `connector.py` docstring and
    from the spec example.

## Why

The provider owns the facts about its own product. Flyto2 reads them; it
does not copy them, and it does not decide them. The pre-check hides
operations and stops calls early. It never authorizes provider access: a
provider refusal is final, it comes back typed, and it is never retried.
Scope grants only narrow. Only the stored, named credential goes upstream.

Rejected alternatives:
- A per-surface check.
- Falling back to the last good answer.
- Treating a missing grant as `"*"`.
- Skipping result items that lack a scope value.
- Reading grants from a plain context mapping. Step results land in the
  context by step id, and Cloud copies a caller's variables into it, so a
  plain mapping could be forged.

## Verified

- Failing first, on c7c60b6 with only the example, fixture and test changed:
  - `test_connector_entitlements.py` failed at collection
    (`effective_module_ids` absent).
  - With the import made lazy, 57 failed and 1 passed. The pass was
    `UNKNOWN_KEY`, which the base also refuses.
  - The forged plain-mapping grant test failed behaviourally on the first
    commit (the call ran, `ok: True`), 2/2, before `ScopeGrants`.
- The no-token-passthrough tests pass on the base source when the pack is
  installed ungated (24 passed with a scratch test). They are regression
  guards, not a fix: the runtime already sent only the named credential.
- After the change:
  - `tests/core/pack`: 244 passed. Of these, 59 are in
    `test_connector_entitlements.py`.
  - `tests/core tests/cli -m "not browser and not e2e"`: 2639 passed, 2
    deselected. This was run after the first commit, before the
    `ScopeGrants` commit. The pack suite (244) was run after it.
- `flyto pack verify --allow-unsigned` and `flyto pack conform --static-only`
  on the example: conformant.
- `generate_reference.py` regenerated. `check_documentation.py` PASS (189
  Markdown files, 243 local links). `check_brand_identity.py` PASS (1284
  files). `lint-project-memory.sh` PASS. Ruff is clean on every changed
  pack and test file.
- `flyto-index verify --strict`: Status PASS, 21 pass, 0 warn, 0 fail.
- `flyto-index task validate`: overall fail, for environmental reasons only.
  The repo-wide ruff hits pre-existing `examples/agent_demo/planner.py`
  I001, and the indexer's pytest lacks pytest-cov
  (`unrecognized arguments: --cov=core`).

## Not verified

- No real provider, credential or API was used. Only the fake server.
- `scopes[].resolve` is validated (it must name an operation) but not used:
  grant values come from the caller.
- AI-egress withholding of `sensitive` paths, roles and partner delegation
  are not built.
- Concurrency: two simultaneous calls on one credential may both read the
  probe. There is no lock, and both answers are fresh.
- CI, release and a full suite run have not been done.

## Follow-ups

- Cloud must record the acting member's grant on the execution, and supply
  provider credentials by name into `secrets` (see the Cloud handoff of the
  same date).
- A provider-pushed revocation (open question 4 of the design).
- A meter mismatch (`matches: false`) is only recorded. It is not yet
  raised as a finding on the pack.
