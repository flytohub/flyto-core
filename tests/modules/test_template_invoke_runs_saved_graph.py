"""A sub-workflow runs as it was drawn: its saved edges reach the inner engine.

A saved workflow keeps its graph as ``steps`` plus ``edges`` (fork branches,
merge inputs). ``template.invoke`` and an agent's template tool built the
inner workflow from ``steps`` alone, so a Fork inside a sub-workflow ran only
its first branch and its merge never received the second input.
"""

import pytest

from core.engine.workflow import WorkflowEngine
from core.modules import atomic  # noqa: F401
from core.modules.registry import ModuleRegistry


@pytest.fixture(autouse=True)
def _allow_template_invoke(monkeypatch) -> None:
    import core.module_policy as module_policy
    from core.module_policy import ModuleFilter

    monkeypatch.delenv("FLYTO_MODULE_DENYLIST", raising=False)
    monkeypatch.setenv("FLYTO_MODULE_ALLOWLIST", "template.*,string.*,flow.*")
    monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())


@pytest.fixture
def ran(monkeypatch):
    seen = []
    module_class = ModuleRegistry.get("string.uppercase")
    original = module_class.execute

    async def execute(self):
        seen.append(self.params.get("text"))
        return await original(self)

    monkeypatch.setattr(module_class, "execute", execute)
    return seen


def _edge(source, target, source_handle="output", target_handle="target"):
    return {"id": f"{source}->{target}", "source": source, "target": target,
            "sourceHandle": source_handle, "targetHandle": target_handle}


CHILD = {
    "steps": [
        {"id": "fork", "module": "flow.fork", "params": {"branch_count": 2}},
        {"id": "a", "module": "string.uppercase", "params": {"text": "a"}},
        {"id": "b", "module": "string.uppercase", "params": {"text": "b"}},
        {"id": "join", "module": "flow.merge", "params": {"strategy": "all", "input_count": 2}},
    ],
    "edges": [
        _edge("fork", "a", "source-branch_1"), _edge("a", "join", "output", "target-input_1"),
        _edge("fork", "b", "source-branch_2"), _edge("b", "join", "output", "target-input_2"),
    ],
}


def test_the_inner_workflow_carries_the_definitions_edges():
    from core.modules.atomic.template.invoke import definition_workflow

    assert definition_workflow(CHILD) == {"steps": CHILD["steps"], "edges": CHILD["edges"]}
    assert definition_workflow({"steps": CHILD["steps"]}) == {"steps": CHILD["steps"]}


@pytest.mark.asyncio
async def test_a_fork_inside_a_sub_workflow_runs_both_branches(ran):
    parent = WorkflowEngine(
        workflow={"steps": [{"id": "call", "module": "template.invoke", "params": {"library_id": "child", "template_id": "child"}}]},
        params={},
        initial_context={"template_definitions": {"child": CHILD}},
    )
    await parent.execute()

    assert ran == ["a", "b"]
