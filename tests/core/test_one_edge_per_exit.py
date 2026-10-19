"""An ordinary exit has at most one edge; choosing, fanning out and joining are explicit.

Two lines from one exit ask a question the workflow never answers: which one
runs? The owner's rule (2026-10-19): a step's ordinary exit, its sole ordinary
port and its error exit each carry at most one edge. Choosing a path is
flow.branch / flow.switch; doing several things at once is flow.fork /
flow.parallel; joining is flow.merge / flow.join through their declared inputs.
A port that truly accepts several edges says so in its contract
(``max_connections``); nothing is decided by a module's name.

Validation refuses the second edge with a typed code, and the engine refuses
to run such a document instead of silently following one of the lines.
"""

import pytest

from core.canvas_handles import exit_edge_conflicts, exit_edge_limit
from core.engine.exceptions import ExitEdgeConflictError
from core.engine.workflow.engine import WorkflowEngine
from core.modules import atomic  # noqa: F401
from core.validation.errors import ErrorCode
from core.validation.workflow import validate_workflow


def _node(node_id, module_id, **params):
    return {"id": node_id, "module_id": module_id, "params": params}


def _edge(edge_id, source, target, source_handle="output", target_handle="target"):
    return {"id": edge_id, "source": source, "target": target, "sourceHandle": source_handle, "targetHandle": target_handle}


NODES = [
    _node("start", "flow.trigger"),
    _node("a", "string.uppercase", text="a"),
    _node("b", "string.uppercase", text="b"),
]


def _codes(result):
    return [e.code for e in result.errors]


def test_a_second_edge_from_an_ordinary_exit_is_refused_with_a_typed_code():
    result = validate_workflow(NODES, [_edge("e1", "start", "a"), _edge("e2", "start", "b")], validate_params=False)

    assert ErrorCode.EXIT_HAS_ONE_EDGE in _codes(result)
    refused = next(e for e in result.errors if e.code == ErrorCode.EXIT_HAS_ONE_EDGE)
    assert refused.path == "edges[e2]"
    assert refused.meta["node_id"] == "start"


def test_the_error_exit_carries_one_edge_too():
    nodes = NODES + [_node("c", "string.uppercase", text="c")]
    edges = [_edge("e1", "start", "a"), _edge("e2", "a", "b", "source-error", "target-top"), _edge("e3", "a", "c", "source-error", "target-top")]

    assert ErrorCode.EXIT_HAS_ONE_EDGE in _codes(validate_workflow(nodes, edges, validate_params=False))


def test_each_exit_of_a_branch_carries_its_own_edge():
    nodes = [_node("start", "flow.trigger"), _node("if", "flow.branch", condition="1 > 0"), _node("a", "string.uppercase", text="a"), _node("b", "string.uppercase", text="b")]
    edges = [_edge("e0", "start", "if"), _edge("e1", "if", "a", "source-true"), _edge("e2", "if", "b", "source-false")]

    assert ErrorCode.EXIT_HAS_ONE_EDGE not in _codes(validate_workflow(nodes, edges, validate_params=False))


def test_a_join_is_two_edges_into_two_declared_inputs():
    nodes = NODES + [_node("join", "flow.merge")]
    edges = [_edge("e1", "a", "join", "output", "target-input_1"), _edge("e2", "b", "join", "output", "target-input_2")]

    assert ErrorCode.EXIT_HAS_ONE_EDGE not in _codes(validate_workflow(nodes, edges, validate_params=False))


def test_a_port_that_accepts_several_edges_says_so_in_its_contract():
    assert exit_edge_limit({"id": "success"}) == 1
    assert exit_edge_limit({"id": "out", "max_connections": 3}) == 3
    assert exit_edge_limit({"id": "out", "max_connections": None}) is None
    edges = [_edge("e1", "s", "a"), _edge("e2", "s", "b")]
    assert exit_edge_conflicts(edges, lambda _: [{"id": "success", "max_connections": None}]) == []
    assert [c["edge_id"] for c in exit_edge_conflicts(edges, lambda _: [{"id": "success"}])] == ["e2"]


@pytest.mark.asyncio
async def test_the_engine_refuses_to_run_two_lines_from_one_exit():
    workflow = {
        "steps": [{"id": n["id"], "module": n["module_id"], "params": n["params"]} for n in NODES],
        "edges": [_edge("e1", "start", "a"), _edge("e2", "start", "b")],
    }

    with pytest.raises(ExitEdgeConflictError) as refused:
        await WorkflowEngine(workflow, {}).execute()

    assert refused.value.code == "EXIT_HAS_ONE_EDGE"
    assert refused.value.conflicts[0]["edge_id"] == "e2"


@pytest.mark.asyncio
async def test_an_edge_and_a_connection_naming_the_same_line_are_one_line():
    workflow = {
        "steps": [
            {"id": "if", "module": "flow.branch", "params": {"condition": "1 > 0"}, "connections": {"true": ["a"]}},
            {"id": "a", "module": "string.uppercase", "params": {"text": "a"}},
        ],
        "edges": [_edge("e1", "if", "a", "source-true")],
    }

    await WorkflowEngine(workflow, {}).execute()
