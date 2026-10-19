# Step outcome reasons, the browser session contract, exclusive params

Owner: claude
Branch: lane/editor-step-display-core (on core-integ 16dae8a)
Date: 2026-10-19

## What changed

Three contracts the Cloud workflow editor reads (its gaps G-12, G-13, G-15):

- **A failure's reason travels as data.**
  - `engine/exceptions.py`: `StepExecutionError.error_code`, and
    `error_code_from_exception()`, which walks `original_error` and
    `__cause__` (never `__context__`).
  - `engine/step_executor/executor.py`: a module failure passes the code
    the module returned. Before, the code existed only inside
    "Module returned failure [CODE]: ...".
  - `engine/outcome.py`: `OutcomeError(code=...)`.
  - `modules/atomic/browser/wait.py`: a timeout raises `code='TIMEOUT'`
    beside `rung=INDETERMINATE`.
  - `engine/step_executor/context_builder.py`: hooks read the code from
    `HookContext.metadata['error_code']`. It is absent when the raise named
    none. Nothing is guessed from an exception's type or text.
- **The browser session contract.**
  - `modules/types/context.py`: the `browser` category now requires a
    `browser` context by default and provides none.
    `CONTEXT_ESTABLISHERS = {browser, page: 'browser.launch'}` lists which
    contexts are sessions, and which module to offer for each.
  - `browser.launch`, `.connect`, `.ensure`, `.pool` and `.proxy_rotate`
    declare `requires_context=[]` and `provides_context=['browser', 'page']`.
  - `browser.release` declares `requires_context=[]`.
  - `validation/workflow.py`: a step whose required session no upstream
    step provides is refused as `CONTEXT_NOT_ESTABLISHED`, with
    `meta.context`, `meta.missing` and `meta.establish_with`.
  - "Upstream" follows the edges. Without edges it follows list order, as
    the engine runs.
  - `validate_workflow(..., context_edges=)` lets a host pass the lines a
    step runs after when it validates fewer control-flow edges (iterate
    edges).
- **Exclusive params.**
  - The field key `exclusive_with` names the fields that, once set, make
    this one unused. `presets.DURATION_MS` passes extra keys through.
  - `browser.wait` declares `duration_ms` with `exclusive_with=['selector']`.
  - `validate_node_params` refuses both set as `PARAMS_EXCLUSIVE` on the
    ruled-out field, with `meta.param` and `meta.ruled_out_by`.
- The generated reference was regenerated, and the inventory tokens were
  updated: 6,820 declarations, 246,887 lines.

## Why

These are the owner's rules. The outcome of a step comes from the envelope
and typed codes, never from message text. A rule is a contract, not a module
name.

A rule keyed on `browser.*` was rejected. Validation reads
`requires_context` / `provides_context`; the test
`test_the_rule_is_read_from_the_contract_not_from_the_module_name` proves
it with a vendor-named module.

## Verified

- Failing first (`<scratchpad>/round10/sd-failfirst-core.txt`):
  - `test_session_context_contract.py` and `test_failure_reason_code.py`
    did not collect (`CONTEXT_ESTABLISHERS` and `error_code_from_exception`
    were missing).
  - `test_exclusive_params.py`: 4 failed, 1 passed.
  - After the change: 25 passed.
- `pytest -m 'not browser'`:
  - 6,526 passed, 74 failed, 158 skipped.
  - 63 of the failures were `tests/test_hints.py`, which needs
    `node_modules` that this new worktree lacked. After `npm ci
    --ignore-scripts` it passes.
  - The other 11 fail identically on core-integ 16dae8a:
    `test_reverse_code` (7), `test_ci_dependency_tooling`,
    `test_verification_packaging`,
    `test_pack_hardening::test_second_provider_with_the_same_contract_is_allowed`,
    and `test_outcome_declaration_coverage::...names_no_module_that_does_not_exist`
    (robotics modules not registered here).
- `generate_reference.py --check`: PASS. `generate_catalog.py --check`:
  PASS. `check_documentation.py`: PASS. `check_brand_identity.py`: PASS.
  `lint-project-memory.sh`: PASS.
- Ruff: no new findings on the changed files (per-file counts equal to
  base).
- 49 browser workflows in flyto-cloud, flyto-core and flyto-modules-pro
  (`workflows/`, `examples/`, `src/`, `tests/`): none is newly refused by
  the session contract, and none sets both wait fields.
- A real headless-Chromium `browser.wait` timeout, run through the engine
  with Cloud's `StepTrackingHooks`, reached Cloud as
  `{"rung": "indeterminate", "reason_code": "TIMEOUT"}` (Cloud handoff).
- Strict verify: see the Cloud handoff's report for this lane.

## Not verified

- CI and a release. Cloud's pin must move to this branch for Cloud's new
  tests (they skip on an older core).
- Modules outside this repository (packs, flyto-modules-pro) in the
  `browser` category now require a session by default. One that opens a
  session must declare `provides_context`.
- A workflow that only ever runs on a browser handed in by its caller (a
  sub-workflow, a local continuation) is now refused at save. Its remedy is
  `browser.ensure`, which reuses the session it is given.
- A duration-only `browser.wait` with no launch before it is also refused.
  The requirement is per module, not per param.

## Follow-ups

- Cloud: lane/editor-step-display reads all three contracts.
- Other modules whose params rule each other out can declare
  `exclusive_with` now.
