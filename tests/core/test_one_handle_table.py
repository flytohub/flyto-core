"""One table says what a canvas handle means, and validation and the engine both read it.

The canvas names an edge's ends by handle id: a generic ``output``/``target``
pair on most nodes, ``source-<port>`` on named exits, ``body_out``/``done_out``
on loops. Connection validation (``core/validation/connection.py``) and the
engine's router (``core/engine/workflow/routing.py``) each kept their own alias
table for those ids, and they disagreed: validation read ``output`` as the
module's one ordinary port, the router read it as an event literally named
``output`` that no module emits. A saved edge out of the trigger or a merge
was then accepted by one and silently not followed by the other (the run fell
through to the next step in list order).

These tests hold both readers to the same answer for every port of every
registered module, and pin that neither keeps a table of its own.
"""

import ast
from pathlib import Path

import pytest

from core.engine.workflow.routing import WorkflowRouter
from core.modules import atomic  # noqa: F401
from core.modules.registry import ModuleRegistry
from core.validation.connection import validate_connection
from core.validation.errors import ErrorCode

SRC = Path(__file__).resolve().parents[2] / "src" / "core"


def _declared_output_ports():
    rows = []
    for module_id in sorted(ModuleRegistry.list_all()):
        meta = ModuleRegistry.get_metadata(module_id) or {}
        ports = [p for p in meta.get("output_ports") or [] if isinstance(p, dict) and p.get("id")]
        ordinary = [p for p in ports if p["id"] != "error"]
        for port in ports:
            handles = {port.get("handle_id") or port["id"]}
            if len(ordinary) == 1 and port is ordinary[0]:
                handles.add("output")  # the generic handle every canvas node draws
            for handle in sorted(handles):
                rows.append((module_id, port["id"], port.get("event") or port["id"], handle))
    return rows


OUTPUT_ROWS = _declared_output_ports()


def _route(module_id, handle, event):
    """Index of the step the engine runs after ``a`` emits ``event`` with an edge a -(handle)-> b."""
    steps = [
        {"id": "a", "module": module_id},
        {"id": "between", "module": "data.json.parse"},
        {"id": "b", "module": "data.json.parse"},
    ]
    router = WorkflowRouter()
    router.build_step_index(steps)
    router.build_edge_index([{"source": "a", "target": "b", "sourceHandle": handle, "targetHandle": "target"}], steps)
    return router.get_next_step_index("a", {"__event__": event}, 0)


def test_the_catalog_declares_ports_to_check():
    assert len(OUTPUT_ROWS) > 50


@pytest.mark.parametrize(
    ("module_id", "port_id", "event", "handle"),
    [row for row in OUTPUT_ROWS if row[1] != "error"],
    ids=lambda value: str(value),
)
def test_the_engine_follows_every_edge_validation_accepts(module_id, port_id, event, handle):
    accepted = validate_connection(module_id, "data.json.parse", from_port=handle, to_port="target")
    assert accepted.error_code != ErrorCode.PORT_NOT_FOUND, accepted.error_message

    assert _route(module_id, handle, event) == 2, (
        f"{module_id} emitted {event!r} through port {port_id!r}; the edge drawn from "
        f"handle {handle!r} was accepted at save but the engine fell through to the next step"
    )


@pytest.mark.parametrize("module_id", ["flow.trigger", "flow.merge"])
def test_the_generic_output_handle_routes_the_one_ordinary_port(module_id):
    meta = ModuleRegistry.get_metadata(module_id)
    (ordinary,) = [p for p in meta["output_ports"] if p["id"] != "error"]

    assert _route(module_id, "output", ordinary.get("event") or ordinary["id"]) == 2


def test_an_error_edge_still_routes_the_error_event():
    assert _route("flow.trigger", "source-error", "error") == 2


def test_a_named_branch_exit_still_routes_only_its_own_event():
    assert _route("flow.branch", "source-true", "true") == 2
    assert _route("flow.branch", "source-true", "false") == 1


def test_validation_and_the_engine_import_the_one_table():
    from core import canvas_handles
    from core.engine.workflow import routing
    from core.validation import connection

    assert connection.resolve_port is canvas_handles.resolve_port
    assert routing.handle_events is canvas_handles.handle_events


@pytest.mark.parametrize("relative", ["validation/connection.py", "engine/workflow/routing.py"])
def test_neither_reader_keeps_its_own_alias_table(relative):
    tree = ast.parse((SRC / relative).read_text(encoding="utf-8"))
    literals = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        and any(isinstance(k, ast.Constant) and k.value in {"output", "main", "body_out", "target"} for k in node.keys)
    ]
    assert not literals, f"{relative} still defines a handle alias table at line {literals[0].lineno}"
