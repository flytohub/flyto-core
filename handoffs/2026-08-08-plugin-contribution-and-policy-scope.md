# Plugin contribution point, per-plugin policy scope, and the manifest draft

Owner: claude
Branch: `claude/plugin-capability-declaration`
Date: 2026-08-08

## What changed

Three commits, in the order they had to happen.

**1. A module may declare the capability it provides.**
`src/core/modules/registry/decorators.py` — `register_module(provides_capability=...)`.
`src/core/modules/registry/metadata.py` — stored in metadata; the parameter is
last and defaulted so callers outside this repository keep working.
`src/core/modules/registry/core.py` — `ModuleRegistry.capabilities()` returns
`{capability: [module_id, ...]}`.

**2. Policy has a plugin dimension, and it can only narrow.**
`src/core/module_policy.py` — `plugin_grants()`, `is_plugin_allowed()`,
`missing_permissions(..., plugin=)`, and `enforce_module_policy(..., plugin=)`.
Three new environment variables: `FLYTO_PLUGIN_GRANTS` (`plugin:permission`
pairs), `FLYTO_PLUGIN_DENYLIST`, `FLYTO_PLUGIN_ALLOWLIST`.
`src/core/modules/registry/core.py` — `_loading_plugin` is set for the span of
each plugin's `register_all()` and cleared in `finally`; `register()` stamps it
into metadata, overwriting whatever the module supplied.
`src/core/modules/base.py` — the chokepoint passes `plugin=` from metadata.

**3. The out-of-process plugin path passes the same gate.**
`src/core/runtime/invoke.py` — `RuntimeInvoker.invoke` calls
`enforce_module_policy` on the resolved module id *before* routing, so the plugin
path and the legacy fallback are covered alike. `_policy_denial` reads the step's
declared `required_permissions` from the plugin's manifest when one is loaded.

**Documentation.** `docs/specs/PLUGIN_MANIFEST_SPEC.md` — DRAFT of the
language-neutral manifest, with an implementation-status table separating what
the code enforces from what is only specified. Indexed in `docs/README.md`.

## Why

An adversarial review of three candidate manifest designs returned a fatal
finding on every one, with the same shape each time: an authority model whose
gates existed in prose and not in code. Per-plugin module policy, per-plugin
permission scope and manifest-verified integrity were all written in the present
tense against a codebase that had none of them.

So the code came first and the spec says what is real.

**The escalation that made this urgent.** With one process-global grant set, a
plugin that *honestly* declared `required_permissions: [shell.execute]` was
asking the operator to grant shell.execute to every module in the process —
flyto-core's own and every other plugin's. Declaring a permission is how a plugin
tells the truth about itself; it must not be how it acquires reach.

**Rejected:** letting a module declare its own owner. The lie worth blocking is
not "I am plugin B" but "I am no plugin at all", because the empty owner is the
one the process-global grant still covers. Ownership is assigned by the registry.

**Rejected:** treating the Python entry point as the ecosystem's contribution
point. It cannot serve a plugin written in another language, and plugins are
explicitly not meant to be language-restricted. It is one binding, and both the
code comments and the spec say so.

## Verified

- `pytest tests/ --ignore=tests/browser --ignore=tests/e2e` →
  **2675 passed, 18 skipped**, coverage 63.39%. Baseline before this work was
  2644; 31 tests added across `tests/core/test_plugin_policy_scope.py` (24) and
  `tests/core/test_runtime_policy_gate.py` (7).
- `scripts/check_documentation.py` → passed, 138 Markdown files, 161 local links.
- `scripts/check_brand_identity.py` → passed.
- `scripts/lint-project-memory.sh` → PASS.
- `scripts/generate_reference.py` → regenerated; inventory tokens reconciled to
  5,558 declarations across the docs that carry them.
- Nine end-to-end policy scenarios run against the real enforcement path,
  including: a global grant no longer reaching a plugin; a per-plugin grant
  reaching only that plugin; and a fully permitted plugin still refused a
  denylisted module id.
- Ownership checked against the really-installed `flyto-modules-vision`:
  `vision.observe` stamps `vision`, `http.get` stamps `""`.
- `ModuleRegistry.capabilities()` against a built wheel in a clean venv returns
  `{'vision.observe': ['vision.observe']}` after `discover_plugins()`.
- One hole found by a failing test rather than by reading: `register()` only
  stored metadata when it was truthy, so a plugin's metadata-less module had no
  owner — and an absent owner reads as first-party. Closed, with a test.

## Not verified

- **No plugin subprocess was actually executed.**
  `RuntimeInvoker.set_plugin_manager` still has no caller, so a workflow step
  cannot reach one. The gate is tested with a stand-in manager, not against a
  spawned process. When that wiring is added, re-verify the gate against a real
  plugin before trusting it.
- Nothing in `docs/specs/PLUGIN_MANIFEST_SPEC.md` marked **SPECIFIED** is
  implemented: no manifest schema, no validator, no `artifact.digest`
  verification, no derived endpoint/token env names, no `locality` enforcement,
  no registry or adoption flow.
- The relationship between `flyto.plugin.v1` and the existing `plugin.yaml`
  documented in `docs/PLUGIN_SDK.md` is an open question, not a decision.
- Browser and E2E suites were not run.
- The five-string `_DANGEROUS_PERMISSIONS` set was read, not re-derived; a
  manifest naming anything outside it names nothing.
