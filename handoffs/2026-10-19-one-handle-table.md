# One canvas-handle table; one edge per exit; forks run every branch; merges join by input

Owner: claude
Branch: lane/one-handle-table-r2 (rebased onto core-integ 350a592)
Date: 2026-10-19

## What changed

- `src/core/canvas_handles.py` is the one table that says how a canvas edge
  end is read. It absorbs the generic-handle rule from 240a484, so there is no
  second copy.
  - **Which port a handle means:** the exact id or `handle_id`; then fixed
    aliases; then the handle with its side prefix stripped; then a generic
    handle, which means the module's ordinary port.
  - **Which events an output handle routes under.**
  - **How many edges an exit carries:** `exit_edge_limit` /
    `exit_edge_conflicts`. The default is one; a port that allows more
    declares `max_connections`. The same source, exit and target count as one
    line.
- **Validation:** `validate_workflow` refuses each extra edge with
  `EXIT_HAS_ONE_EDGE`, placed on that edge.
- **Engine:** it refuses such a document before the first step, with
  `ExitEdgeConflictError` (code `EXIT_HAS_ONE_EDGE`).
- **Router** (`engine/workflow/routing.py`):
  - Graph mode: a document with edges is followed along each step's ordinary
    edge, and a path with no edge ends there. A document without edges still
    runs in list order, skipping routed-exit targets.
  - Forks: `start_fork` and `path_end` run every `fork`-event exit in exit
    order, then the join.
  - Merges: `inputs_by_port` hands a joining step (more than one declared
    input) each input's value. An edge that names no input takes the first
    free one.
  - The error-route check reads the declared route instead of comparing
    indexes.
- **`flow/fork.py` contract:** every connected branch runs, one after another
  in exit order, then the run continues at the join. A failing branch stops
  the run, and later branches do not start. Nothing runs concurrently.
- **`flow/trigger.py`:** declares the host settings `timezone`,
  `webhook_provider`, `require_signature` and `triggers`. They are hidden,
  have no default, and hold no secret.

## Why

- Validation and the engine disagreed about handles.
- If/else ran both branches; loops ran one extra time; error handlers ran
  after success.
- Schedule saves were refused.
- The owner's rule: two lines from one exit must be an explicit Fork with
  defined order and failure semantics.
- A Fork ran only its first branch, and a merge never received its inputs.

## Verified

Failing first:

| Test | Before the fix |
| --- | --- |
| `test_one_handle_table` | 471 failed |
| `test_routed_steps_not_fallen_into` | 3 failed |
| `test_one_edge_per_exit` | failed at collection |
| `test_fork_and_join_run` | NO_INPUTS, and the multi-step branch ran `['y1', 'y2', 'n2']` |
| `test_fork_and_join_run`, unnamed join input | 1 failed |
| `test_one_edge_per_exit`, edge and connection to the same target | 1 failed |

The trigger settings are absent on core-integ and present here.

The `tests/core` suite was green after the fork work (3,453 passed). The final
full non-browser suite: 6,528 passed, 0 failed, 192 skipped.

Docs reference, catalog, token sync and memory lint pass. Ruff is clean on the
changed files.

End to end, through the Cloud editor acceptance suite on
lane/editor-acceptance-r2: T01, T03, T04, T07, T08, T26 and T27 pass with this
branch.

## Not verified

- CI on GitHub, and a release. The Cloud pins still name 350a592.
- `registry/resolve.py enrich_port_handle_metadata` derives `handle_id`
  itself. The catalog-wide test holds it to the table's reading, but it does
  not import the table.
- Workflows that relied on implicit behaviour now stop or are refused:
  - falling from a routed target into the next listed step;
  - two lines leaving one exit.

## Follow-ups

- Bump the core pin in flyto-cloud (`test.yml`, `e2e.yml`,
  `mcp-closed-loop.yml`) to this branch in the same round as
  lane/editor-acceptance-r2.
- `flow.parallel` still runs embedded `tasks`, not canvas branches. The Fork is
  the canvas's "run both".
