# Language-neutral module packs `flyto.pack.v1` (2.37.0)

Owner: claude
Branch: claude/language-neutral-packs
Date: 2026-10-04

## What changed

- `src/core/pack/` (new):
  - `manifest.py` — `flyto.pack.v1` schema and validator. A pack manifest is the
    `ModuleRegistry` row `@register_module` produces, as JSON (decorator keyword
    names; the validator applies the decorator's defaults; the contract goes
    through `validate_contract`). Bounded JSON copy, unsafe Unicode refused,
    reserved/core namespaces refused, value-free error codes. `pack_tree_digest`
    (sorted `path NUL sha256 NUL size` lines, symlinks refused).
  - `signature.py` — ed25519 over `b"flyto.pack-signature.v1\n" +
    canonical(normalized manifest)`; detached `flyto-pack.sig.json`; offline
    verification against a host-supplied `{key_id: public key}` set.
  - `host.py` — `install_pack` / `uninstall_pack` / `installed_packs`:
    digest + signature (required by default) → `PluginManager.register_pack`
    (subprocess) or derived-env endpoint (http) → one `@register_module` row per
    module inside `ModuleRegistry.install_external_pack` (owner = pack id) →
    invoker wiring → `flyto.pack-provenance.v1` record. The pack process gets
    params and `{pack_id, module_id, execution_id}` only.
  - `export.py` — `export_python_pack` (entry point name or `module:callable`).
- `src/cli/pack.py` + `src/cli/main.py`: `flyto pack manifest|digest|keygen|sign|verify`.
- `src/core/modules/registry/core.py`: `_external_packs`, included in every
  discovery pass; `install_external_pack` / `uninstall_external_pack`;
  `_load_plugin` returns bool and honours `pack_version` / `pack_description`.
- `src/core/runtime/manager.py`: `register_pack` / `unregister_pack`,
  `language_explicit`, `process_env`; plugin ids may contain single dots.
- `src/core/runtime/invoke.py`: `invoke_plugin_step`, `plugin_manager`
  property. `set_plugin_manager` now has a caller (pack install).
- `examples/packs/node-greeter/` — Node.js pack, dependency-free
  `registerModule` helper (`flyto.js`), checked-in `flyto-pack.json`.
- Tests: `tests/core/pack/` (76 tests).
- Docs: `docs/specs/PACK_MANIFEST_SPEC.md` (new), `docs/CAPABILITY_CONTRACT.md`
  "Other languages", `PLUGIN_MANIFEST_SPEC.md`, DECISIONS (new schema, not an
  extension of `flyto.plugin.v1`), CHANGELOG 2.37.0, STATE, SECURITY versions,
  regenerated `docs/reference/`, inventory tokens. Version 2.37.0.

## Why

The owner's requirement: `@register_module` is Python authoring syntax; the
platform spec is a language-neutral contract that any language can produce and
Core can load. `flyto.plugin.v1` uses a closed JSON-Schema parameter subset and
an adoption shape, so a decorator export could not round-trip; the new schema
is the registry row itself. The out-of-process runtime had a never-called
`set_plugin_manager`.

## Verified

- `tests/core/pack/`: 76 passed (manifest, signature, host via a stdlib Python
  JSON-RPC subprocess, http binding against a loopback server, export + CLI,
  Node example end to end with node v23.11.1).
- Node and Python rows for the same two modules normalize to identical JSON
  (`test_node_and_python_produce_the_same_rows`).
- Real flyto-modules-robotics (origin/main) exported with
  `flyto pack manifest flyto_modules_robotics:register_all --pack-id robotics
  --version 1.0.0`: 7 modules, 7 contracts, validates.
- Clean venv (`pip install -e '.[dev,browser]'`, Python 3.12) full
  `pytest -m 'not browser and not e2e'`: 5169 passed, 174 skipped, 0 failed,
  coverage 67.81%.
- `python -m build` + `twine check`: PASSED; wheel contains `core/pack/*`,
  `cli/pack.py`.
- `check_documentation` (after `generate_reference`), `check_brand_identity`,
  `lint-project-memory`, ruff on changed files: pass.
- `flyto-index verify . --full-scan --strict`: 20 pass / 1 fail —
  `weak_scan_taint`, the pre-existing `mcp_post → run_recipe → load_recipe`
  path_traversal finding recorded in earlier handoffs; nothing in this change.
- `flyto-index task validate`: fails for environmental reasons — repo-wide ruff
  on pre-existing `examples/agent_demo/*` import order, and the indexer's own
  interpreter lacks `pytest-cov` for the repo's `addopts`.

## Not verified

- flyto-cloud does not call `install_pack`; its worker still discovers
  `plugin.yaml` plugins with an unwired `PluginManager`. No Cloud/Desktop path
  loads a `flyto.pack.v1` pack yet.
- No OS sandbox for subprocess packs (same as every out-of-process plugin).
- TypeScript/Go/etc. runtimes are only reachable through the existing language
  table; only Python and Node were executed.
- No robot, Gazebo twin or ROS 2 adapter was run; nothing here touches the
  capability host or adapter safety invariants.

## Follow-ups

- flyto-cloud: install packs from a configured directory with an operator key
  set, and surface `installed_packs()` provenance on the resource.
- A pack registry / key distribution is out of scope.
