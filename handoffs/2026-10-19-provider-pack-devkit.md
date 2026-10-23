# Provider pack developer kit: init, consequence, doctor, test

Owner: claude
Branch: lane/pack-devkit (on the core integration tip f75f3a2)
Date: 2026-10-19

## What changed

A provider (a security-rating vendor, an issue tracker, a robot vendor) can
now build, test and ship its own connector pack, and so its own MCP server,
with flyto-core alone.

- `src/core/pack/scaffold.py` (new) has two parts.
  - `init_pack` writes `flyto-pack.json`, `fixtures/exchanges.json` and
    `tests/test_pack.py`. The manifest has `connector`, `entitlements`,
    `scopes` and `standalone`. It starts from a blank template or, through
    the existing `core.pack.openapi.import_openapi`, from an OpenAPI 3
    document.
    - No consequence is ever written.
    - A non-empty target is refused (`INIT_TARGET_NOT_EMPTY`).
    - Ids are checked before the first write.
    - An OpenAPI scaffold writes one call per operation and records no
      responses.
  - `decide_consequences` checks every decision before it writes:
    `CONSEQUENCE_TARGET_UNKNOWN`, `CONSEQUENCE_UNKNOWN` and
    `CONSEQUENCE_DECISION_INVALID`.
- `src/core/pack/connector.py`: `_refuse_undecided`. `CONSEQUENCE_MISSING`
  now names every undecided operation, in file order, in its message and in
  the new `PackManifestError.operations` (`src/core/pack/manifest.py`).
  `operation` is still the first one. `validate`, `build`, `install` and
  `doctor` all get this through the one validator.
- `src/core/pack/recorded.py` (new) implements `flyto pack test`.
  - Fixture format: `flyto.pack-fixtures.v1` (customers with a test
    credential and an optional `offered` list, recorded exchanges, calls with
    `expect`).
  - The fake provider is a loopback HTTP server built only from the
    exchanges. It identifies the customer by the header the runtime itself
    encodes, uses a test token endpoint for client credentials, and answers
    401 to an unknown credential.
  - `recorded_install` copies the manifest, points `base_url` and
    `token_url` at the fake, and installs it with `install_pack`.
    `FLYTO_ALLOWED_HOSTS` and `FLYTO_HTTP_ALLOWED_PORTS` are set for the run
    and restored after.
  - Every call goes through `ModuleRegistry` and `module.run()`, so the real
    connector runtime and gate run.
  - Per-operation typed failures (`TEST_FAILURES`): `UNEXPECTED_RESULT`,
    `CALL_RAISED`, `UNRECORDED_REQUEST`, `UNKNOWN_CREDENTIAL`,
    `SENSITIVE_PATH_UNMATCHED`, `DATA_PATH_UNMATCHED`,
    `RESULT_SCOPE_UNMATCHED` (`RESULT_SCOPE_UNREADABLE` maps here through
    the `DECLARATION_FAILURES` table), `PROBE_SHAPE_INVALID` (each customer's
    probe answer through `read_answer`), `OPERATION_UNTESTED`, and
    `EFFECTIVE_OPERATIONS_MISMATCH` (`effective_module_ids` against
    `offered`).
  - It then runs `conform_async`.
  - Refusals: `FIXTURES_MISSING`, `FIXTURES_INVALID`,
    `NOT_A_CONNECTOR_PACK`.
- `src/core/pack/doctor.py` (new): `DIAGNOSES` is one table of code to
  cause and fix, with 134 rows.
  - `diagnose` explains the first refusal. For a connector pack it then
    checks every operation on its own, with a stand-in consequence that is
    never written, so every operation-level refusal shows at once.
  - Unknown codes get `UNLISTED`; no meaning is guessed.
- `src/core/pack/supply_chain.py`: the revocation signature code map is
  hoisted to the table `REVOCATION_SIGNATURE_REFUSALS`, so the completeness
  test can read it.
- `src/cli/pack.py` adds `flyto pack init|consequence|doctor|test`.
- `examples/packs/product-combinations/` (new): three products (`records`,
  `planning`, `analytics`) and `plan.forecast`, which needs two. The
  fixtures hold eight customers, one per combination, each with its
  `offered` listing.
- Docs:
  - New `docs/guides/BUILD_A_PACK.md`.
  - `docs/CLI.md` gains a Packs section.
  - `docs/specs/PACK_MANIFEST_SPEC.md` gains the CLI lines, a fixtures
    section and the example.
  - `docs/README.md`, `CHANGELOG.md` (Unreleased), `STATE.md` and
    `DECISIONS.md`.
  - Regenerated `docs/reference/` and the inventory tokens.
- Tests (new):
  - `test_pack_init.py` (18)
  - `test_pack_test.py` (22)
  - `test_pack_doctor.py` (143, of which 134 are per-row)
  - `test_product_combinations.py` (14)
  - `test_build_a_pack_guide.py` (4)
  - helpers in `devkit_helpers.py`

## Why

A provider has to be able to ship without Flyto2's help, and every customer
holds a different product combination. Rejected alternatives:

- Inferring a consequence from the HTTP method.
- Inventing responses for an OpenAPI scaffold.
- A test mode inside the runtime: the fake is an ordinary loopback server
  behind the SSRF guard's operator opt-in.
- A doctor table with no completeness check. The test parses the
  `core/pack` sources with `ast`. It requires a row for every literal code,
  including both branches of a conditional. It maps each run-time-chosen
  code site to the table that holds its codes, and fails on any new dynamic
  site.

## Verified

- Failing first (`scratchpad/round7/pack-devkit-evidence/failing-first.txt`):
  22 failed and 3 collection errors (`core.pack.recorded` and
  `core.pack.doctor` absent). Base behaviour on f75f3a2
  (`consequence-naming-base.txt`): `CONSEQUENCE_MISSING` named only
  `account.entitlements`, and `operations` was ABSENT.
- The guide test was checked by mutation. With the same guide edits:
  - dropping a promised `# exit 1` failed it;
  - quoting an inline command that no block runs failed it;
  - swapping a feature list in the excerpt failed it.
- After the change: 201 new tests passed. Pack and CLI suites: 643 passed,
  6 failed. The 6 are listed under "Not verified"; they fail identically on
  f75f3a2.
- Full non-browser suite `pytest -m 'not browser and not e2e' --no-cov`:
  5951 passed, 6 failed (the same 6 pre-existing tests listed below), 174
  skipped, 508 deselected, 3 warnings.
- `generate_reference.py` regenerated the reference (6,775 declarations,
  1014 files). `check_documentation.py` PASS (195 Markdown files, 250 local
  links). `check_brand_identity.py` PASS (1305 files).
  `lint-project-memory.sh` PASS.
- Ruff on every changed Python file: all checks passed.
- `flyto-index verify --strict`: Status PASS, 21 pass, 0 warn, 0 fail.

## Not verified

- These 6 tests fail on the base tip f75f3a2 without this change:
  `test_portable_pack.py::test_the_pack_cli_builds_and_verifies_a_zip` and
  five in `test_standalone_server.py`. They are integration drift between
  the portable lane (written for a 3-operation example) and the entitlements
  lane (it added `account.entitlements` and `portfolio.add`).
  - One of them is a real gap, not only a stale count. The standalone
    server passes only `secrets`, never `scope_grants`, so a scoped
    operation called standalone is refused with
    `PROVIDER_ENTITLEMENT_UNREADABLE` or `SCOPE_GRANT_MISSING`.
  - That also applies to the guide's scaffold if a customer calls
    `items.item.get` through `flyto pack run`. The guide only lists the
    tools.
  - Not fixed here: deciding who grants scope standalone is a design
    decision for the portable or entitlements owner.
- No real provider, credential or network was used. Only loopback fakes.
- The Windows entry points and a real lockfile were not exercised. The
  guide's `--lock` is the suite's fixture lock.
- `flyto pack test` with `oauth2_client_credentials` and with
  `link_header` pagination is implemented but has no dedicated test.
- CI and release were not run.

## Follow-ups

- Decide how the standalone server grants data scope (the user owns the
  credential, so `"*"` per declared dimension may be right), then fix the 6
  stale standalone and portable tests.
- Add tests for client-credentials and Link-header fixtures.
- A `flyto pack record` that captures exchanges from a provider sandbox
  (it needs the network; out of scope here).
