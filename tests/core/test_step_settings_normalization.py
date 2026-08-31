# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Legacy execution-setting spellings on stored steps.

The template builder's settings panel once wrote camelCase keys (`onError`,
`runIf`, `foreachAs`) while the engine has only ever read the canonical ones
(`on_error`, `when`, `as`). The panel was fixed to write canonical, but the
reader was never taught the old spelling and saved templates were never
migrated — so every template written before that fix kept parsing cleanly and
silently ignoring its own execution settings. A step saying
`onError: continue` behaved as `stop`.

The engine normalises once, where a stored step list enters execution, so all
five downstream readers see the canonical key. These tests use the shape the
owner's saved runs actually carry:

    {"id": "save_report", "module": "file.write", "onError": "continue"}
"""

import copy

import pytest

from core.engine.exceptions import WorkflowExecutionError
from core.engine.flow_control import (
    LEGACY_STEP_SETTING_KEYS,
    normalize_step_settings,
    normalize_step_settings_list,
)
from core.engine.workflow import WorkflowEngine
from core.modules import atomic  # noqa: F401 — registers production modules

# A step that fails at runtime: divide by zero.
FAILING_STEP = {
    "id": "boom",
    "module": "math.calculate",
    "params": {"operation": "divide", "a": 5, "b": 0},
}
FOLLOWING_STEP = {
    "id": "after",
    "module": "string.uppercase",
    "params": {"text": "ran"},
}


# ---------------------------------------------------------------------------
# The normaliser itself
# ---------------------------------------------------------------------------

class TestNormaliser:
    def test_adds_canonical_key(self):
        assert normalize_step_settings({"onError": "continue"})["on_error"] == "continue"
        assert normalize_step_settings({"runIf": "${a}"})["when"] == "${a}"
        assert normalize_step_settings({"foreachAs": "row"})["as"] == "row"

    def test_does_not_mutate_the_caller(self):
        """The step may be a stored template definition held by the caller.

        This is the same failure mode as the credential_resolver defect: an
        in-place edit of a shared definition is visible to every other holder
        of it, including the sinks that serialise it back out.
        """
        stored = {"id": "s", "module": "file.write", "onError": "continue"}
        before = copy.deepcopy(stored)

        result = normalize_step_settings(stored)

        assert stored == before
        assert result is not stored
        assert "on_error" in result

    def test_canonical_spelling_wins_when_both_present(self):
        both = {"on_error": "stop", "onError": "continue"}
        assert normalize_step_settings(both)["on_error"] == "stop"

    def test_legacy_key_is_kept_alongside_the_canonical_one(self):
        """Additive only — nothing that echoes the step config loses a field."""
        result = normalize_step_settings({"onError": "continue"})
        assert result["onError"] == "continue"

    def test_untouched_step_is_passed_through_unchanged(self):
        step = {"id": "s", "on_error": "continue"}
        assert normalize_step_settings(step) is step

    def test_list_helper_preserves_order_and_length(self):
        steps = [{"onError": "continue"}, {"id": "b"}]
        out = normalize_step_settings_list(steps)
        assert len(out) == 2
        assert out[0]["on_error"] == "continue"
        assert out[1] is steps[1]

    def test_timeout_ms_is_deliberately_not_aliased(self):
        """`timeoutMs` is milliseconds; the engine's `timeout` is seconds.

        The settings panel maps timeoutMs -> timeout, but the engine hands
        `timeout` straight to asyncio.wait_for and StepTimeoutError reports it
        as seconds. Aliasing the names would reinterpret a 30000 ms budget as
        30000 seconds — an 8-hour hang where there is currently no timeout at
        all. That pair needs a unit conversion agreed with the frontend, not a
        rename, so it must stay out of this table.
        """
        assert "timeoutMs" not in LEGACY_STEP_SETTING_KEYS
        assert "timeout" not in normalize_step_settings({"timeoutMs": 30000})


# ---------------------------------------------------------------------------
# End to end, through the engine boundary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestEngineHonoursLegacySpellings:
    @pytest.mark.parametrize("key", ["on_error", "onError"])
    async def test_continue_lets_the_workflow_carry_on(self, key):
        steps = [{**FAILING_STEP, key: "continue"}, dict(FOLLOWING_STEP)]
        engine = WorkflowEngine(workflow={"steps": steps}, initial_context={})

        await engine.execute()

        assert "after" in engine.context, (
            f"step spelled {key!r} did not continue past the failure"
        )

    @pytest.mark.parametrize("key", ["on_error", "onError"])
    async def test_stop_is_still_the_default_behaviour(self, key):
        """The alias must not turn every step into 'continue'."""
        steps = [{**FAILING_STEP, key: "stop"}, dict(FOLLOWING_STEP)]
        engine = WorkflowEngine(workflow={"steps": steps}, initial_context={})

        with pytest.raises(WorkflowExecutionError):
            await engine.execute()

        assert "after" not in engine.context

    @pytest.mark.parametrize("key", ["when", "runIf"])
    async def test_false_condition_skips_the_step(self, key):
        steps = [{
            "id": "gated",
            "module": "string.uppercase",
            "params": {"text": "x"},
            key: "1 == 2",
        }]
        engine = WorkflowEngine(workflow={"steps": steps}, initial_context={})

        await engine.execute()

        assert engine.context.get("gated") is None

    @pytest.mark.parametrize("key", ["when", "runIf"])
    async def test_true_condition_still_runs_the_step(self, key):
        steps = [{
            "id": "gated",
            "module": "string.uppercase",
            "params": {"text": "x"},
            key: "1 == 1",
        }]
        engine = WorkflowEngine(workflow={"steps": steps}, initial_context={})

        await engine.execute()

        assert engine.context["gated"]["data"]["result"] == "X"

    @pytest.mark.parametrize("key", ["as", "foreachAs"])
    async def test_foreach_binds_the_named_loop_variable(self, key):
        steps = [{
            "id": "loop",
            "module": "string.uppercase",
            "params": {"text": "${row}"},
            "foreach": ["a", "b"],
            key: "row",
        }]
        # A non-empty initial context: VariableResolver does `context or {}`,
        # so an empty dict would be replaced by a fresh one and the foreach
        # variable would never reach the resolver.
        engine = WorkflowEngine(
            workflow={"steps": steps},
            initial_context={"__seed__": 1},
        )

        await engine.execute()

        assert [r["data"]["result"] for r in engine.context["loop"]] == ["A", "B"]

    async def test_stored_workflow_is_not_rewritten(self):
        """Execution understands both spellings; it does not migrate the data.

        The owner's saved templates must come back out of a run in exactly the
        shape they went in — the engine is not allowed to write its preferred
        spelling back into them.
        """
        steps = [{**FAILING_STEP, "onError": "continue"}, dict(FOLLOWING_STEP)]
        workflow = {"steps": steps}
        before = copy.deepcopy(workflow)

        engine = WorkflowEngine(workflow=workflow, initial_context={})
        await engine.execute()

        assert workflow == before
        assert "on_error" not in workflow["steps"][0]


# ---------------------------------------------------------------------------
# The composite boundary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCompositeHonoursLegacySpellings:
    @staticmethod
    def _register(monkeypatch, steps):
        from core.modules.composite.base.module import CompositeModule
        from core.modules.composite.base.registry import CompositeRegistry

        module_id = "test.legacy_spelling_composite"

        class _Composite(CompositeModule):
            pass

        _Composite.module_id = module_id

        monkeypatch.setitem(
            CompositeRegistry._metadata,
            module_id,
            {"steps": steps, "params_schema": {}},
        )
        monkeypatch.setitem(CompositeRegistry._composites, module_id, _Composite)
        return _Composite

    @pytest.mark.parametrize("key", ["on_error", "onError"])
    async def test_continue_lets_the_composite_carry_on(self, monkeypatch, key):
        steps = [{**FAILING_STEP, key: "continue"}, dict(FOLLOWING_STEP)]
        composite = self._register(monkeypatch, steps)({}, {})

        await composite.execute()

        assert "after" in composite.step_results

    async def test_registered_definition_is_not_rewritten(self, monkeypatch):
        steps = [{**FAILING_STEP, "onError": "continue"}, dict(FOLLOWING_STEP)]
        before = copy.deepcopy(steps)
        composite = self._register(monkeypatch, steps)({}, {})

        await composite.execute()

        assert steps == before
        assert "on_error" not in steps[0]
