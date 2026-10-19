"""A step that needs a session established upstream says so in its contract.

`browser.wait` with a selector, `browser.goto`, `browser.click` and the rest
read `context['browser']` and raise "Browser not launched" when nothing put one
there. Save validation accepted such a document and it failed only at run
time (Cloud gap G-13). The requirement is a contract field the registry
already has -- ``requires_context`` / ``provides_context`` -- and validation
reads it: a step whose required session context no upstream step establishes
is refused with ``CONTEXT_NOT_ESTABLISHED``, naming the context and the module
the contract table names to establish it. Nothing here keys on a module id.
"""

import pytest

from core.modules import atomic  # noqa: F401
from core.modules.registry import ModuleRegistry
from core.modules.types.context import CONTEXT_ESTABLISHERS
from core.validation.errors import ErrorCode
from core.validation.workflow import validate_workflow


def _node(node_id, module_id, **params):
    return {"id": node_id, "module_id": module_id, "params": params}


def _edge(edge_id, source, target):
    return {"id": edge_id, "source": source, "target": target, "sourceHandle": "output", "targetHandle": "target"}


def _refusals(result):
    return [e for e in result.errors if e.code == ErrorCode.CONTEXT_NOT_ESTABLISHED]


def test_a_lone_browser_step_is_refused_with_a_typed_code_naming_the_context():
    nodes = [_node("start", "flow.trigger"), _node("wait", "browser.wait", selector="text=Notices")]
    result = validate_workflow(nodes, [_edge("e1", "start", "wait")], validate_params=False)

    refused = _refusals(result)
    assert [r.path for r in refused] == ["nodes[wait]"]
    assert refused[0].meta["node_id"] == "wait"
    assert refused[0].meta["context"] == "browser"
    assert refused[0].meta["establish_with"] == "browser.launch"
    assert result.valid is False


def test_a_browser_step_after_a_launch_is_accepted():
    nodes = [
        _node("start", "flow.trigger"),
        _node("open", "browser.launch"),
        _node("go", "browser.goto", url="https://example.com"),
        _node("wait", "browser.wait", selector="text=Notices"),
    ]
    edges = [_edge("e1", "start", "open"), _edge("e2", "open", "go"), _edge("e3", "go", "wait")]

    assert _refusals(validate_workflow(nodes, edges, validate_params=False)) == []


def test_a_launch_on_another_branch_does_not_establish_the_session():
    nodes = [
        _node("start", "flow.trigger"),
        _node("open", "browser.launch"),
        _node("go", "browser.goto", url="https://example.com"),
    ]
    # `open` is not upstream of `go`: they are siblings, each reached from nowhere.
    edges = [_edge("e1", "start", "go")]

    assert [r.meta["node_id"] for r in _refusals(validate_workflow(nodes, edges, validate_params=False))] == ["go"]


def test_without_edges_the_steps_run_in_list_order_and_are_read_that_way():
    ordered = [_node("open", "browser.launch"), _node("go", "browser.goto", url="https://example.com")]
    reversed_ = list(reversed(ordered))

    assert _refusals(validate_workflow(ordered, [], validate_params=False)) == []
    assert [r.meta["node_id"] for r in _refusals(validate_workflow(reversed_, [], validate_params=False))] == ["go"]


def test_lineage_edges_count_even_when_the_control_flow_edges_omit_them():
    # A loop body is reached by an iterate edge, which hosts drop from the
    # control-flow edges they validate. The session still reaches the body.
    nodes = [_node("open", "browser.launch"), _node("each", "flow.loop"), _node("go", "browser.goto", url="https://example.com")]
    control = [_edge("e1", "open", "each")]
    lineage = control + [{"id": "e2", "source": "each", "target": "go", "sourceHandle": "source-iterate", "targetHandle": "target"}]

    assert _refusals(validate_workflow(nodes, control, validate_params=False, context_edges=lineage)) == []


def test_the_rule_is_read_from_the_contract_not_from_the_module_name(monkeypatch):
    real = ModuleRegistry.get_metadata

    def contract(module_id):
        if module_id == "vendor.session_reader":
            return {"module_id": module_id, "requires_context": ["browser"], "provides_context": []}
        if module_id == "vendor.session_opener":
            return {"module_id": module_id, "requires_context": [], "provides_context": ["browser", "page"]}
        return real(module_id)

    monkeypatch.setattr(ModuleRegistry, "get_metadata", staticmethod(contract))
    alone = [_node("read", "vendor.session_reader")]
    opened = [_node("open", "vendor.session_opener"), _node("read", "vendor.session_reader")]

    assert [r.meta["node_id"] for r in _refusals(validate_workflow(alone, [], validate_params=False))] == ["read"]
    assert _refusals(validate_workflow(opened, [_edge("e1", "open", "read")], validate_params=False)) == []


@pytest.mark.parametrize("module_id", ["browser.launch", "browser.connect", "browser.ensure", "browser.pool", "browser.proxy_rotate"])
def test_the_modules_that_start_a_session_declare_they_provide_it_and_need_none(module_id):
    meta = ModuleRegistry.get_metadata(module_id)
    assert "browser" in meta["provides_context"]
    assert meta["requires_context"] == []


def test_every_browser_step_that_reads_a_session_declares_it_needs_one():
    providers = {"browser.launch", "browser.connect", "browser.ensure", "browser.pool", "browser.proxy_rotate"}
    # release answers "no browser to release" when none is open.
    tolerant = {"browser.release"}
    browser_modules = [m for m in ModuleRegistry.get_all_metadata() if m.startswith("browser.")]
    assert len(browser_modules) > 40
    for module_id in browser_modules:
        meta = ModuleRegistry.get_metadata(module_id)
        if module_id in providers or module_id in tolerant:
            assert "browser" not in meta["requires_context"], module_id
        else:
            assert "browser" in meta["requires_context"], module_id
            assert "browser" not in meta["provides_context"], module_id


def test_only_contexts_with_an_establisher_are_enforced():
    # DATA and FILE requirements describe inputs, not a session; they are not refused here.
    assert set(CONTEXT_ESTABLISHERS) == {"browser", "page"}
    nodes = [_node("start", "flow.trigger"), _node("calc", "string.uppercase", text="x")]
    assert _refusals(validate_workflow(nodes, [_edge("e1", "start", "calc")], validate_params=False)) == []
