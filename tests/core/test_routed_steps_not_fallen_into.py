"""A step reached through a routed exit is entered only through that exit.

A canvas workflow is stored as an ordered step list plus routed exits (branch
true/false, a loop's body, an error exit). When a step finished without a
route of its own, the engine stepped to the next step in list order, and that
step was often another exit's target: the true branch ran on into the false
branch, a loop ran its body once more after ``done``, and a step's error
handler ran after it succeeded. The next step in list order is now skipped
while it is the target of another step's routed exit, and the run moves on
to the first step that is not.
"""

import pytest

from core.engine.workflow.engine import WorkflowEngine
from core.modules import atomic  # noqa: F401
from core.modules.registry import ModuleRegistry


@pytest.fixture
def ran(monkeypatch):
    """The ``text`` of every string.uppercase step that ran, in order."""
    seen = []
    module_class = ModuleRegistry.get("string.uppercase")
    original = module_class.execute

    async def execute(self):
        seen.append(self.params.get("text"))
        return await original(self)

    monkeypatch.setattr(module_class, "execute", execute)
    return seen


def _step(step_id, text=None):
    return {"id": step_id, "module": "string.uppercase", "params": {"text": text or step_id}}


def _edge(source, target, handle="output"):
    return {"source": source, "target": target, "sourceHandle": handle, "targetHandle": "target"}


@pytest.mark.asyncio
@pytest.mark.parametrize(("condition", "taken"), [("1 > 0", "yes"), ("1 < 0", "no")])
async def test_an_if_else_runs_only_the_branch_it_took(ran, condition, taken):
    workflow = {
        "steps": [
            {"id": "decide", "module": "flow.branch", "params": {"condition": condition}},
            _step("yes"),
            _step("no"),
            _step("after"),
        ],
        "edges": [
            _edge("decide", "yes", "source-true"),
            _edge("decide", "no", "source-false"),
            _edge("yes", "after"),
            _edge("no", "after"),
        ],
    }

    await WorkflowEngine(workflow, {}).execute()

    assert ran == [taken, "after"]


@pytest.mark.asyncio
async def test_a_loop_runs_its_body_once_per_item_and_not_again_after_done(ran):
    workflow = {
        "steps": [
            {"id": "each", "module": "flow.foreach", "params": {"items": ["a", "b", "c"]}},
            _step("body", "${loop.item}"),
        ],
        "edges": [_edge("each", "body", "body_out")],
    }

    await WorkflowEngine(workflow, {}).execute()

    assert ran == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_an_error_handler_does_not_run_after_its_step_succeeds(ran):
    workflow = {
        "steps": [_step("work"), _step("handler"), _step("next")],
        "edges": [_edge("work", "handler", "source-error"), _edge("work", "next")],
    }

    await WorkflowEngine(workflow, {}).execute()

    assert ran == ["work", "next"]


@pytest.mark.asyncio
async def test_plain_sequences_still_run_in_list_order(ran):
    workflow = {"steps": [_step("one"), _step("two"), _step("three")]}

    await WorkflowEngine(workflow, {}).execute()

    assert ran == ["one", "two", "three"]
