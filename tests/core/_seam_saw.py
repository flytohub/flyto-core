# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The saw: cut one load-bearing connection, on purpose, by name.

A unit test asks whether a function returns. That is not the question that has
been failing. Every defect this project found in the 2026-08-30 audit and in the
two rounds since was a *seam* — two parts each correct alone, connected wrongly
or not at all — and unit tests are blind to seams by construction. The measured
case: a merge analysis stacked two Escape listeners on one element, and both
sides' suites passed 7/7 and 6/6. Broken integration, everything green.

So this file is a saw, and ``test_severed_seams.py`` is the check that the
alarms are wired. Each entry below names one connection, describes how to cut
it, and names the tests that must go red when it is cut. The harness cuts it in
a subprocess and requires those tests to fail. A seam whose tests still pass is
not covered — the alarm is decorative — and that is a failure of this suite.

Two rules keep it honest:

  * A cut must be a real severing, not a sabotage. Replacing a function with
    ``raise AssertionError`` proves nothing: every test would fail, including
    ones that never depended on the seam. Each cut here restores the *previous,
    plausible* behaviour — the code as it was before the fix, or the obvious
    thing a future author would write without knowing why.

  * A cut must be reachable through the public path. Reaching into a private
    attribute the production code never sets would test the saw, not the seam.

Adding a fix without adding its seam here is how the next regression gets in:
the fix works today, nothing says why it must keep working, and the test that
covers it is one refactor away from being deleted as redundant.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, NamedTuple


ENV_VAR = "FLYTO_SEVER_SEAM"


class Seam(NamedTuple):
    """One load-bearing connection, and the alarm that must be on it."""

    name: str
    #: What the connection carries, in one sentence a person can check.
    carries: str
    #: Restore the pre-fix behaviour. Takes a monkeypatch-like `setattr`.
    cut: Callable[[], None]
    #: Node ids that MUST fail once it is cut.
    guarded_by: List[str]


def _cut_capability_gate_in_the_mode_dispatcher() -> None:
    """Put the gate back inside `run()` only, where items/all never reach it."""
    from core.engine.step_executor import executor

    original = executor.StepExecutor._execute_module

    async def without_the_gate(self, step_id, module_id, params, context, **kwargs):
        from core.modules.registry import ModuleRegistry

        module_class = ModuleRegistry.get(module_id)
        if not module_class:
            return await original(self, step_id, module_id, params, context, **kwargs)
        instance = module_class(params, context)
        mode = getattr(instance, "execution_mode", "single")
        if mode == "items":
            return await self._execute_items_mode(
                step_id, instance, params, kwargs.get("input_items"), kwargs.get("step_trace")
            )
        if mode == "all":
            return await self._execute_all_mode(step_id, instance, kwargs.get("input_items"))
        return await original(self, step_id, module_id, params, context, **kwargs)

    executor.StepExecutor._execute_module = without_the_gate


def _cut_the_per_item_outcome_walk() -> None:
    """Restore the walk that read only the result and a dict-shaped `data`.

    The aggregate an items-mode module returns has a *list* under `data`, so the
    old `isinstance(data, dict)` skipped it and every per-item outcome beneath
    was invisible.
    """
    from core.engine.step_executor import executor

    def only_the_top_and_a_dict_data(result: Any) -> List[Dict[str, Any]]:
        payloads: List[Dict[str, Any]] = []
        candidates = result if isinstance(result, (list, tuple)) else [result]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            payloads.append(candidate)
            data = candidate.get("data")
            if isinstance(data, dict):
                payloads.append(data)
        return payloads

    executor._outcome_payloads = only_the_top_and_a_dict_data


def _cut_the_declaration_ceiling() -> None:
    """Let a module claim `verified` with no postcondition declared."""
    from core.engine import outcome
    from core.engine.step_executor import executor

    executor.ceiling_for = lambda declared: outcome.Outcome.VERIFIED


def _cut_the_legacy_reporter_check() -> None:
    """Stamp the default over a module that reported the legacy way.

    The check used to ask only `read_envelope`, so a default `dispatched` landed
    beside browser.click's `verification_status` and masked it.
    """
    from core.engine.step_executor import executor

    executor._payload_outcome = lambda payload: None


def _cut_the_empty_read_rung() -> None:
    """Claim OBSERVED for a read that returned no rows.

    `len(rows) == 0` reads the same whether a statement matched nothing, changed
    five rows and returned no result set, or was discarded entirely.
    """
    from core.engine.outcome import ClaimBy, Outcome, envelope
    from core.modules.atomic.database import query

    def always_observed(backend, fetch_mode, row_count):
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{"kind": "rows_returned", "count": row_count}],
        )

    query._returned_rows = always_observed


def _cut_the_read_path_commit() -> None:
    """Close the sqlite connection without committing, as it used to.

    A write run through the default `fetch='all'` then opens sqlite's implicit
    DML transaction and is rolled back on close, while the module reports ok.

    Cut at ``sqlite3.connect`` -- a module attribute, and assignable -- rather
    than at ``sqlite3.Connection.commit``, which CPython refuses because the
    type is immutable. The first version of this cut did exactly that, died in
    ``pytest_configure``, and the harness -- which then only checked the exit
    code -- recorded the crash as "the alarm fired" while nothing had run. That
    is why ``test_severed_seams.py`` now reads the child's tally instead.

    Not at the module object ``query`` reaches, either: ``import sqlite3`` sits
    inside the function (query.py:494), so a module-level substitution is
    shadowed by the local import every time.
    """
    import sqlite3

    original_connect = sqlite3.connect

    class _NeverCommits:
        """Everything the module does, minus the commit that keeps the data."""

        def __init__(self, real):
            object.__setattr__(self, "_real", real)

        def commit(self):
            return None

        def __getattr__(self, name):
            return getattr(object.__getattribute__(self, "_real"), name)

        def __setattr__(self, name, value):
            # `conn.row_factory = sqlite3.Row` has to reach the real thing.
            setattr(object.__getattribute__(self, "_real"), name, value)

        def __enter__(self):
            return object.__getattribute__(self, "_real").__enter__()

        def __exit__(self, *exc):
            return object.__getattribute__(self, "_real").__exit__(*exc)

    sqlite3.connect = lambda *a, **k: _NeverCommits(original_connect(*a, **k))


def _cut_the_content_length_guard() -> None:
    """Parse a peer-controlled Content-Length without a guard."""
    from core.modules.atomic.http import request

    def unguarded(content_length_header, body_content):
        if content_length_header:
            return int(content_length_header)
        return len(
            body_content if isinstance(body_content, (str, bytes)) else str(body_content)
        )

    request._compute_content_length = unguarded


def _cut_the_off_ladder_precedence() -> None:
    """Average an off-ladder answer away instead of letting it win.

    `failed` and `indeterminate` are not low rungs. Treating them as the bottom
    of the ladder lets one verified sibling bury them.
    """
    from core.engine.step_executor import executor

    original = executor.step_outcome

    def weakest_by_position(result):
        found = original(result)
        if found is None:
            return None
        rung = found[0]
        if executor.is_on_ladder(rung):
            return found
        # The plausible wrong thing: treat them as the lowest rung and let a
        # min() over positions pick a real rung instead.
        payloads = [
            executor._payload_outcome(payload)
            for payload in executor._outcome_payloads(result)
        ]
        on_ladder = [p for p in payloads if p is not None and executor.is_on_ladder(p[0])]
        return on_ladder[0] if on_ladder else found

    executor.step_outcome = weakest_by_position


SEAMS: List[Seam] = [
    Seam(
        name="capability-gate-in-mode-dispatcher",
        carries=(
            "every module execution reaches enforce_module_policy, whatever "
            "execution_mode the module declares"
        ),
        cut=_cut_capability_gate_in_the_mode_dispatcher,
        guarded_by=["tests/core/test_policy_chokepoint_execution_mode.py"],
    ),
    Seam(
        name="per-item-outcome-walk",
        carries=(
            "an outcome reported inside an items-mode aggregate is visible to "
            "the engine"
        ),
        cut=_cut_the_per_item_outcome_walk,
        guarded_by=[
            "tests/core/test_step_outcome_reading.py::TestWhatTheEngineCanSee",
            "tests/core/test_step_outcome_reading.py::TestWhatDegradesAStep",
        ],
    ),
    Seam(
        name="declaration-ceiling",
        carries="verified requires a declared postcondition to have been evaluated",
        cut=_cut_the_declaration_ceiling,
        guarded_by=["tests/core/test_step_outcome_reading.py::TestTheCeiling"],
    ),
    Seam(
        name="legacy-reporter-not-overwritten",
        carries=(
            "the default stamp does not land on a module that already reported "
            "through verification_status"
        ),
        cut=_cut_the_legacy_reporter_check,
        guarded_by=[
            "tests/core/test_step_outcome_reading.py::TestTheDefaultRule",
            "tests/modules/test_browser_click_semantics.py",
        ],
    ),
    Seam(
        name="empty-read-is-not-an-observation",
        carries="a row_count of zero is not evidence that anything was seen",
        cut=_cut_the_empty_read_rung,
        guarded_by=["tests/core/test_database_query_outcome.py"],
    ),
    Seam(
        name="read-path-commit",
        carries="a write run through the default fetch mode is not rolled back",
        cut=_cut_the_read_path_commit,
        guarded_by=["tests/core/test_database_query_outcome.py::TestSqliteReads"],
    ),
    Seam(
        name="content-length-guard",
        carries=(
            "a peer-controlled Content-Length cannot turn a successful response "
            "into a step failure"
        ),
        cut=_cut_the_content_length_guard,
        guarded_by=["tests/core/test_http_request_outcome.py"],
    ),
    Seam(
        name="off-ladder-precedence",
        carries="failed and indeterminate are not averaged away by a verified sibling",
        cut=_cut_the_off_ladder_precedence,
        guarded_by=["tests/core/test_step_outcome_reading.py::TestOffLadderAnswersWinOutright"],
    ),
]

BY_NAME: Dict[str, Seam] = {seam.name: seam for seam in SEAMS}


# ---------------------------------------------------------------------------
# pytest plugin half: applied inside the subprocess the harness spawns.
# ---------------------------------------------------------------------------

def pytest_configure(config):  # pragma: no cover - runs only in the child
    name = os.environ.get(ENV_VAR)
    if not name:
        return
    seam = BY_NAME.get(name)
    if seam is None:
        raise SystemExit(f"unknown seam: {name!r}")
    seam.cut()
