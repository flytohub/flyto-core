# Capability Manifest — `flyto.core.capability-manifest.v1`

- **Owner:** claude
- **Branch:** (working tree; not committed)
- **Status:** Third rework pass applied. Session 4 attempted ledger closure and
  was blocked; session 5 fixed two real Ruff findings (`SIM105`, `B904`) in
  `tests/core/test_mcp_real.py`; session 6 enumerated the full diff (git was
  granted for the first time) and withdrew the generated-docs provenance claim.
  The intent ledger is **still open**, the six
  pinned gates are **still unrun**, and no strict route receipt exists. The
  generated-reference blocker from
  the previous revision is **closed** — the docs are regenerated. A
  stale-refresh race found in the second pass is fixed. **The six pinned gates
  are still not run**; only the two declared project actions are executable
  here. See "Gates" below.

## Generated references — closed

`docs/reference/` is regenerated and current. The earlier revision of this file
recorded it as unfixable because every route into Python was denied; that was
true of the commands tried, but wrong about the conclusion. The repository
declares `generate_reference` and `generate_catalog` as project actions in
`.flyto/coding.yaml` precisely so an implementer who cannot run arbitrary
commands can still rewrite generated output by name. Both ran:

```
generate_reference  exit 0  5,583 declarations, 954 source files
generate_catalog    exit 0  468 modules across 85 categories
```

`generate_reference` was run again after the last source edit and returned the
same figures. ~~so the committed generated docs match the tree as it stands.~~
**That conclusion is withdrawn — see Session 6.** The declared actions run in
the isolated project-action sandbox, so a stable figure says the generator is
deterministic, not that this checkout's generated files are current.
`http-api.md` now carries 24 operations including `GET /v1/capabilities`
(`modules.py:98`) and `POST /v1/capabilities/refresh` (`modules.py:118`), with
every other handler line re-measured by the generator rather than by hand.
`python-api.md` carries `src/core/capability_manifest.py` and both new registry
methods.

**Lesson for the next agent: check `.flyto/coding.yaml` for declared actions
before recording something as blocked on execution.**

## Third pass — the stale-refresh race

The second pass traded a deadlock for a data bug and said so in this file:
"two concurrent builds both run and the last store wins... every caller still
gets a truthful, self-consistent document." The first half is right and the
second half hides the cost. Each *caller* gets a truthful document; the
*cache* does not. A build that reads the registry, is descheduled, and stores
after a refresh has already published the post-refresh document puts the
pre-refresh state back — and nothing corrects it, because the slot is only
rewritten by the next build, which can lose the same race. The refresh looks
like it succeeded and silently did nothing.

The fix is to order stores by the state they describe rather than by thread
schedule.

- `ModuleRegistry._generation` — a monotonic counter bumped at every site that
  writes `_modules`, `_metadata` or `_plugins`: `register`, `unregister`,
  `_restore`, `clear`, the `_plugins` write and rollback in `_load_plugin`, and
  `_forget_uninstalled_plugins`. Always bumped with `_discovery_lock` held.
- `capability_snapshot()` returns `generation` alongside the three views, read
  under the same hold, so it dates *that* state and not what the registry
  became afterwards.
- `capability_manifest._cached_generation` beside the cached document. A build
  publishes only when `_cached is None or generation >= _cached_generation`.
  The losing build still returns its own document to its own caller — it
  describes a state that genuinely existed and hashes to itself.

The generation is deliberately **not** in the manifest. It is a process-local
mutation count, and putting it in the document would break the cross-host
byte-identity the whole schema exists for. `build_capability_manifest()` keeps
its dict-only signature; the private `_build_with_generation()` carries the
pair.

Two things that look like details and are not:

- The counter is never reset. `_reset_registry()` in the tests does not touch
  it and `_REGISTRY_STATE` does not save it, both on purpose: rewinding it
  would let a pre-reset snapshot compare as newer than a post-reset one, which
  is the exact failure it exists to rule out. Test cache invalidation goes
  through `_invalidate_manifest_cache()`, which sets the generation to `-1` so
  any real build outranks an emptied slot.
- Bumping is coarse — two bumps leaving identical content still advance the
  counter. That costs a redundant store. A *missed* bump is the error that
  matters, because it lets two different states tie and the older one win.

### The regression test

`test_a_stale_build_cannot_overwrite_a_newer_cached_manifest` forces the
interleave with events, not sleeps, so it is deterministic in both directions:
correct code always passes, and an unconditional store always fails because the
slow build's store is guaranteed to land after the refresh's.

A slow build is parked between reading the registry and storing, by patching
`capability_snapshot` with a wrapper that waits *after* the real call returns.
That placement is load-bearing — the real method takes and releases
`_discovery_lock` before returning, so the wait holds nothing. Pausing inside
the lock would block the refresh meant to overtake it and the test would
deadlock rather than assert.

`test_generation_advances_with_every_registry_change` pins the counter itself:
it moves on register, unregister and rediscovery, and stands still across a
pure read.

Also fixed here: `test_capability_snapshot_reads_under_one_lock` now expects
`generation` in the key set, and a duplicated `assert not errors, errors` at
the end of the concurrency test was removed.

## Verification surface widened

`.flyto/coding.yaml`'s `lint` argv previously covered none of the
capability-manifest surface, so a Ruff failure in the files this change is
about would not have been caught by the pinned check. Added:
`src/core/capability_manifest.py`, `src/core/modules/registry/core.py`,
`src/core/api/routes/modules.py`, `src/core/mcp_handler.py`,
`tests/core/test_capability_manifest.py`,
`tests/core/api/test_capability_surface.py`,
`tests/core/api/test_mcp_transport.py`, `tests/core/test_mcp_real.py`, and
`tests/core/test_plugin_policy_scope.py`.

`docs/TESTING.md`'s ruff line had drifted into a *different* list from the
pinned argv — it was missing the CLI, constants, workflows-route, crypto and
DNS targets the check actually lints. Both now spell out the same set.

## Prose inventory tokens

`check_documentation.py` derives required prose tokens from the generated
references, so the new module moved every one of them. Updated to 5,583
declarations across 954 maintained Python files (807 declaration-bearing, up
from 806) in `ARCHITECTURE.md`, `STATE.md`, `docs/README.md`,
`docs/MIGRATION_STATUS.md`, `docs/WHITEPAPER.md`, `docs/FEATURES.md`, along
with the 197,795-line total. `ARCHITECTURE.md` also had stale HTTP-operation
and environment-name counts (22/93); both corrected to the generated 24/107.

## What was added

An in-process, read-only capability *catalog* derived from `ModuleRegistry`.
It is not a subprocess manager: nothing starts, stops, or supervises a process.
It answers "which module ids and capabilities are installed right now",
identically on every host with the same installed distributions.

| File | Change |
|---|---|
| `src/core/capability_manifest.py` | New. `build_capability_manifest`, `get_capability_manifest`, `refresh_capability_manifest`, `compute_manifest_hash`, `MANIFEST_SCHEMA`. |
| `src/core/modules/registry/core.py` | New `ModuleRegistry.capability_snapshot()` — atomic grouped read (see below). |
| `src/core/api/routes/modules.py` | `GET /v1/capabilities` (open, read-only); `POST /v1/capabilities/refresh` (`Depends(require_auth)`). |
| `src/core/mcp_handler.py` | `get_capability_manifest` tool: `TOOLS` entry, dispatch branch, implementation. |
| `tests/core/test_capability_manifest.py` | Document tests: entry-point add/remove, ordering/hash determinism, copy isolation, catalog compatibility, **atomicity/concurrency**. |
| `tests/core/api/test_capability_surface.py` | New. MCP dispatch, REST GET, authenticated refresh, unauthorized refresh. |
| `tests/core/api/test_mcp_transport.py`, `tests/core/test_mcp_real.py` | Tool-count expectations corrected 8 → 9. |
| `docs/TESTING.md` | Added `src/core/capability_manifest.py` to the ruff target list. |

## Second audit round — disposition

### CORE-LOCK — **fixed. This was a real deadlock I introduced.**

The first rework added `_cache_lock` and held it across the build. Building
acquires the registry's `_discovery_lock`. Discovery holds `_discovery_lock`
while running a plugin's `register_all`, and a plugin may call
`get_capability_manifest()` — which wanted `_cache_lock`. Two locks, two
threads, opposite orders: reader parks on the registry holding the cache,
discovery parks on the cache holding the registry, neither moves again.

My previous handoff asserted "nothing in the registry reaches back into this
module, so the ordering cannot cycle." That was wrong, and wrong in the way
that matters: plugin code runs *inside* the registry lock, and plugin code can
call anything. The audit was right.

The invariant now, documented at the lock's definition: **never hold
`_cache_lock` while acquiring the registry lock or while running plugin code.**

- `get_capability_manifest` reads the slot under the lock, releases, builds
  with nothing held, then re-takes the lock only to store. The `deepcopy` of a
  cache hit also happens outside the lock — a stored manifest is only rebound,
  never mutated in place, so a captured reference is safe.
- `refresh_capability_manifest` calls `ModuleRegistry.refresh()` with no cache
  lock held at all, and returns the document *this* call built rather than
  re-reading the slot.
- `_cache_lock` is now a leaf: never held while waiting on anything, so no
  cycle can form.

Cost, accepted deliberately: two concurrent builds both run and the last store
wins. Each stores a whole snapshot, and refresh returns its own rebuild, so
every caller still gets a truthful, self-consistent document.

Tests: `test_cache_lock_is_never_held_while_reading_the_registry` observes the
invariant directly — every entry into `capability_snapshot` probes the cache
lock from a *separate* thread (an `RLock` would happily re-acquire on the
owning thread) and records a violation. `test_plugin_reentrant_manifest_call_does_not_deadlock`
drives the full inversion cross-thread with events, so correct code always
finishes and broken code hangs into a join timeout.

### CORE-LINT — **fixed**

`src/core/api/routes/modules.py` had I001: `from core.session_reaper` (first
party) sat below the `..models`/`..security` local-folder imports, and
`require_auth, module_filter` was unsorted within its from-import. Reordered to
stdlib → third-party → first-party → local, names sorted. Ruff config is
`select = ["E","F","W","I","N","B","A","C4","SIM"]` with no isort overrides, so
default section ordering applies.

`docs/TESTING.md` lint argv now also covers `src/core/api/routes/modules.py`,
`src/core/modules/registry/core.py`, `src/core/mcp_handler.py`,
`tests/core/test_capability_manifest.py`, and
`tests/core/api/test_capability_surface.py` alongside
`src/core/capability_manifest.py`.

### CORE-RED — **suite fixes applied; generated refs still blocked**

`test_concurrent_get_and_refresh_never_tears` failed because first-party
modules were still registered: it monkeypatched `entry_points` but never reset
registry state, then asserted exact module-set equality. Two fixes:

1. The state reset is now the shared `_reset_registry()` helper, used by the
   `installed` fixture, the concurrency test, and
   `test_refresh_rediscovers_installed_plugins` (which previously called
   `clear()` directly).
2. **A latent bug in my own fixture:** it reset `_pass_registered` and
   `_pass_touched` to `set()`. `clear()` decides whether it is mid-discovery
   with `cls._pass_touched is not None`, so empty sets made every subsequent
   `clear()` believe it was inside a pass and keep the loading owner and pass
   ledger alive. Both now reset to `None`.
3. Assertions reframed from exact module sets to implication invariants
   ("`cap.left` present ⇒ `left.a` present and no right modules"), plus
   provider ⊆ modules and per-plugin count agreement. `refresh()` legitimately
   replays recorded contributions, so demanding an exact set was testing the
   replay machinery rather than atomicity.

Generated references remain stale — see "Blocked" above.

## First audit round — disposition

### 1. CORE-ATOMIC — **fixed**

The three registry reads (`get_all_metadata`, `capabilities`, `get_plugins`)
were each individually `@_synchronized` but were called in sequence, so the lock
dropped twice in between. A `refresh()` landing in either gap produced a
manifest whose module list came from before the rebuild and whose plugin list
came from after — a registry state that never existed, carrying a hash naming
nothing.

Fix follows the pattern `_synchronized`'s own docstring already established for
single reads, lifted to a group:

- **`ModuleRegistry.capability_snapshot()`** (`registry/core.py`), decorated
  `@_synchronized`, gathers all three under one hold. The nested calls re-enter
  the `RLock` this thread already owns — the re-entry that decorator was made
  reentrant for. It does no I/O and does not await, so it respects the ordering
  note about keeping `_discovery_lock` innermost.
- **`_cache_lock` (RLock)** in `capability_manifest.py` guards the cache slot.
  Build-and-store is one step, the `deepcopy` happens inside the hold, and
  `refresh_capability_manifest` holds it across re-discovery *and* rebuild so
  two concurrent refreshes cannot interleave and leave the older document
  behind.
- Lock ordering is documented in the module: `_cache_lock` is always taken
  before the registry lock, never the reverse. Nothing in the registry reaches
  back into this module, so the ordering cannot cycle.

`filter_by_stability=False` moved into the snapshot, so the environment-
dependent filter cannot influence the hash.

Tests added: `test_concurrent_get_and_refresh_never_tears` (3 readers + 2
refreshers against two mutually-exclusive installs, asserting every observed
document is wholly one or wholly the other and self-hashing),
`test_snapshot_is_internally_consistent`, `test_capability_snapshot_reads_under_one_lock`,
`test_snapshot_ignores_the_stability_filter`.

### 2. CORE-CHECKS — **partly closed; docs regeneration NOT done**

**Tool counts: fixed.** All five located and corrected. In
`test_mcp_transport.py` the three literals now derive from `len(TOOLS)`, because
a hand-typed count meant adding one tool broke five unrelated *transport*
tests — the count was never what those tests were about. Tool identity is
asserted by name instead, and `get_capability_manifest` is now asserted present.
`test_mcp_real.py`'s `EXPECTED_TOOL_COUNT` is 9 with its inventory comment updated.

**Generated references: NOT regenerated. This finding remains open.** I could
not run `scripts/generate_reference.py`. These files embed source line numbers
and GitHub permalinks, and my edits shifted them, so hand-editing would mean
fabricating generator output — worse than leaving it visibly stale. Known stale
in `docs/reference/http-api.md`:

- `/v1/modules` recorded at `modules.py:30`, now **32**
- `/v1/modules/{module_id:path}` recorded at `modules.py:80`, now **82**
- `GET /v1/capabilities` (**`modules.py:97`**) and
  `POST /v1/capabilities/refresh` (**`modules.py:117`**) are missing entirely
- `execute_module` moved to **136**

`docs/reference/python-api.md` also needs the new `src/core/capability_manifest.py`
module and the new `capability_snapshot` registry method.

**Next agent: run `.venv/bin/python scripts/generate_reference.py` then
`scripts/check_documentation.py` before anything else.**

### 3. CORE-SURFACE — **fixed**

New `tests/core/api/test_capability_surface.py`:

- **MCP dispatch** — tool registered with read-only annotations and empty input
  schema; `_handle_tool_call` returns the document; stray arguments tolerated;
  `isError` is False; text block and `structuredContent` agree.
- **REST GET** — 200 without auth, stable across calls, agrees byte-for-byte
  with the MCP tool's document, leaks no volatile detail.
- **Authenticated refresh** — 200, valid document, and what refresh returns is
  what the next read serves (no stale cache).
- **Unauthorized refresh** — missing token and wrong token both refused; a
  refused refresh provably has **no side effect** on the served document; the
  rebuild is not reachable via GET.

A shared `_assert_is_manifest` re-verifies `compute_manifest_hash(body) == body["hash"]`
on every surface, so a client's hash is checkable against the body it arrived with.

## Compatibility finding — list/search/detail needed no change

`core/catalog/outline.py::get_outline`/`get_categories` already derive
categories from live registry metadata with label fallbacks for unknown
categories; `core/catalog/module.py` already projects `provides_capability` and
`plugin` via `_IDENTITY_FIELDS`. Tests pin this rather than rewriting it.

`core/catalog_facts.py` still hardcodes `CORE_MODULE_COUNT = 468` /
`CORE_CATALOG_CATEGORY_COUNT = 85` for help text. Pre-existing, left alone, but
it is a static count in a now-dynamic world — a plugin changes the real number
and not that constant.

## Gates

Ran here, through the declared project actions — the only execution route this
session had:

- [x] `generate_reference` — exit 0, 5,583 declarations across 954 source files
- [x] `generate_catalog` — exit 0, 468 modules across 85 categories

Everything else was denied: `pytest`, `ruff`, `compileall`,
`scripts/check_documentation.py`, and the Indexer MCP tools. So the source
changes above are the product of reading code, not of a green run, and the
regression test is written but unexecuted. **Do not record this change as
verified on the strength of this file.**

1. [ ] `.venv/bin/python scripts/check_documentation.py` — expected to pass:
       the generator was re-run after the last source edit and the six prose
       token sets were updated to match it. This is the check the previous
       audit round failed on, so run it first.
2. [ ] `.venv/bin/python -m pytest tests/core/test_capability_manifest.py tests/core/api/test_capability_surface.py -o addopts=''`
3. [ ] `.venv/bin/python -m pytest tests/core/api/test_mcp_transport.py tests/core/test_mcp_real.py tests/core/test_plugin_policy_scope.py -o addopts=''`
4. [ ] `.venv/bin/python -m pytest -m 'not browser and not e2e'`
5. [ ] `ruff check` with the argv in `docs/TESTING.md` — now identical to the
       pinned `lint` argv in `.flyto/coding.yaml`, and newly covering the whole
       capability surface, so this is the first run that can fail on these
       files. Expect to fix real findings rather than none.
6. [ ] `.venv/bin/python -m compileall -q src`
7. [ ] `.venv/bin/python scripts/check_brand_identity.py`
8. [ ] `bash scripts/lint-project-memory.sh`
9. [ ] `flyto-index verify . --full-scan --strict --json`

## Session 4 (ledger-closure attempt) — what ran and what did not

Objective was to close `action_fix_intent_ledger_task_unplanned_diff` by
building a task ledger covering every diff file, then rerun the six checks and
strict route validation. **The ledger was not built and no check was rerun.**
The blocking reason is recorded here so the next agent does not re-derive it.

Execution routes available this session:

- [x] `run_project_action` — the only working route. `generate_reference`
      returned exit 0, `{"declarations": 5583, "source_files": 954}` — the same
      figures as session 3, run against the tree as it currently stands.
- [ ] `git` — every form denied (`status`, `diff`, `log`, `branch`).
- [ ] Indexer MCP — `task`, `verify` and `impact` all ungranted.
- [ ] `pytest`, `ruff`, `compileall`, `scripts/*.py`, `bash` — denied.

Independently confirmed by reading (not by a green run):

- `docs/reference/http-api.md` reconciles with source. It records
  `GET /v1/capabilities` at `modules.py:98`, `POST /v1/capabilities/refresh` at
  `:118` and `execute_module` at `:137`; a fresh grep of
  `src/core/api/routes/modules.py` puts those handlers at exactly 98, 118 and
  137. The stale line numbers listed under CORE-CHECKS are closed.
- All 26 paths in the `lint` argv in `.flyto/coding.yaml` exist. That check
  fails outright on a listed path that no longer exists, so it cannot fail on
  that ground. It can still fail on real Ruff findings — unrun here.

**Why no ledger was written.** `action_fix_intent_ledger_task_unplanned_diff`
fails when the ledger's targets do not match the actual diff. Without `git` the
diff cannot be enumerated, and the file table above covers only the source and
test files — not the generated references, project-memory prose, `.flyto/coding.yaml`
or handoff edits that this change also touched. A ledger assembled from the
table alone would very likely reproduce the same failure while looking
authoritative. Building it blind was judged worse than leaving it open.

**Next agent: this needs `git` plus the Indexer MCP granted. Enumerate the diff
first, then build the ledger from that list — not from this file's table.**

## Session 5 — the two real Ruff findings, fixed

An audit run of the pinned `lint` check reported two genuine failures in
`tests/core/test_mcp_real.py`. Both were real, both are fixed. This is the
outcome session 3 predicted when it widened the lint argv: "Expect to fix real
findings rather than none."

| Rule | Was | Now |
|---|---|---|
| `SIM105` (~:272) | `try: … except Exception: pass` around the stderr drain | `with contextlib.suppress(Exception):` |
| `B904` (~:323) | `raise RuntimeError(…)` inside `except Exception:` | `except Exception as exc:` … `raise … from exc` |

`import contextlib` added to the stdlib block (sorted first, ahead of `json`).
Net effect on the file is −1 line.

Confirmed by reading the result: the suppress block sits at 272–274 and the
`from exc` raise at 318–322. The only other handler in the file (:259,
`except Exception as e: exc.append(e)`) binds and uses `e`, has no bare `pass`
and no re-raise, so it triggers neither rule. The three `raise` statements at
:267/:269/:275 are in function body scope, not in an `except` clause, so `B904`
does not reach them.

Two follow-on risks checked rather than assumed:

- **Generated-doc drift.** `generate_reference` was re-run after the edit:
  exit 0, `{"declarations": 5583, "source_files": 954}` — identical to before,
  as expected since neither edit adds or removes a declaration.
  `ARCHITECTURE.md:17` still reads "954 maintained Python files, 5,583
  declarations" and remains correct.
- **The line-count prose token.** The −1 line would matter if
  `check_documentation.py` validated a total-line figure. It does not — the
  script's only line-oriented code is `splitlines()` over a git file list
  (:72) and one `re.MULTILINE` extras parse (:227). The 197,795 figure in the
  memory files is unvalidated prose and is not moved by this edit.

**Still unrun, and still the reason this is not closed:** `ruff`, `pytest`,
`compileall`, `scripts/*.py` and the Indexer MCP (`task`/`verify`/`impact`)
remain denied in this session, exactly as in session 4. `run_project_action`
is still the only execution route and exposes only the two doc generators —
there is no route that runs a `checks:` entry. So the two fixes above are
argued from the rule definitions and the surrounding code, **not** from a green
Ruff run, and no strict route receipt was obtained.

## Session 6 — the diff is enumerated; the ledger still cannot be filed

Objective was the same as session 4: build the intent ledger through Indexer
task planning, run the six pinned checks, finish with a strict route receipt.
**None of those three completed.** What changed is that `git` was granted for
the first time, so session 4's stated blocker — "without `git` the diff cannot
be enumerated" — is closed. The enumeration is below; the next agent builds the
ledger from *this* list, not from the file table above, which covers only 10 of
the 30 paths.

### Execution routes, session 6

- [x] `git` (read) — `status`, `diff`, `log`, `rev-parse`. **Newly available.**
- [x] `run_project_action` — `generate_reference` exit 0
      (`{"declarations": 5583, "source_files": 954}`), `generate_catalog` exit 0
      (468 modules, 85 categories). Same figures as sessions 3–5.
- [ ] Indexer MCP — `task` (plan/gate/validate) and `verify` both ungranted;
      each attempted twice. **This is what blocks the ledger and the strict
      route receipt.**
- [ ] `pytest`, `ruff`, `compileall`, `python`, `bash scripts/*` — all denied.
      There is no route to any `checks:` entry, so the six pinned gates could
      not be run here either.

### The project actions run in a sandbox — provenance correction

`generate_catalog` reported `Generated /workspace/docs/TOOL_CATALOG.md`. This
checkout is `/Users/chester/flytohub/flyto-core`, and `git status --short`
returned an identical file list before and after both actions ran. So the
declared actions execute against an isolated copy and **cannot** mutate this
tree.

Sessions 3–5 and `STATE.md` each read the generators' stable figures as evidence
that the committed generated docs match the tree. That inference does not hold
and has been withdrawn in both places. What the runs do establish: the
generators exit 0 and are deterministic, and the sandbox tree carries 5,583
declarations across 954 files. What they do not establish: that
`docs/reference/*` and `docs/TOOL_CATALOG.md` *here* are current. Only the
pinned `generated_reference` check settles that.

### Authoritative diff — 30 paths, from `git status --short`

25 modified, 5 untracked. The working tree carries **two** changes; a ledger
scoped to only one of them will fail `action_fix_intent_ledger_task_unplanned_diff`
on the other's files.

**A. Capability manifest (this handoff)**

| Path | State |
|---|---|
| `src/core/capability_manifest.py` | new |
| `src/core/api/routes/modules.py` | modified |
| `src/core/mcp_handler.py` | modified |
| `tests/core/test_capability_manifest.py` | new |
| `tests/core/api/test_capability_surface.py` | new |
| `tests/core/api/test_mcp_transport.py` | modified — tool count 8 → 9 |
| `tests/core/test_mcp_real.py` | modified — tool count 8 → 9, plus the session-5 `SIM105`/`B904` fixes |
| `handoffs/2026-08-11-capability-manifest.md` | new (this file) |

**B. Registry plugin-load transaction (`2026-08-11-registry-plugin-load-transaction.md`, Completed)**

| Path | State |
|---|---|
| `tests/core/test_plugin_policy_scope.py` | modified — +1,706 lines |
| `tests/core/test_catalog_determinism.py` | modified — +367 lines |
| `scripts/generate_catalog.py` | modified — +60 lines |
| `handoffs/2026-08-11-registry-plugin-load-transaction.md` | new |

**C. Shared between A and B**

| Path | State |
|---|---|
| `src/core/modules/registry/core.py` | modified — +956 lines. Carries B's pass-record transaction **and** A's `capability_snapshot()` / `_generation`. Cannot be assigned to one change. |

**D. Config, project memory, generated docs**

`.flyto/coding.yaml` (lint argv widened by A) · `ARCHITECTURE.md` ·
`CHANGELOG.md` · `DECISIONS.md` · `STATE.md` · `tasks.md` ·
`handoffs/_registry.md` · `docs/TESTING.md` (lint argv mirrored) ·
`docs/CLI.md` · `docs/FEATURES.md` · `docs/MIGRATION_STATUS.md` ·
`docs/README.md` · `docs/TOOL_CATALOG.md` · `docs/WHITEPAPER.md` ·
`docs/reference/http-api.md` · `docs/reference/python-api.md` ·
`docs/reference/source-modules.md`

### Why the ledger still was not filed

Same fail-closed reasoning as session 4, one blocker down and one to go. The
diff is now known, but `task(action='plan')` is ungranted, so there is no way to
*file* a ledger — and a ledger is the Indexer's artifact, not a Markdown table.
Writing the list above into prose is the part that can be done without the tool;
it is explicitly **not** a substitute for the planned ledger.

**Next agent: this needs `mcp__flyto-indexer__task` and
`mcp__flyto-indexer__verify` granted, plus any route that runs a `checks:` entry.
With those, the ledger is a mechanical transcription of the 30 paths above.**

## Risks for whoever picks this up

Ranked by how likely I think they are to bite, given none of this has run.

0. **A missed generation bump.** The counter is instrumented at seven call
   sites by hand. If some other path mutates `_modules`, `_metadata` or
   `_plugins` without going through one of them, two different registry states
   can share a generation and the cache falls back to last-store-wins for that
   pair. That is the current behaviour, not a new break, but it is where this
   fix is incomplete rather than wrong. A future refactor should route all
   writes through one choke point instead.
1. **The concurrency tests.** `test_concurrent_get_and_refresh_never_tears`
   still uses a 2s wall-clock window; under a contended CI box it may be slow
   rather than flaky, but if it *hangs* rather than fails, the lock invariant
   has regressed — check that nothing holds `_cache_lock` across a build.
   `test_plugin_reentrant_manifest_call_does_not_deadlock` is the canary for
   exactly that and should fail first.
2. **The reentrancy test's ordering.** It uses events to drive thread B into
   its build before the plugin re-enters, which makes correct code always pass
   and broken code reliably hang — but the window is enforced by
   `b_started.wait(timeout=5)`, not by a hard barrier, so a pathological
   scheduler could let broken code slip through. It cannot produce a false
   *failure*, only a false pass.
3. **Registry fixture semantics.** `_reset_registry()` sets `_pass_registered`
   and `_pass_touched` to `None` because `clear()` tests `is not None` to decide
   whether it is mid-pass. If other registry internals also treat "empty" and
   "absent" differently, this helper is where that surfaces.
4. Test metadata bypasses `build_module_metadata`, so `stability`, `ui_label`
   and `ui_description` are set by hand. If catalog search scores on a field I
   missed, `test_detail_and_search_expose_plugin_modules` fails.
5. `_mcp_payload` unwraps the modern-vs-legacy JSON-RPC envelope heuristically;
   only the legacy (`modern=False`) path is actually exercised.
6. The I001 fix assumes ruff classifies `core` as first-party via its default
   `src` detection. If it classifies it as third-party instead, the correct
   order differs and ruff will say so.
