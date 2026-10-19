# Portable packs, pack supply chain, and bundles

Owner: claude
Branch: lane/portable-pack (on origin/feat/unified-platform-integration-20261018 at c7c60b6)
Date: 2026-10-19

## What changed

The owner's decision (Flyto2 is not a gateway): a pack runs on its own as a
standalone MCP server with the user's own credentials, and the same artifact
loads into a Flyto2 Space. One artifact, two ways to run.

- `src/core/mcp_protocol.py` (new): the MCP protocol code that was in
  `core.mcp_handler` (protocol eras, `initialize`/`server/discover`,
  `tools/list`, `tools/call` dispatch) and in `core.api.routes.mcp` (the
  Streamable HTTP POST rules and mirrored-header checks), plus the STDIO loop
  from `core.mcp_server`. The catalog server and the standalone pack server
  both use it, so there is one implementation. The existing behavior is
  unchanged. One test patch target moved (`decode_mcp_header`).
- `src/core/pack/portable.py` (new): the `standalone` section. Authors write
  `transports`, `runtime` and `lockfile`. Normalization derives
  `credentials` (names from `connector.auth`, plus the env var
  `FLYTO_CREDENTIAL_<NAME>` and keychain service/account),
  `credentials_needed` and per-platform `entry_points` from the
  `PLATFORMS` and `STANDALONE_RUNTIMES` tables. A hand-written copy is
  refused (`STANDALONE_DERIVED`). The module also holds
  `build_portable_pack`, which writes the generated `bin/<platform>/*`,
  `README.md` and `THIRD_PARTY_NOTICES.md`, sets the digest, signs, verifies
  and writes a deterministic zip. It also holds `extract_pack_zip` (all
  entries checked before any write) and `verify_pack` (dir or zip).
- `src/core/pack/standalone.py` (new): one generic runtime. It verifies the
  pack (revocation first), installs it with `install_pack` (the Space path),
  and serves the modules as MCP tools over stdio or loopback-only Streamable
  HTTP (bearer token required, non-loopback `Origin` refused). Tool
  annotations come from `connector.CONSEQUENCE_ANNOTATIONS`. `tools/call`
  goes through `core.mcp_handler.execute_module`. `health()` reports
  credential names and sources, never values.
- `src/core/pack/standalone_auth.py` (new): `CredentialResolver`. It reads
  the env var first, then the OS keychain (`KEYCHAIN_READERS` table:
  `security` on macOS, `secret-tool` on Linux, `keyring` on Windows when
  installed). `FLYTO_PACK_NO_KEYCHAIN=1` turns the keychain off. The file is
  not named `credentials.py` because the indexer's `change_hygiene` treats
  `*credential*` paths as secret-shaped.
- `src/core/pack/supply_chain.py` (new): `pack_digest` (sha256 of the
  normalized manifest, which carries `artifact.digest`), `parse_lockfile`
  (pip `--require-hashes` format; every line pinned and hashed; runtime
  package at `min_host` or later), and the signed revocation list
  `flyto.pack-revocations.v1` (`sign_revocations`, `load_revocations`,
  `read_revocations`, `RevocationList.check`).
- `src/core/pack/bundle.py` (new): `flyto.bundle.v1`. Packs are referenced by
  id, exact version and pack digest and never copied. Workflows and templates
  each carry their own digest. Building and verifying refuse
  `PACK_DIGEST_MISMATCH`, `PACK_NOT_FOUND`, `PACK_REVOKED`,
  `MODULE_NOT_PROVIDED` (module ids found with `module_policy`'s collector,
  inline sub-workflows included), `DUPLICATE_NAME`, `VERSION_NOT_PINNED`,
  `UNDECLARED_FILE` and `WORKFLOW_/TEMPLATE_DIGEST_MISMATCH`. Signing is
  optional (`flyto-bundle.sig.json`).
- `src/core/pack/signature.py`: `sign_detached`/`verify_detached` (one
  ed25519 step with a domain per document type). `sign_manifest` and
  `verify_manifest_signature` use them, and their output is unchanged.
- `src/core/pack/host.py`: `install_pack(..., revocations=)` refuses a
  revoked pack before anything else runs.
- `src/core/pack/manifest.py`: adds the `standalone` top-level key.
  `_iter_pack_files` gains a `skip` parameter.
- `src/core/pack/connector.py`: adds the `CONSEQUENCE_ANNOTATIONS` table.
- `src/core/pack/compatibility.py`: adds the row `pack.standalone`
  (2.41.0).
- `src/cli/pack.py`, `src/cli/main.py`: add `flyto pack build|run|health`;
  `pack verify` now takes a zip and revocation options; new
  `flyto bundle build|verify`.
- Example `examples/packs/ratings-connector` gains a `standalone` section.
  New `examples/bundles/rating-review/` (one workflow, one template).
- Docs: `docs/specs/PACK_MANIFEST_SPEC.md` (Portable packs and Supply chain
  sections), new `docs/specs/BUNDLE_SPEC.md`, `ADAPTER_COMPATIBILITY_MATRIX.md`,
  `CHANGELOG.md` (2.41.0), `STATE.md`, `DECISIONS.md`, `docs/README.md`,
  `docs/CLI.md`, `.env.example` (`FLYTO_PACK_HTTP_TOKEN`), regenerated
  `docs/reference/`, inventory tokens.

## Why

One pack must not need a second "standalone edition", and the standalone
server must not be code written per provider. Running through
`install_pack` plus `execute_module` means a standalone tool is the same
module, behind the same policy gate, as in a Space. A revocation list that
fails verification refuses the start instead of being ignored.

Rejected alternatives:

- Writing a second MCP server. Instead the protocol was extracted and is
  shared.
- A `--base-url` override at run time. It would change where the credential
  is sent without a new signed manifest.
- Writing the license notice from the build machine's installed metadata.
  The digest would then depend on the build environment.

## Verified

- Failing first: the four new test files all failed at collection
  (`ModuleNotFoundError: core.pack.bundle` / `portable` / `standalone` /
  `supply_chain`; `install_pack` had no `revocations`). Recorded in the lane
  evidence `failing-first-collection.txt`.
- New tests, 94 passed: `test_portable_pack.py` 45,
  `test_pack_revocation.py` 12, `test_standalone_server.py` 15,
  `test_bundle.py` 22.
- The proof test
  (`test_the_built_zip_runs_standalone_over_stdio_through_its_generated_entry_point`)
  builds the example into a zip and extracts it. It then runs the generated
  `bin/macos/serve.sh` as a subprocess, using a venv shim whose `flyto` is
  this checkout's CLI. As an MCP client it sends `initialize`,
  `tools/list` (3 tools, `readOnlyHint` true) and `tools/call`
  (`ratings.company.get` returns the recorded body from a loopback fake
  provider). The credential comes from `FLYTO_CREDENTIAL_RATINGS_API_TOKEN`
  and never appears in stderr.
- Manual CLI run: `flyto pack build examples/packs/ratings-connector --lock
  <fixture>` wrote a 13-entry zip, and `pack verify` and `pack health`
  passed. `pack health` with no credential exited 1 with
  `CREDENTIAL_MISSING`. `pack run --transport streamable_http` returned 401
  without a token and listed the 3 tools with one.
- Related suites (pack, api, MCP stdio/real): 601 passed. Full non-browser
  suite `pytest -m 'not browser and not e2e' --no-cov`: 5658 passed, 174
  skipped, 508 deselected.
- `generate_reference.py` regenerated; `check_documentation.py` PASS (191
  Markdown files, 247 local links); `check_brand_identity.py` PASS;
  `lint-project-memory.sh` PASS; ruff clean on every changed Python file
  (`mcp_server.py` had 7 pre-existing findings, fixed because the file was
  touched).
- `flyto-index verify --strict`: PASS, 21 pass, 0 warn, 0 fail. An earlier run
  failed `env_contract` (`FLYTO_PACK_HTTP_TOKEN` not in `.env.example`) and
  `change_hygiene` (a `credentials.py` path); both were fixed at the source.

## Not verified

- The install entry point was never run. It needs a package index, and the
  lockfile in the tests is a fixture whose hash is not of a real wheel.
  flyto-core 2.41.0 is unreleased, so no real lock exists yet.
- The Windows `.cmd` entry points were generated and their content was
  checked, but they were never run on Windows. The Windows keychain path
  (`keyring`) is untested.
- The Linux `serve.sh` was not run; only the macOS one was.
- No real provider and no real credential were used. One manual
  `pack health` run without the env var made a read-only lookup in the macOS
  keychain for a non-existent item (`flyto.pack.com.example.ratings`); after
  that, `FLYTO_PACK_NO_KEYCHAIN` was added and the tests set it.
- No revocation list is distributed anywhere, and no sequence/rollback
  tracking is kept across lists.
- CI and release were not run. Cloud does not yet call `install_pack` with
  `revocations`.

## Follow-ups

- Release: produce the real `requirements.lock` for portable packs from the
  published flyto-core 2.41.0 wheel hashes (and its dependency closure).
- Cloud/Desktop: pass the host's verified revocation list to
  `install_pack(revocations=...)`, and install bundles from file with
  `verify_bundle`.
- Windows: run the generated `.cmd` entry points on a Windows host.

## Addendum: the standalone server lists only entitled tools

Owner: claude
Branch: lane/standalone-entitled (on core-integ f75f3a2)

The connector pre-check landed beside portable packs, and the example pack
gained an entitlements probe (`ratings.account.entitlements`) and a gated
write (`ratings.portfolio.add`). The standalone server listed every declared
operation, and its calls carried no scope grant, so six tests failed: five
hardcoded the old three tools, and the calls were refused
`PROVIDER_NOT_FOUND` (the fake provider had no probe) and then
`SCOPE_GRANT_MISSING`.

- `connector_gate.EntitledListing` and `ConnectorTransport.entitled_listing`:
  the one listing, with what it stood on (`provider`, `cache`,
  `not_required`, `unreadable` + `error_code`). `effective_module_ids` is
  now a wrapper over it; `host.entitled_listing(pack_id, secrets)` is the
  host entry point.
- `standalone`: `tools/list` filters the declared tools by that listing
  (same probe, same cache, no second copy). An unreadable probe lists only
  ungated tools; every declared tool stays callable and the gate refuses
  typed. The probe is itself a tool (ungated observe, always listed).
  Calls carry `standalone_scope_grants`: `"*"` for each declared dimension,
  because the credential holder is the caller. `health` adds
  `entitled_tools` and `entitlements`, and an unreadable probe with a
  credential present is a `PROVIDER_ENTITLEMENT_UNREADABLE` problem.
- `mcp_protocol.McpServer`: `list_tools` may be a coroutine;
  `tools_list_public=False` drops the public cache hint on a
  per-credential list.
- Tests read expectations from the example manifest and the recorded
  entitlement answers (`portable_helpers.entitled_ids` / `declared_ids`);
  no tool count is hardcoded. New: fewer features list fewer tools (and the
  hidden call is `FEATURE_NOT_ENTITLED`), an unreadable probe lists only
  ungated tools (and `company.get` is `PROVIDER_ENTITLEMENT_UNREADABLE`
  without reaching the provider), health reports the entitled count for
  three answers, and a modern `tools/list` carries no `cacheScope`.
- `PACK_MANIFEST_SPEC.md` "Running standalone" and the pre-check section
  record the rule and the probe-as-tool decision.

Not verified: no real provider, no Windows or Linux entry point run, CI not
run. The standalone `"*"` scope grant is a design decision recorded in the
spec; no owner review of it yet.
