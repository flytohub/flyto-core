"""
Unit Tests for Autocomplete Engine

Tests expression autocomplete and validation for workflow editors.
"""

import pytest
from typing import Any, Dict, List

from core.engine.sdk.models import (
    AutocompleteItem,
    AutocompleteResult,
    VarCatalog,
    VarInfo,
    PortVarInfo,
    NodeVarInfo,
    IntrospectionMode,
)
from core.engine.introspection.autocomplete import (
    AutocompleteEngine,
    ExpressionValidator,
    autocomplete,
    validate_expression,
    create_autocomplete,
)


# =============================================================================
# Test Fixtures
# =============================================================================

def create_test_workflow() -> Dict[str, Any]:
    """Create a workflow for autocomplete testing"""
    return {
        "id": "test-workflow",
        "params": {
            "api_key": {"type": "string", "description": "API Key"},
            "timeout": {"type": "number", "default": 30},
        },
        "nodes": [
            {
                "id": "http_node",
                "module_id": "http.request",
                "params": {"url": "https://api.example.com"},
            },
            {
                "id": "transform",
                "module_id": "data.transform.map",
                "params": {},
            },
            {
                "id": "output",
                "module_id": "core.output.json",
                "params": {},
            },
        ],
        "edges": [
            {"source": "http_node", "target": "transform"},
            {"source": "transform", "target": "output"},
        ],
    }


def create_test_catalog() -> VarCatalog:
    """Create a test VarCatalog for autocomplete testing"""
    return VarCatalog(
        schema_version="1.0",
        mode=IntrospectionMode.EDIT,
        node_id="transform",
        inputs={
            "main": PortVarInfo(
                port_id="main",
                var_type="object",
                description="Main input",
                fields={
                    "message": VarInfo(path="input.message", var_type="string"),
                    "count": VarInfo(path="input.count", var_type="number"),
                },
            ),
        },
        nodes={
            "http_node": NodeVarInfo(
                node_id="http_node",
                node_type="http.request",
                ports={
                    "output": PortVarInfo(
                        port_id="output",
                        var_type="object",
                        fields={
                            "ok": VarInfo(path="http_node.output.ok", var_type="boolean"),
                            "status": VarInfo(path="http_node.output.status", var_type="number"),
                            "data": VarInfo(path="http_node.output.data", var_type="object"),
                        },
                    ),
                },
            ),
        },
        params={
            "api_key": VarInfo(path="params.api_key", var_type="string"),
            "timeout": VarInfo(path="params.timeout", var_type="number"),
        },
        globals={},
        env={
            "NODE_ENV": VarInfo(path="env.NODE_ENV", var_type="string"),
        },
    )


# =============================================================================
# AutocompleteEngine Tests
# =============================================================================

class TestAutocompleteEngine:
    """Tests for AutocompleteEngine"""

    def test_suggest_root_variables(self):
        catalog = create_test_catalog()
        engine = AutocompleteEngine(catalog)

        result = engine.suggest("")
        assert isinstance(result, AutocompleteResult)
        assert len(result.items) > 0

        # Should suggest common root variables
        paths = [item.path for item in result.items]
        assert "input" in paths

    def test_suggest_with_prefix(self):
        catalog = create_test_catalog()
        engine = AutocompleteEngine(catalog)

        result = engine.suggest("http")
        assert len(result.items) > 0

        # Should suggest http_node paths
        paths = [item.path for item in result.items]
        assert any("http_node" in p for p in paths)

    def test_suggest_nested_path(self):
        catalog = create_test_catalog()
        engine = AutocompleteEngine(catalog)

        result = engine.suggest("http_node")
        assert len(result.items) > 0

        paths = [item.path for item in result.items]
        assert any("http_node" in p for p in paths)

    def test_suggest_params(self):
        catalog = create_test_catalog()
        engine = AutocompleteEngine(catalog)

        result = engine.suggest("params")
        paths = [item.path for item in result.items]
        assert "params.api_key" in paths
        assert "params.timeout" in paths

    def test_suggest_env(self):
        catalog = create_test_catalog()
        engine = AutocompleteEngine(catalog)

        result = engine.suggest("env")
        paths = [item.path for item in result.items]
        assert "env.NODE_ENV" in paths

    def test_no_suggestions_for_invalid_path(self):
        catalog = create_test_catalog()
        engine = AutocompleteEngine(catalog)

        result = engine.suggest("nonexistent_xyz")
        # Should return no matches
        assert len(result.items) == 0


class TestAutocompleteItem:
    """Tests for AutocompleteItem"""

    def test_item_creation(self):
        item = AutocompleteItem(
            path="http_node.data",
            display="http_node.data",
            var_type="object",
            description="Response data",
        )

        assert item.path == "http_node.data"
        assert item.display == "http_node.data"
        assert item.var_type == "object"

    def test_item_with_insert_text(self):
        item = AutocompleteItem(
            path="http_node.data.items",
            display="http_node.data.items",
            var_type="array",
            insert_text="{{http_node.data.items[0]}}",
        )

        assert item.insert_text == "{{http_node.data.items[0]}}"


# =============================================================================
# ExpressionValidator Tests
# =============================================================================

class TestExpressionValidator:
    """Tests for ExpressionValidator"""

    def test_validate_valid_expression(self):
        catalog = create_test_catalog()
        validator = ExpressionValidator(catalog)

        result = validator.validate("input")
        assert result["valid"] is True

    def test_validate_unknown_variable(self):
        catalog = create_test_catalog()
        validator = ExpressionValidator(catalog)

        result = validator.validate("unknown_node.data")
        assert result["valid"] is False
        assert "error" in result


# =============================================================================
# Factory Function Tests
# =============================================================================

class TestAutocompleteFunctions:
    """Tests for autocomplete factory functions"""

    def test_autocomplete_function(self):
        workflow = create_test_workflow()

        result = autocomplete(
            workflow=workflow,
            node_id="transform",
            prefix="",
        )

        assert isinstance(result, AutocompleteResult)

    def test_validate_expression_function(self):
        workflow = create_test_workflow()

        result = validate_expression(
            workflow=workflow,
            node_id="transform",
            expression="{{input}}",
        )

        assert isinstance(result, dict)
        assert "valid" in result

    def test_create_autocomplete_factory(self):
        workflow = create_test_workflow()
        engine = create_autocomplete(workflow, node_id="transform")

        assert isinstance(engine, AutocompleteEngine)

        result = engine.suggest("input")
        assert isinstance(result, AutocompleteResult)


# =============================================================================
# Edge Cases Tests
# =============================================================================

class TestAutocompleteEdgeCases:
    """Tests for edge cases in autocomplete"""

    def test_empty_catalog(self):
        catalog = VarCatalog()
        engine = AutocompleteEngine(catalog)

        result = engine.suggest("")
        # Should return at least input shorthand
        assert isinstance(result, AutocompleteResult)

    def test_prefix_with_braces(self):
        catalog = create_test_catalog()
        engine = AutocompleteEngine(catalog)

        # Should strip {{ }}
        result = engine.suggest("{{input")
        assert isinstance(result, AutocompleteResult)

    def test_limit_results(self):
        catalog = create_test_catalog()
        engine = AutocompleteEngine(catalog)

        result = engine.suggest("", limit=3)
        assert len(result.items) <= 3
