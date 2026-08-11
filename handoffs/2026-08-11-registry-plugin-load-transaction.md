# Registry plugin-load transaction: stale removal, foreign-row rollback, empty plugins

Owner: claude
Branch (as written, 2026-08-11): `claude/plugin-capability-declaration`
Branch (audited/accepted): `main`
Date: 2026-08-11
Status: Completed — verified and accepted 2026-08-11

> **Branch correction.** This handoff and its "same branch" line below were
> written against `claude/plugin-capability-declaration`. The audited worktree
> is on `main`, which is the branch the acceptance below applies to. Original
> lines left as written.

Continues the 2026-08-08 plugin contribution/policy-scope handoff. Same files,
same branch, same owner.

## Why

`_load_plugin` decided everything from ownership metadata — `_owned_by(name)`
read after `register_all()` returned. That answers "who owns this row now", and
three different questions were being asked of it that it cannot answer:

1. **Is a module the plugin owns still provided?** It always looked provided,
   because the stale row from the previous pass was still sitting there and
   nothing removed it. A plugin that dropped a module kept it forever, and kept
   being billed for it in `module_count`. The docstring already claimed the
   replacement included "modules it has stopped providing"; the code did not do
   it.
2. **Did this pass create the row, or overwrite someone else's?**
   `register()` stamps the loading plugin's name onto whatever it writes, so a
   row the failing plugin overwrote — flyto-core's own, or another plugin's —
   came back owned by the failing plugin. Rollback computed
   `partial = _owned_by(name) - before_ids` and dropped it, which **deleted the
   displaced module** instead of returning it to its owner.
3. **Does an empty result mean "cached import" or "provides nothing"?**
   Indistinguishable, so `if not owned and remembered` replayed an earlier
   pass's modules over a plugin that legitimately provides nothing.

## What changed

`src/core/modules/registry/core.py`

- New per-pass record, installed and torn down in the same `try/finally` as
  `_loading_plugin`: `_pass_registered` (ids this `register_all()` wrote) and
  `_pass_displaced` (the row that stood at each id before the first write to
  it). `register()` captures the displaced row *before* overwriting, which is
  the last moment it exists. `_load_plugin` holds both as locals so the
  `finally` can clear the class attributes while rollback still reads them.
- New `_cleared`, set by `clear()` and consumed by the next `discover_plugins`
  pass, which snapshots it as `_started_empty`. Deliberately not "the registry
  is empty": a registry emptied by unregistering a plugin's modules one at a
  time is indistinguishable from a cleared one, and replaying into it would
  resurrect what somebody just removed.
- `_load_plugin` now branches on the record:
  - **registered something** → that is the whole answer. Ids the plugin owned
    going in and did not register again are unregistered, guarded by a
    still-owned check so a module another plugin has since taken over is left to
    that plugin. The contribution record is rewritten, so the withdrawal
    survives the next clear/discover cycle.
  - **registered nothing, registry began the pass empty** → the clear/discover
    case the record exists for; replay it.
  - **registered nothing, registry already had contents** → the call said
    nothing, so neither does this. No replay.
- Rollback is now `_restore(displaced, drop=registered - set(displaced))`:
  every displaced row goes back exactly, and only ids that held nothing before
  are deleted. `_restore(prior_rows)` follows as a backstop for rows lost by
  some route other than being overwritten.
- `clear()` also drops the in-flight record, for the same reason it already
  reset `_loading_plugin`.
- The "registered nothing into a live registry" branch refreshes
  `_plugin_contributions[name]` when the plugin is already on record, so a
  plugin emptied by unregistering its modules stops being replayed by the next
  `clear()`.
- `discover_plugins`' `finally` clears the pass record too, so anything raising
  after the plugin loop cannot leave the next `register()` writing into a pass
  that is over.

`tests/core/test_plugin_policy_scope.py` — 17 tests added under "discovery is a
transaction over the registry", driving discovery against described entry points
(`_EntryPoint`, returned in a `_Groups` list subclass so the double satisfies
both the 3.10+ `entry_points(group=)` and the 3.9 `entry_points().get()` call
shapes, since the package supports 3.9) rather than installed distributions. A `registry` fixture saves
and restores all eleven pieces of process-global registry state. Coverage:
first catalog read triggers discovery and a read from inside a plugin does not
start a second pass; owner counts including the second-pass `module_count` 0
regression; exact clear/force cycles including first-party baseline restore;
stopped-providing removal and its survival across a clear; uninstalled
plugin/module removal and non-replay, plus the unknown-owner module that is not
a leftover; full rollback including first-party and cross-plugin foreign-row
restoration, failed-first-load, pass continuation, and no leaked record.

No API changed. `register()`, `unregister()`, `discover_plugins()`, `clear()`
and `PluginInfo` keep their signatures; the new state is private.

## Verification: accepted

This change is **verified and accepted**. `REGISTRY_VERSION` is 1.4.0.

Receipts. The revisions are flyto coding implementation revisions (SHA-256).
They are not Git commit hashes and do not resolve against this repository's
object database.

| Covers | Acceptance job ID | Accepted implementation revision (SHA-256) |
| --- | --- | --- |
| Documentation | `job_453f3754aa2041309060b75a` | `ebeb0ebfcab2d56bec576a944dcadd23fa197ff9726c558379df1c76eb12e341` |
| Source and tests | `job_ad0baf4f580e4bc6aaac37de` | `b391189517db77146c4ab51def48ed7ada04fb30308296480e2e083df46bf65c` |
| Generated catalog and tests | `job_8d8d49019afa402a8c503aa0` | `a08df544401cf36a54dfe4f6fc084512cb3035a9febf885442baca5cd8366f15` |

Passed against those receipts:

- The six pinned checks in `.flyto/coding.yaml` — `project_memory`, `compile`,
  `lint`, `generated_reference`, `registry_plugin_contract`, `tests`.
- The Core module-contract proof, `flyto.core.module-contract.v1`.
- Strict Indexer verification.
- An independent replay of 78 registry tests and 25 catalog tests.

This supersedes the earlier "unverified" status of this handoff and the
tracing-by-hand caveat it carried: the behavioural claims in *What changed* are
now backed by runs, not by hand-tracing.

### Provenance of this record

The acceptance above was produced by the audited acceptance run against those
receipts and reported into the session that wrote this section; it was not
re-executed there. That session could execute only the two declared project
actions, and ran both against the current tree:

- `generate_reference` — exit 0, 5,572 declarations across 953 files.
- `generate_catalog` — exit 0, 468 modules across 85 categories.

Both match the figures already on record, which is the evidence that the
accepted tree and this tree agree on generated output. The six pinned checks,
the Core proof and the Indexer strict run were not re-run there — `pytest`,
`compileall`, `ruff` and the Indexer MCP tools were denied. No commit,
deployment, or hardware claim is made.

### The `registry_plugin_contract` coverage question is settled

The pinned argv now passes `--no-cov`, so the check reports the registry
contract it was pinned to prove rather than the project-wide coverage floor it
used to inherit from `addopts` in `pyproject.toml`. The earlier warning in this
handoff — that a red exit code meant the coverage gate rather than a real
failure — no longer applies; the exit code can now be read directly.

## Remaining

The `PluginService` / runtime plugin lifecycle is tracked separately and is
**not** closed by this work. The out-of-process plugin path
(`src/core/api/plugins/service.py`, `src/core/plugin/`) sits outside this
transaction: it is omitted from the coverage kernel, has no equivalent
rollback, and its `PluginLoader.discover_plugins` returns its own live mapping.
Open since 2026-08-08 and carried in `tasks.md`.

That is this handoff's remaining scope, and only that. It is **not** a claim
that the runtime lifecycle is the last open plugin surface in the repository —
other plugin surfaces are documented open elsewhere and are outside what this
work touched or assessed. `docs/specs/PLUGIN_MANIFEST_SPEC.md` is the reference:
the `flyto.plugin.v1` manifest is a DRAFT specification whose
implementation-status table separates what the code enforces from what is only
specified, `RuntimeInvoker.set_plugin_manager` still has no caller anywhere (so
a workflow step cannot reach a plugin subprocess), and that document also
records the containment flyto-core cannot provide for a plugin running as its
own process.
