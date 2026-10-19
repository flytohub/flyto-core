"""A fork runs every branch in a defined order, and a merge joins them by its declared inputs.

flow.fork's contract: its branch exits run one after another in exit order
(branch_1 first), each branch until it ends or reaches a join; then the run
continues at the join. A branch that fails ends the run with that failure and
later branches do not start. flow.merge receives each incoming edge's value on
the input port that edge was drawn to (input_1, input_2).

Before: the engine followed only the first branch (the router kept one route
per event), a merge never received its inputs ("No inputs received"), and a
step at the end of one branch stepped on in list order into the next branch.
"""

import pytest

from core.engine.exceptions import WorkflowExecutionError
from core.engine.workflow.engine import WorkflowEngine
from core.modules import atomic  # noqa: F401
from core.modules.registry import ModuleRegistry


@pytest.fixture
def ran(monkeypatch):
    seen = []
    module_class = ModuleRegistry.get("string.uppercase")
    original = module_class.execute

    async def execute(self):
        text = self.params.get("text")
        seen.append(text)
        if text == "boom":
            raise RuntimeError("branch failed")
        return await original(self)

    monkeypatch.setattr(module_class, "execute", execute)
    return seen


def _step(step_id, text=None):
    return {"id": step_id, "module": "string.uppercase", "params": {"text": text or step_id}}


def _edge(source, target, source_handle="output", target_handle="target"):
    return {"id": f"{source}->{target}", "source": source, "target": target,
            "sourceHandle": source_handle, "targetHandle": target_handle}


def _fork_workflow(first="a1", second="b1"):
    return {
        "steps": [
            {"id": "fork", "module": "flow.fork", "params": {"branch_count": 2}},
            _step("a1", first), _step("a2"),
            _step("b1", second), _step("b2"),
            {"id": "join", "module": "flow.merge", "params": {"strategy": "all", "input_count": 2}},
            _step("after"),
        ],
        "edges": [
            _edge("fork", "a1", "source-branch_1"), _edge("a1", "a2"), _edge("a2", "join", "output", "target-input_1"),
            _edge("fork", "b1", "source-branch_2"), _edge("b1", "b2"), _edge("b2", "join", "output", "target-input_2"),
            _edge("join", "after"),
        ],
    }


@pytest.mark.asyncio
async def test_a_fork_runs_each_branch_in_exit_order_then_the_join(ran):
    engine = WorkflowEngine(_fork_workflow(), {})
    await engine.execute()

    assert ran == ["a1", "a2", "b1", "b2", "after"]
    merged = engine.context["join"]
    assert len(merged["outputs"]["output"]["merged_data"]) == 2


@pytest.mark.asyncio
async def test_a_failing_branch_ends_the_run_and_later_branches_do_not_start(ran):
    with pytest.raises(WorkflowExecutionError, match="branch failed"):
        await WorkflowEngine(_fork_workflow(first="boom"), {}).execute()

    assert ran == ["boom"]


@pytest.mark.asyncio
async def test_a_branch_of_several_steps_does_not_step_into_the_other_branch(ran):
    workflow = {
        "steps": [
            {"id": "if", "module": "flow.branch", "params": {"condition": "1 > 0"}},
            _step("y1"), _step("y2"), _step("n1"), _step("n2"),
        ],
        "edges": [
            _edge("if", "y1", "source-true"), _edge("y1", "y2"),
            _edge("if", "n1", "source-false"), _edge("n1", "n2"),
        ],
    }

    await WorkflowEngine(workflow, {}).execute()

    assert ran == ["y1", "y2"]


@pytest.mark.asyncio
async def test_an_edge_drawn_without_a_handle_takes_the_first_free_input(ran):
    workflow = _fork_workflow()
    for edge in workflow["edges"]:
        if edge["targetHandle"] == "target-input_1":
            edge.pop("targetHandle")

    engine = WorkflowEngine(workflow, {})
    await engine.execute()

    assert len(engine.context["join"]["outputs"]["output"]["merged_data"]) == 2
