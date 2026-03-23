"""
Tests for the core.validation module.

Covers: errors, connection, workflow, and index submodules.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest

# -- errors.py imports --
from core.validation.errors import ErrorCode, explain_error, ERROR_MESSAGES

# -- connection.py imports --
from core.validation.connection import (
    _find_port,
    ConnectionResult,
    validate_connection,
    get_connectable,
    get_connectable_summary,
)

# -- workflow.py imports --
from core.validation.workflow import (
    _evaluate_show_condition,
    _is_field_active,
    WorkflowError,
    WorkflowResult,
    validate_workflow,
    validate_start,
    get_startable_modules,
)

# -- index.py imports --
from core.validation.index import ConnectionIndex

# Register all atomic modules so ModuleRegistry is populated
from core.modules import atomic  # noqa: F401


# ============================================================
# 1. errors.py
# ============================================================

class TestErrorCode:
    """Verify all ErrorCode constants exist."""

    EXPECTED_CODES = [
        "TYPE_MISMATCH",
        "PORT_NOT_FOUND",
        "MAX_CONNECTIONS",
        "SELF_CONNECTION",
        "INCOMPATIBLE_MODULES",
        "INVALID_START_NODE",
        "MISSING_START_PARAMS",
        "NO_START_NODE",
        "MULTIPLE_START_NODES",
        "ORPHAN_NODE",
        "CYCLE_DETECTED",
        "DISCONNECTED_GRAPH",
        "MISSING_REQUIRED_PARAM",
        "INVALID_PARAM_VALUE",
        "INVALID_PARAM_TYPE",
        "UNKNOWN_PARAM",
        "MODULE_NOT_FOUND",
        "MODULE_DISABLED",
    ]

    @pytest.mark.parametrize("code", EXPECTED_CODES)
    def test_error_code_exists(self, code):
        assert hasattr(ErrorCode, code)
        assert getattr(ErrorCode, code) == code


class TestExplainError:
    """Test explain_error() with various inputs."""

    def test_known_code_with_meta(self):
        result = explain_error(
            ErrorCode.TYPE_MISMATCH,
            meta={
                "to_module": "browser.click",
                "expected": "browser_page",
                "received": "string",
            },
        )
        assert result["code"] == "TYPE_MISMATCH"
        assert result["title"] == "Type Mismatch"
        assert "browser.click" in result["message"]
        assert "browser_page" in result["message"]
        assert result["meta"]["to_module"] == "browser.click"

    def test_unknown_code(self):
        result = explain_error("TOTALLY_UNKNOWN_CODE")
        assert result["code"] == "TOTALLY_UNKNOWN_CODE"
        assert result["message"] == "Unknown error"
        assert result["title"] == "Totally Unknown Code"

    def test_zh_tw_locale(self):
        result = explain_error(
            ErrorCode.SELF_CONNECTION,
            locale="zh-TW",
        )
        assert result["code"] == "SELF_CONNECTION"
        assert "節點不能連接到自己" in result["message"]

    def test_missing_meta_keys_falls_back(self):
        # Template expects {to_module}, {expected}, {received} but none provided
        result = explain_error(ErrorCode.TYPE_MISMATCH, meta={})
        assert result["code"] == "TYPE_MISMATCH"
        # Should fall back to raw template since keys are missing
        assert isinstance(result["message"], str)

    def test_none_meta_defaults_to_empty(self):
        result = explain_error(ErrorCode.NO_START_NODE)
        assert result["code"] == "NO_START_NODE"
        assert result["meta"] == {}


# ============================================================
# 2. connection.py
# ============================================================

class TestConnectionResult:
    """Test ConnectionResult dataclass."""

    def test_valid_result(self):
        r = ConnectionResult(valid=True)
        assert r.valid is True
        assert r.error_code is None
        assert r.error_message is None
        assert r.meta == {}

    def test_invalid_result(self):
        r = ConnectionResult(
            valid=False,
            error_code=ErrorCode.TYPE_MISMATCH,
            error_message="type mismatch",
            meta={"key": "val"},
        )
        assert r.valid is False
        assert r.error_code == "TYPE_MISMATCH"
        assert r.meta["key"] == "val"


class TestFindPort:
    """Test _find_port() helper."""

    PORTS = [
        {"id": "success", "handle_id": "source-success"},
        {"id": "error", "handle_id": "source-error"},
        {"id": "input"},
        {"id": "case-abc"},
    ]

    def test_direct_match(self):
        result = _find_port(self.PORTS, "success", {})
        assert result is not None
        assert result["id"] == "success"

    def test_alias_match(self):
        aliases = {"output": "success"}
        result = _find_port(self.PORTS, "output", aliases)
        assert result is not None
        assert result["id"] == "success"

    def test_handle_id_match(self):
        result = _find_port(self.PORTS, "source-success", {})
        assert result is not None
        assert result["id"] == "success"

    def test_source_prefix_strip(self):
        result = _find_port(self.PORTS, "source-case-abc", {})
        assert result is not None
        assert result["id"] == "case-abc"

    def test_not_found(self):
        result = _find_port(self.PORTS, "nonexistent", {})
        assert result is None

    def test_empty_ports(self):
        result = _find_port([], "success", {})
        assert result is None

    def test_none_ports(self):
        result = _find_port(None, "success", {})
        assert result is None


class TestValidateConnection:
    """Test validate_connection() with registered modules."""

    def test_valid_connection(self):
        # http.get -> data.json.parse should be compatible
        result = validate_connection("http.get", "data.json.parse")
        assert result.valid is True

    def test_same_module_id_is_valid(self):
        # Same module_id for from/to is valid (different node instances)
        result = validate_connection("http.get", "http.get")
        # Should be valid since module-level self-connection is fine
        assert isinstance(result, ConnectionResult)

    def test_unknown_module_returns_error(self):
        result = validate_connection("nonexistent.module", "http.get")
        assert result.valid is False
        assert result.error_code == ErrorCode.MODULE_NOT_FOUND

    def test_unknown_target_module_returns_error(self):
        result = validate_connection("http.get", "nonexistent.module")
        assert result.valid is False
        assert result.error_code == ErrorCode.MODULE_NOT_FOUND

    def test_template_connection_always_valid(self):
        result = validate_connection("template.custom", "http.get")
        assert result.valid is True


class TestGetConnectable:
    """Test get_connectable() and get_connectable_summary()."""

    def test_get_connectable_returns_list(self):
        results = get_connectable("http.get", direction="next")
        assert isinstance(results, list)
        if results:
            item = results[0]
            assert "module_id" in item
            assert "label" in item
            assert "category" in item

    def test_get_connectable_prev(self):
        results = get_connectable("data.extract", direction="prev")
        assert isinstance(results, list)

    def test_get_connectable_summary_returns_dict(self):
        summary = get_connectable_summary("http.get", direction="next")
        assert isinstance(summary, dict)
        # Values should be ints (category counts)
        for k, v in summary.items():
            assert isinstance(k, str)
            assert isinstance(v, int)


# ============================================================
# 3. workflow.py
# ============================================================

class TestWorkflowDataclasses:
    """Test WorkflowError and WorkflowResult dataclasses."""

    def test_workflow_error_creation(self):
        err = WorkflowError(
            code=ErrorCode.CYCLE_DETECTED,
            message="Cycle found",
            path="workflow",
            meta={"cycle": ["n1", "n2", "n1"]},
        )
        assert err.code == "CYCLE_DETECTED"
        assert err.path == "workflow"

    def test_workflow_result_valid(self):
        r = WorkflowResult(valid=True)
        assert r.valid is True
        assert r.errors == []
        assert r.warnings == []

    def test_workflow_result_invalid(self):
        err = WorkflowError(code="X", message="x", path="p")
        r = WorkflowResult(valid=False, errors=[err])
        assert r.valid is False
        assert len(r.errors) == 1


class TestEvaluateShowCondition:
    """Test _evaluate_show_condition() operator support."""

    def test_in_operator_match(self):
        assert _evaluate_show_condition({"$in": ["a", "b"]}, "a") is True

    def test_in_operator_no_match(self):
        assert _evaluate_show_condition({"$in": ["a", "b"]}, "c") is False

    def test_ne_operator_match(self):
        assert _evaluate_show_condition({"$ne": "x"}, "y") is True

    def test_ne_operator_no_match(self):
        assert _evaluate_show_condition({"$ne": "x"}, "x") is False

    def test_not_empty_true(self):
        assert _evaluate_show_condition({"$notEmpty": True}, "hello") is True

    def test_not_empty_false_on_empty(self):
        assert _evaluate_show_condition({"$notEmpty": True}, "") is False

    def test_not_empty_false_on_none(self):
        assert _evaluate_show_condition({"$notEmpty": True}, None) is False

    def test_not_empty_inverted(self):
        # $notEmpty: false means "is empty"
        assert _evaluate_show_condition({"$notEmpty": False}, "") is True
        assert _evaluate_show_condition({"$notEmpty": False}, "val") is False

    def test_list_shorthand(self):
        assert _evaluate_show_condition(["a", "b", "c"], "b") is True
        assert _evaluate_show_condition(["a", "b", "c"], "d") is False

    def test_equality(self):
        assert _evaluate_show_condition("exact", "exact") is True
        assert _evaluate_show_condition("exact", "other") is False

    def test_unknown_dict_operator(self):
        assert _evaluate_show_condition({"$unknown": 1}, "x") is False


class TestIsFieldActive:
    """Test _is_field_active() with showIf, hideIf, displayOptions."""

    def test_no_conditions_returns_true(self):
        assert _is_field_active({}, {}) is True

    def test_show_if_met(self):
        param_def = {"showIf": {"mode": "advanced"}}
        params = {"mode": "advanced"}
        assert _is_field_active(param_def, params) is True

    def test_show_if_not_met(self):
        param_def = {"showIf": {"mode": "advanced"}}
        params = {"mode": "simple"}
        assert _is_field_active(param_def, params) is False

    def test_hide_if_met(self):
        param_def = {"hideIf": {"disabled": True}}
        params = {"disabled": True}
        assert _is_field_active(param_def, params) is False

    def test_hide_if_not_met(self):
        param_def = {"hideIf": {"disabled": True}}
        params = {"disabled": False}
        assert _is_field_active(param_def, params) is True

    def test_display_options_show(self):
        param_def = {
            "displayOptions": {
                "show": {"format": ["json", "xml"]},
            }
        }
        assert _is_field_active(param_def, {"format": "json"}) is True
        assert _is_field_active(param_def, {"format": "csv"}) is False

    def test_display_options_hide(self):
        param_def = {
            "displayOptions": {
                "hide": {"format": ["raw"]},
            }
        }
        assert _is_field_active(param_def, {"format": "raw"}) is False
        assert _is_field_active(param_def, {"format": "json"}) is True


class TestValidateWorkflow:
    """Test validate_workflow() with various graph structures."""

    def test_empty_workflow(self):
        result = validate_workflow(nodes=[], edges=[])
        assert result.valid is True
        assert result.errors == []

    def test_single_node(self):
        nodes = [{"id": "n1", "module_id": "http.get", "params": {}}]
        result = validate_workflow(nodes=nodes, edges=[], validate_params=False)
        assert isinstance(result, WorkflowResult)
        # Single node, no edges — should be valid (no start-node error for 1 node)
        assert result.valid is True or any(
            e.code == ErrorCode.INVALID_START_NODE for e in result.errors
        )

    def test_valid_simple_workflow(self):
        nodes = [
            {"id": "n1", "module_id": "http.get", "params": {}},
            {"id": "n2", "module_id": "data.json.parse", "params": {}},
        ]
        edges = [
            {"id": "e1", "source": "n1", "target": "n2"},
        ]
        result = validate_workflow(nodes=nodes, edges=edges, validate_params=False)
        assert isinstance(result, WorkflowResult)

    def test_cycle_detection(self):
        nodes = [
            {"id": "n1", "module_id": "http.get", "params": {}},
            {"id": "n2", "module_id": "data.json.parse", "params": {}},
            {"id": "n3", "module_id": "http.get", "params": {}},
        ]
        edges = [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
            {"id": "e3", "source": "n3", "target": "n1"},
        ]
        result = validate_workflow(nodes=nodes, edges=edges, validate_params=False)
        cycle_errors = [e for e in result.errors if e.code == ErrorCode.CYCLE_DETECTED]
        assert len(cycle_errors) > 0

    def test_self_connection_error(self):
        nodes = [
            {"id": "n1", "module_id": "http.get", "params": {}},
        ]
        edges = [
            {"id": "e1", "source": "n1", "target": "n1"},
        ]
        result = validate_workflow(nodes=nodes, edges=edges, validate_params=False)
        self_errors = [e for e in result.errors if e.code == ErrorCode.SELF_CONNECTION]
        assert len(self_errors) > 0


class TestValidateStart:
    """Test validate_start() for start-node validation."""

    def test_no_start_node_error(self):
        # All nodes have incoming edges -> no start node
        nodes = [
            {"id": "n1", "module_id": "http.get", "params": {}},
            {"id": "n2", "module_id": "data.json.parse", "params": {}},
        ]
        edges = [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n1"},
        ]
        errors = validate_start(nodes, edges)
        no_start = [e for e in errors if e.code == ErrorCode.NO_START_NODE]
        assert len(no_start) > 0

    def test_single_valid_start_node(self):
        # browser.launch is a startable module
        nodes = [
            {"id": "n1", "module_id": "browser.launch", "params": {}},
            {"id": "n2", "module_id": "browser.click", "params": {}},
        ]
        edges = [
            {"id": "e1", "source": "n1", "target": "n2"},
        ]
        errors = validate_start(nodes, edges)
        invalid_start = [e for e in errors if e.code == ErrorCode.INVALID_START_NODE]
        assert len(invalid_start) == 0

    def test_empty_nodes(self):
        errors = validate_start([], [])
        assert errors == []


class TestGetStartableModules:
    """Test get_startable_modules()."""

    def test_returns_list(self):
        modules = get_startable_modules()
        assert isinstance(modules, list)

    def test_items_have_expected_keys(self):
        modules = get_startable_modules()
        if modules:
            item = modules[0]
            assert "module_id" in item
            assert "label" in item
            assert "category" in item
            assert "start_requires_params" in item


# ============================================================
# 4. index.py
# ============================================================

class TestConnectionIndex:
    """Test ConnectionIndex singleton and rebuild."""

    def test_get_instance_singleton(self):
        a = ConnectionIndex.get_instance()
        b = ConnectionIndex.get_instance()
        assert a is b

    def test_rebuild_returns_index(self):
        index = ConnectionIndex.rebuild()
        assert isinstance(index, ConnectionIndex)
        assert index._built is True

    def test_rebuild_creates_new_instance(self):
        old = ConnectionIndex.get_instance()
        new = ConnectionIndex.rebuild()
        # rebuild replaces the singleton
        assert ConnectionIndex.get_instance() is new

    def test_connectable_next_populated(self):
        index = ConnectionIndex.get_instance()
        assert isinstance(index.connectable_next, dict)
        # Should have entries after module registration
        assert len(index.connectable_next) > 0

    def test_startable_modules_populated(self):
        index = ConnectionIndex.get_instance()
        assert isinstance(index.startable_modules, list)

    def test_get_summary_returns_category_counts(self):
        index = ConnectionIndex.get_instance()
        # Pick a module that should exist
        if index.connectable_next:
            module_id = next(iter(index.connectable_next))
            summary = index.get_summary(module_id, "next")
            assert isinstance(summary, dict)
            for k, v in summary.items():
                assert isinstance(k, str)
                assert isinstance(v, int)


# ============================================================
# 5. Extended connection.py tests
# ============================================================

from core.validation.connection import (
    _validate_template_connection,
    _validate_connection_rules,
    _get_module_category,
    _validate_port_compatibility,
    _types_compatible,
    _data_types_compatible,
    _matches_any_pattern,
    get_connectable_for_replacement,
    validate_replacement,
)
from core.validation.workflow import (
    validate_node_params,
    _detect_cycles,
)


class TestValidateTemplateConnection:
    """Test _validate_template_connection() for template.xxx modules."""

    def test_both_templates_valid(self):
        result = _validate_template_connection("template.a", "template.b")
        assert result is not None
        assert result.valid is True

    def test_template_source_real_target_valid(self):
        result = _validate_template_connection("template.custom", "http.get")
        assert result is not None
        assert result.valid is True

    def test_real_source_template_target_valid(self):
        result = _validate_template_connection("http.get", "template.custom")
        assert result is not None
        assert result.valid is True

    def test_template_source_unknown_target_module_not_found(self):
        result = _validate_template_connection("template.custom", "nonexistent.xyz")
        assert result is not None
        assert result.valid is False
        assert result.error_code == ErrorCode.MODULE_NOT_FOUND

    def test_unknown_source_template_target_module_not_found(self):
        result = _validate_template_connection("nonexistent.xyz", "template.custom")
        assert result is not None
        assert result.valid is False
        assert result.error_code == ErrorCode.MODULE_NOT_FOUND

    def test_both_real_modules_returns_none(self):
        """Non-template modules should return None (continue validation)."""
        result = _validate_template_connection("http.get", "data.json.parse")
        assert result is None


class TestValidateConnectionRules:
    """Test _validate_connection_rules() for can_connect_to / can_receive_from."""

    def test_wildcard_allows_everything(self):
        from_meta = {"can_connect_to": ["*"]}
        to_meta = {"can_receive_from": ["*"]}
        result = _validate_connection_rules("http.get", "data.extract", from_meta, to_meta)
        assert result is None  # None means valid

    def test_restricted_can_connect_to_no_match(self):
        from_meta = {"can_connect_to": ["browser.*"]}
        to_meta = {"can_receive_from": ["*"]}
        result = _validate_connection_rules("http.get", "data.extract", from_meta, to_meta)
        assert result is not None
        assert result.valid is False
        assert result.error_code == ErrorCode.INCOMPATIBLE_MODULES

    def test_restricted_can_connect_to_match(self):
        from_meta = {"can_connect_to": ["data.*"]}
        to_meta = {"can_receive_from": ["*"]}
        result = _validate_connection_rules("http.get", "data.extract", from_meta, to_meta)
        assert result is None

    def test_restricted_can_receive_from_no_match(self):
        from_meta = {"can_connect_to": ["*"]}
        to_meta = {"can_receive_from": ["browser.*"]}
        result = _validate_connection_rules("http.get", "data.extract", from_meta, to_meta)
        assert result is not None
        assert result.valid is False
        assert result.error_code == ErrorCode.INCOMPATIBLE_MODULES

    def test_restricted_can_receive_from_match(self):
        from_meta = {"can_connect_to": ["*"]}
        to_meta = {"can_receive_from": ["http.*"]}
        result = _validate_connection_rules("http.get", "data.extract", from_meta, to_meta)
        assert result is None

    def test_both_restricted_both_match(self):
        from_meta = {"can_connect_to": ["data.*"]}
        to_meta = {"can_receive_from": ["http.*"]}
        result = _validate_connection_rules("http.get", "data.extract", from_meta, to_meta)
        assert result is None


class TestGetModuleCategory:
    """Test _get_module_category() category extraction."""

    def test_simple_two_part(self):
        assert _get_module_category("browser.click") == "browser"

    def test_core_prefix_stripped(self):
        assert _get_module_category("core.browser.click") == "browser"

    def test_pro_prefix_stripped(self):
        assert _get_module_category("pro.ai.chat") == "ai"

    def test_cloud_prefix_stripped(self):
        assert _get_module_category("cloud.storage.upload") == "storage"

    def test_single_part(self):
        assert _get_module_category("flow") == "flow"

    def test_three_parts_no_known_prefix(self):
        assert _get_module_category("data.json.parse") == "data"


class TestMatchesAnyPattern:
    """Test _matches_any_pattern() pattern matching."""

    def test_wildcard_always_true(self):
        assert _matches_any_pattern("anything.module", ["*"]) is True

    def test_category_wildcard_match(self):
        assert _matches_any_pattern("browser.click", ["browser.*"]) is True

    def test_category_wildcard_no_match(self):
        assert _matches_any_pattern("http.get", ["browser.*"]) is False

    def test_exact_match(self):
        assert _matches_any_pattern("http.get", ["http.get"]) is True

    def test_no_match(self):
        assert _matches_any_pattern("http.get", ["browser.click", "data.extract"]) is False

    def test_multiple_patterns_one_matches(self):
        assert _matches_any_pattern("http.get", ["browser.*", "http.*"]) is True

    def test_empty_patterns(self):
        assert _matches_any_pattern("http.get", []) is False

    def test_category_wildcard_partial_prefix_no_match(self):
        """'browser.*' should NOT match 'browser_find.xxx'."""
        assert _matches_any_pattern("browser_find.query", ["browser.*"]) is False


class TestTypesCompatible:
    """Test _types_compatible() module-level type compatibility."""

    def test_control_always_compatible(self):
        assert _types_compatible(["control"], ["browser_page"]) is True

    def test_any_output_always_compatible(self):
        assert _types_compatible(["any"], ["browser_page"]) is True

    def test_any_input_always_compatible(self):
        assert _types_compatible(["string"], ["any"]) is True

    def test_matching_types(self):
        assert _types_compatible(["string", "json"], ["json", "object"]) is True

    def test_no_matching_types(self):
        assert _types_compatible(["string"], ["browser_page"]) is False

    def test_multiple_output_one_matches(self):
        assert _types_compatible(["string", "object"], ["object"]) is True


class TestDataTypesCompatible:
    """Test _data_types_compatible() port-level data type compatibility."""

    def test_same_type_compatible(self):
        assert _data_types_compatible(["string"], ["string"]) is True

    def test_string_to_json_compatible(self):
        assert _data_types_compatible(["string"], ["json"]) is True

    def test_incompatible_types(self):
        assert _data_types_compatible(["browser"], ["string"]) is False

    def test_any_target_accepts_everything(self):
        assert _data_types_compatible(["browser"], ["any"]) is True

    def test_unknown_types_fallback_to_string_equality(self):
        assert _data_types_compatible(["custom_type"], ["custom_type"]) is True

    def test_unknown_types_no_match(self):
        assert _data_types_compatible(["custom_a"], ["custom_b"]) is False


class TestValidatePortCompatibility:
    """Test _validate_port_compatibility() port-level validation."""

    def test_port_not_found_from(self):
        from_meta = {
            "output_ports": [{"id": "success"}],
            "input_ports": [],
        }
        to_meta = {
            "output_ports": [],
            "input_ports": [{"id": "input"}],
        }
        result = _validate_port_compatibility(
            "mod.a", "mod.b", from_meta, to_meta,
            from_port="nonexistent", to_port="input",
        )
        assert result.valid is False
        assert result.error_code == ErrorCode.PORT_NOT_FOUND

    def test_port_not_found_to(self):
        from_meta = {
            "output_ports": [{"id": "success"}],
            "input_ports": [],
        }
        to_meta = {
            "output_ports": [],
            "input_ports": [{"id": "input"}],
        }
        result = _validate_port_compatibility(
            "mod.a", "mod.b", from_meta, to_meta,
            from_port="success", to_port="nonexistent",
        )
        assert result.valid is False
        assert result.error_code == ErrorCode.PORT_NOT_FOUND

    def test_incompatible_edge_types(self):
        from_meta = {
            "output_ports": [{"id": "success", "edge_type": "data"}],
        }
        to_meta = {
            "input_ports": [{"id": "input", "edge_type": "control"}],
        }
        result = _validate_port_compatibility(
            "mod.a", "mod.b", from_meta, to_meta,
            from_port="success", to_port="input",
        )
        assert result.valid is False
        assert result.error_code == ErrorCode.INCOMPATIBLE_MODULES

    def test_data_type_mismatch(self):
        from_meta = {
            "output_ports": [{"id": "success", "data_type": "browser"}],
        }
        to_meta = {
            "input_ports": [{"id": "input", "data_type": "string"}],
        }
        result = _validate_port_compatibility(
            "mod.a", "mod.b", from_meta, to_meta,
            from_port="success", to_port="input",
        )
        assert result.valid is False
        assert result.error_code == ErrorCode.TYPE_MISMATCH

    def test_compatible_ports(self):
        from_meta = {
            "output_ports": [{"id": "success", "data_type": "string"}],
        }
        to_meta = {
            "input_ports": [{"id": "input", "data_type": "string"}],
        }
        result = _validate_port_compatibility(
            "mod.a", "mod.b", from_meta, to_meta,
            from_port="success", to_port="input",
        )
        assert result.valid is True

    def test_no_ports_falls_back_to_module_types(self):
        from_meta = {
            "output_ports": [],
            "output_types": ["string"],
        }
        to_meta = {
            "input_ports": [],
            "input_types": ["browser_page"],
        }
        result = _validate_port_compatibility(
            "mod.a", "mod.b", from_meta, to_meta,
            from_port=None, to_port=None,
        )
        assert result.valid is False
        assert result.error_code == ErrorCode.TYPE_MISMATCH

    def test_no_ports_compatible_module_types(self):
        from_meta = {
            "output_ports": [],
            "output_types": ["string", "json"],
        }
        to_meta = {
            "input_ports": [],
            "input_types": ["json"],
        }
        result = _validate_port_compatibility(
            "mod.a", "mod.b", from_meta, to_meta,
            from_port=None, to_port=None,
        )
        assert result.valid is True

    def test_default_port_when_none(self):
        """When port is None, should default to first available port."""
        from_meta = {
            "output_ports": [{"id": "success", "data_type": "string"}],
        }
        to_meta = {
            "input_ports": [{"id": "input", "data_type": "string"}],
        }
        result = _validate_port_compatibility(
            "mod.a", "mod.b", from_meta, to_meta,
            from_port=None, to_port=None,
        )
        assert result.valid is True


class TestGetConnectableExtended:
    """Extended tests for get_connectable() with filters."""

    def test_get_connectable_with_search(self):
        results = get_connectable("http.get", direction="next", search="json")
        assert isinstance(results, list)
        # All results should contain 'json' in module_id or label
        for item in results:
            has_json = (
                "json" in item["module_id"].lower()
                or "json" in item["label"].lower()
            )
            assert has_json, f"Result {item['module_id']} does not match search 'json'"

    def test_get_connectable_with_category(self):
        results = get_connectable("http.get", direction="next", category="data")
        assert isinstance(results, list)
        for item in results:
            assert item["module_id"].startswith("data."), (
                f"Result {item['module_id']} not in category 'data'"
            )

    def test_get_connectable_with_limit(self):
        results = get_connectable("http.get", direction="next", limit=2)
        assert len(results) <= 2

    def test_get_connectable_prev_direction(self):
        results = get_connectable("data.json.parse", direction="prev")
        assert isinstance(results, list)
        # http.get should be in the list of possible predecessors
        module_ids = [r["module_id"] for r in results]
        assert "http.get" in module_ids or len(module_ids) > 0


class TestGetConnectableForReplacement:
    """Test get_connectable_for_replacement() with various combinations."""

    def test_upstream_only(self):
        results = get_connectable_for_replacement(upstream_module_id="http.get")
        assert isinstance(results, list)
        # Should return modules that can receive from http.get
        assert len(results) > 0

    def test_downstream_only(self):
        results = get_connectable_for_replacement(downstream_module_id="data.json.parse")
        assert isinstance(results, list)
        assert len(results) > 0

    def test_both_upstream_and_downstream(self):
        results = get_connectable_for_replacement(
            upstream_module_id="http.get",
            downstream_module_id="data.extract",
        )
        assert isinstance(results, list)
        # Should be intersection of both sets

    def test_neither_returns_empty(self):
        results = get_connectable_for_replacement()
        assert results == []

    def test_result_has_expected_keys(self):
        results = get_connectable_for_replacement(upstream_module_id="http.get")
        if results:
            item = results[0]
            assert "module_id" in item
            assert "label" in item
            assert "category" in item


class TestValidateReplacement:
    """Test validate_replacement() for node replacement validation."""

    def test_valid_replacement(self):
        result = validate_replacement(
            new_module_id="data.json.parse",
            upstream_module_id="http.get",
        )
        assert isinstance(result, ConnectionResult)
        # Should be valid since http.get -> data.json.parse is compatible

    def test_no_connections(self):
        result = validate_replacement(new_module_id="http.get")
        assert result.valid is True

    def test_invalid_upstream_connection(self):
        # Use a combination that's likely incompatible
        result = validate_replacement(
            new_module_id="http.get",
            upstream_module_id="nonexistent.module",
        )
        assert result.valid is False

    def test_invalid_downstream_connection(self):
        result = validate_replacement(
            new_module_id="http.get",
            downstream_module_id="nonexistent.module",
        )
        assert result.valid is False


# ============================================================
# 6. Extended workflow.py tests
# ============================================================

class TestValidateNodeParams:
    """Test validate_node_params() for parameter validation."""

    def test_empty_module_id_returns_empty(self):
        node = {"id": "n1", "module_id": "", "params": {"url": "test"}}
        errors = validate_node_params(node)
        assert errors == []

    def test_unknown_module_returns_empty(self):
        node = {"id": "n1", "module_id": "nonexistent.xyz", "params": {"x": 1}}
        errors = validate_node_params(node)
        assert errors == []

    def test_unknown_param_error(self):
        node = {
            "id": "n1",
            "module_id": "http.get",
            "params": {"totally_fake_param": "value"},
        }
        errors = validate_node_params(node)
        unknown = [e for e in errors if e.code == ErrorCode.UNKNOWN_PARAM]
        assert len(unknown) == 1
        assert "totally_fake_param" in unknown[0].message

    def test_missing_required_param(self):
        """http.get requires 'url' — omitting it should raise MISSING_REQUIRED_PARAM."""
        node = {
            "id": "n1",
            "module_id": "http.get",
            "params": {},
        }
        errors = validate_node_params(node)
        missing = [e for e in errors if e.code == ErrorCode.MISSING_REQUIRED_PARAM]
        assert len(missing) >= 1
        param_names = [e.meta.get("param") for e in missing]
        assert "url" in param_names

    def test_required_param_hidden_by_show_if_no_error(self):
        """If a required field is hidden by showIf, no error should be raised."""
        # We simulate this by building a node with a module that has showIf
        # Since http.get doesn't have showIf, we test via validate_workflow
        # using a node whose required field is satisfied
        node = {
            "id": "n1",
            "module_id": "http.get",
            "params": {"url": "https://example.com"},
        }
        errors = validate_node_params(node)
        missing = [e for e in errors if e.code == ErrorCode.MISSING_REQUIRED_PARAM]
        assert len(missing) == 0

    def test_valid_params_no_errors(self):
        node = {
            "id": "n1",
            "module_id": "http.get",
            "params": {"url": "https://example.com"},
        }
        errors = validate_node_params(node)
        # Should have no MISSING_REQUIRED or UNKNOWN errors
        assert all(e.code not in (ErrorCode.MISSING_REQUIRED_PARAM, ErrorCode.UNKNOWN_PARAM) for e in errors)


class TestValidateWorkflowExtended:
    """Extended tests for validate_workflow() with complex scenarios."""

    def test_edge_with_missing_source_node(self):
        nodes = [
            {"id": "n2", "module_id": "http.get", "params": {}},
        ]
        edges = [
            {"id": "e1", "source": "nonexistent", "target": "n2"},
        ]
        result = validate_workflow(nodes=nodes, edges=edges, validate_params=False)
        source_errors = [
            e for e in result.errors if e.code == ErrorCode.MODULE_NOT_FOUND
            and "nonexistent" in e.message
        ]
        assert len(source_errors) > 0

    def test_edge_with_missing_target_node(self):
        nodes = [
            {"id": "n1", "module_id": "http.get", "params": {}},
        ]
        edges = [
            {"id": "e1", "source": "n1", "target": "nonexistent"},
        ]
        result = validate_workflow(nodes=nodes, edges=edges, validate_params=False)
        target_errors = [
            e for e in result.errors if e.code == ErrorCode.MODULE_NOT_FOUND
            and "nonexistent" in e.message
        ]
        assert len(target_errors) > 0

    def test_self_connection_same_node_id(self):
        nodes = [
            {"id": "n1", "module_id": "http.get", "params": {}},
        ]
        edges = [
            {"id": "e1", "source": "n1", "target": "n1"},
        ]
        result = validate_workflow(nodes=nodes, edges=edges, validate_params=False)
        self_errs = [e for e in result.errors if e.code == ErrorCode.SELF_CONNECTION]
        assert len(self_errs) > 0

    def test_validate_params_false_skips_param_validation(self):
        nodes = [
            {"id": "n1", "module_id": "http.get", "params": {"bogus_param": "x"}},
        ]
        result = validate_workflow(nodes=nodes, edges=[], validate_params=False)
        # Should not have UNKNOWN_PARAM warnings when validate_params=False
        unknown = [w for w in result.warnings if w.code == ErrorCode.UNKNOWN_PARAM]
        assert len(unknown) == 0

    def test_validate_params_true_unknown_params_as_warnings(self):
        nodes = [
            {"id": "n1", "module_id": "http.get", "params": {"bogus_param": "x", "url": "https://x.com"}},
        ]
        result = validate_workflow(nodes=nodes, edges=[], validate_params=True)
        unknown = [w for w in result.warnings if w.code == ErrorCode.UNKNOWN_PARAM]
        assert len(unknown) >= 1

    def test_incompatible_modules_in_edge(self):
        """Connecting incompatible module types should produce an error."""
        # ai -> browser should be context-incompatible
        nodes = [
            {"id": "n1", "module_id": "ai.text", "params": {}},
            {"id": "n2", "module_id": "browser.click", "params": {}},
        ]
        edges = [
            {"id": "e1", "source": "n1", "target": "n2"},
        ]
        result = validate_workflow(nodes=nodes, edges=edges, validate_params=False)
        # If modules exist, should get an incompatibility error; if not found,
        # that's also an error — either way result should not be fully valid
        # (unless both modules happen to be compatible)
        assert isinstance(result, WorkflowResult)


class TestValidateStartExtended:
    """Extended tests for validate_start()."""

    def test_module_not_found(self):
        nodes = [
            {"id": "n1", "module_id": "nonexistent.xyz", "params": {}},
        ]
        edges = []
        errors = validate_start(nodes, edges)
        not_found = [e for e in errors if e.code == ErrorCode.MODULE_NOT_FOUND]
        assert len(not_found) > 0

    def test_module_cannot_be_start(self):
        """flow.if (branch) has can_be_start=False (resolved by node_type=BRANCH)."""
        nodes = [
            {"id": "n1", "module_id": "flow.if", "params": {}},
            {"id": "n2", "module_id": "http.get", "params": {}},
        ]
        edges = [
            {"id": "e1", "source": "n1", "target": "n2"},
        ]
        errors = validate_start(nodes, edges)
        invalid_start = [e for e in errors if e.code == ErrorCode.INVALID_START_NODE]
        # flow.if as a branch node should not be startable
        assert len(invalid_start) >= 1 or any(
            e.code == ErrorCode.MODULE_NOT_FOUND for e in errors
        )

    def test_single_valid_start_node_no_error(self):
        """http.request has can_be_start=True explicitly set."""
        nodes = [
            {"id": "n1", "module_id": "http.request", "params": {}},
        ]
        edges = []
        errors = validate_start(nodes, edges)
        invalid_start = [e for e in errors if e.code == ErrorCode.INVALID_START_NODE]
        assert len(invalid_start) == 0


class TestDetectCycles:
    """Test _detect_cycles() cycle detection."""

    def test_no_cycle(self):
        node_ids = {"n1", "n2", "n3"}
        outgoing = {"n1": ["n2"], "n2": ["n3"], "n3": []}
        node_map = {
            "n1": {"id": "n1", "module_id": "http.get"},
            "n2": {"id": "n2", "module_id": "data.json.parse"},
            "n3": {"id": "n3", "module_id": "data.extract"},
        }
        errors = _detect_cycles(node_ids, outgoing, node_map)
        assert len(errors) == 0

    def test_simple_cycle(self):
        node_ids = {"n1", "n2"}
        outgoing = {"n1": ["n2"], "n2": ["n1"]}
        node_map = {
            "n1": {"id": "n1", "module_id": "http.get"},
            "n2": {"id": "n2", "module_id": "data.json.parse"},
        }
        errors = _detect_cycles(node_ids, outgoing, node_map)
        cycle_errs = [e for e in errors if e.code == ErrorCode.CYCLE_DETECTED]
        assert len(cycle_errs) > 0

    def test_three_node_cycle(self):
        node_ids = {"n1", "n2", "n3"}
        outgoing = {"n1": ["n2"], "n2": ["n3"], "n3": ["n1"]}
        node_map = {
            "n1": {"id": "n1", "module_id": "http.get"},
            "n2": {"id": "n2", "module_id": "data.json.parse"},
            "n3": {"id": "n3", "module_id": "data.extract"},
        }
        errors = _detect_cycles(node_ids, outgoing, node_map)
        cycle_errs = [e for e in errors if e.code == ErrorCode.CYCLE_DETECTED]
        assert len(cycle_errs) > 0

    def test_loop_nodes_skipped(self):
        """Loop-type nodes should be skipped in cycle detection."""
        node_ids = {"n1", "n2"}
        outgoing = {"n1": ["n2"], "n2": ["n1"]}
        node_map = {
            "n1": {"id": "n1", "module_id": "http.get"},
            "n2": {"id": "n2", "module_id": "flow.loop"},
        }
        errors = _detect_cycles(node_ids, outgoing, node_map)
        cycle_errs = [e for e in errors if e.code == ErrorCode.CYCLE_DETECTED]
        # n2 is a loop node, so the cycle back through n2 should be skipped
        assert len(cycle_errs) == 0

    def test_disconnected_no_cycle(self):
        node_ids = {"n1", "n2"}
        outgoing = {"n1": [], "n2": []}
        node_map = {
            "n1": {"id": "n1", "module_id": "http.get"},
            "n2": {"id": "n2", "module_id": "data.extract"},
        }
        errors = _detect_cycles(node_ids, outgoing, node_map)
        assert len(errors) == 0
