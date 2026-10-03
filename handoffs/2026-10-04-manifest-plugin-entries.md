# Capability manifest plugin entries: `module_ids` and `description` (2.35.1)

Owner: claude
Branch: claude/manifest-plugin-modules
Date: 2026-10-04

## What changed

- `src/core/modules/registry/core.py`: `PluginInfo` gains `description: str = ""` (also in `to_dict()`); new `_pack_description(register_func)` reads an optional module-level `PACK_DESCRIPTION` string from the module that defines the entry point callable. Read, never called; non-string or blank reads as `""`. `_load_plugin` stores it.
- `src/core/capability_manifest.py`: each `plugins[]` entry gains `module_ids` (sorted ids whose metadata names the plugin as owner — the `get_plugin_modules` answer, but derived from the same `capability_snapshot()` so it cannot tear) and `description` only when non-empty.
- MCP `get_module_info` already returned `plugin` and `contract` (via `catalog.module.get_module_detail`); no code change, now pinned by a test.
- `tests/core/test_capability_manifest.py`: 11 new tests (module_ids sorted/equal to registry, key set without description, PACK_DESCRIPTION stripped and in PluginInfo/to_dict, 5 non-string/blank cases, hash changes only when declared, no-plugin manifest shape, MCP owner+contract).
- `docs/CAPABILITY_CONTRACT.md` "Writing a provider": `PACK_DESCRIPTION` convention and the plugin entry shape.
- Version 2.35.1 (pyproject, server.json, SECURITY*.md), CHANGELOG, STATE, regenerated `docs/reference/`, inventory counts (6,144 declarations, 233,652 lines).

## Why

Hosts (Cloud AI Space) group a non-core pack's modules per resource and want the pack's own wording without reverse-mapping ids. `PACK_DESCRIPTION` was chosen over a `describe()` callable: a constant cannot run code or fail during plugin load, so the load transaction is unchanged.

Additive: a manifest with no plugins is byte-identical (plugins list stays `[]`). A manifest with plugins gains `module_ids`, so its hash changes once on upgrade to 2.35.1.

## Verified

Worktree venv, Python 3.11, `pip install -e '.[dev,browser]'`, `npm ci --ignore-scripts`:
- `tests/core/test_capability_manifest.py` + `test_capability_contract.py` + `test_plugin_policy_scope.py`: 313 passed.
- `pytest -m 'not browser'`: 4948 passed, 192 skipped, 79 failed, coverage 66.29%. 63 failures were `tests/test_hints.py` missing `jsdom` before `npm ci` (all pass after). 16 are `tests/modules/test_shell_exec_outcome.py`, which fail identically on the 2.35.0 checkout (0af4da8) in this sandbox; the same call succeeds outside pytest. Treated as environmental; CI is the authority.
- `check_release_drift.py` (2.35.1 unreleased), `check_documentation.py`, `generate_reference.py --check`, `check_brand_identity.py`, `lint-project-memory.sh`, `ruff check` on changed files + CI-audited list: pass.
- `flyto-index verify --strict`: 20 pass / 1 fail — the pre-existing `weak_scan_taint` (`api/routes/mcp.py` -> `cli/recipe.py`), unchanged from main.

## Not verified

- `task(action='validate')` via MCP (server pinned to another root) — not run.
- `lock-deps.sh` / pip-audit not run locally (no dependency change).

## Follow-ups

- flyto-modules-robotics: declare `PACK_DESCRIPTION` beside `register_all`.
- Tag/publish 2.35.1 is the owner's call (no tag pushed here).
