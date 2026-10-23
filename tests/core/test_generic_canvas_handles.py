"""The canvas draws one generic handle per node; it means the module's one ordinary port.

Every canvas node offers a single ``output`` source handle and a single
``target`` handle, whatever the module declares. Validation mapped
``output`` to a port named ``success`` only, so an edge out of a module whose
ordinary output has another name, such as the trigger's ``triggered``, was
refused with "Port not found: output" on every save, while the engine ran the
same edge. A generic handle now resolves to the module's one ordinary port,
read from its declared ports. A module with several ordinary outputs still
needs the edge to name one.
"""

import pytest

from core.modules import atomic  # noqa: F401
from core.validation.connection import validate_connection
from core.validation.errors import ErrorCode


@pytest.mark.parametrize("handle", ["output", "source", None])
def test_an_edge_out_of_the_trigger_by_the_generic_handle_is_valid(handle):
    result = validate_connection("flow.trigger", "data.json.parse", from_port=handle, to_port="target")

    assert result.valid, result.error_message


def test_the_trigger_error_port_is_still_found_by_name():
    assert validate_connection("flow.trigger", "data.json.parse", from_port="source-error").valid


def test_a_module_with_several_ordinary_outputs_still_needs_the_edge_to_name_one():
    result = validate_connection("flow.branch", "data.json.parse", from_port="output")

    assert not result.valid
    assert result.error_code == ErrorCode.PORT_NOT_FOUND


def test_an_unknown_named_port_is_still_refused():
    result = validate_connection("flow.trigger", "data.json.parse", from_port="no-such-port")

    assert not result.valid
    assert result.error_code == ErrorCode.PORT_NOT_FOUND


def test_a_generic_target_handle_reaches_a_module_with_one_input_of_another_name():
    result = validate_connection("data.json.parse", "flow.error_handle", from_port="output", to_port="target")

    assert result.error_code != ErrorCode.PORT_NOT_FOUND, result.error_message
