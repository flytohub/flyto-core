"""
Unit Tests for Variable Resolver v2

Tests the expression parser and variable resolution with full syntax support.
"""

import pytest
from typing import Any, Dict

from core.engine.sdk.resolver import (
    ExpressionParser,
    VariableResolver,
    VariableNotFoundError,
    ExpressionSyntaxError,
    create_resolver,
)
from core.engine.sdk.models import ResolutionMode


class TestExpressionParser:
    """Tests for ExpressionParser"""

    def setup_method(self):
        self.parser = ExpressionParser()

    def test_parse_simple_identifier(self):
        result = self.parser.parse("input")
        assert result.is_valid
        assert len(result.tokens) == 1
        assert result.tokens[0].token_type == "identifier"
        assert result.tokens[0].value == "input"

    def test_parse_dotted_path(self):
        result = self.parser.parse("node.port.field")
        assert result.is_valid
        assert len(result.tokens) == 3
        assert result.tokens[0].value == "node"
        assert result.tokens[1].value == "port"
        assert result.tokens[2].value == "field"

    def test_parse_array_index(self):
        result = self.parser.parse("arr[0]")
        assert result.is_valid
        assert len(result.tokens) == 2
        assert result.tokens[0].value == "arr"
        assert result.tokens[1].token_type == "index"
        assert result.tokens[1].value == "0"

    def test_parse_quoted_key_double_quotes(self):
        result = self.parser.parse('obj["my-key"]')
        assert result.is_valid
        assert len(result.tokens) == 2
        assert result.tokens[0].value == "obj"
        assert result.tokens[1].token_type == "quoted_key"
        assert result.tokens[1].value == "my-key"

    def test_parse_quoted_key_single_quotes(self):
        result = self.parser.parse("obj['my-key']")
        assert result.is_valid
        assert len(result.tokens) == 2
        assert result.tokens[1].token_type == "quoted_key"
        assert result.tokens[1].value == "my-key"

    def test_parse_complex_path(self):
        result = self.parser.parse('data.items[0]["name"]')
        assert result.is_valid
        assert len(result.tokens) == 4
        assert result.tokens[0].value == "data"
        assert result.tokens[1].value == "items"
        assert result.tokens[2].token_type == "index"
        assert result.tokens[3].token_type == "quoted_key"

    def test_parse_default_filter(self):
        result = self.parser.parse("input | default('fallback')")
        assert result.is_valid
        assert result.raw == "input | default('fallback')"

    def test_parse_invalid_character(self):
        result = self.parser.parse("input@invalid")
        assert not result.is_valid
        assert result.error is not None

    def test_extract_expressions(self):
        text = "Hello {{name}}, your order {{order.id}} is ready"
        results = self.parser.extract_expressions(text)
        assert len(results) == 2
        assert results[0][0] == "name"
        assert results[1][0] == "order.id"


class TestVariableResolver:
    """Tests for VariableResolver"""

    def test_resolve_input_shorthand(self):
        context = {
            "inputs": {"main": {"message": "hello"}}
        }
        resolver = VariableResolver(context=context)
        result = resolver.resolve("{{input.message}}")
        assert result == "hello"

    def test_resolve_input_fallback(self):
        context = {
            "input": "direct value"
        }
        resolver = VariableResolver(context=context)
        result = resolver.resolve("{{input}}")
        assert result == "direct value"

    def test_resolve_inputs_port(self):
        context = {
            "inputs": {
                "main": {"data": "main data"},
                "secondary": {"data": "secondary data"}
            }
        }
        resolver = VariableResolver(context=context)
        result = resolver.resolve("{{inputs.secondary.data}}")
        assert result == "secondary data"

    def test_resolve_node_output(self):
        context = {
            "fetch_node": {"ok": True, "data": {"title": "Test"}}
        }
        resolver = VariableResolver(context=context)
        result = resolver.resolve("{{fetch_node.data.title}}")
        assert result == "Test"

    def test_resolve_params(self):
        context = {}
        params = {"api_key": "secret123"}
        resolver = VariableResolver(context=context, params=params)
        result = resolver.resolve("{{params.api_key}}")
        assert result == "secret123"

    def test_resolve_globals(self):
        context = {}
        globals_dict = {"workflow": {"id": "wf123"}}
        resolver = VariableResolver(context=context, globals=globals_dict)
        result = resolver.resolve("{{global.workflow.id}}")
        assert result == "wf123"

    def test_resolve_env(self):
        context = {}
        env = {"NODE_ENV": "production"}
        resolver = VariableResolver(context=context, env=env)
        result = resolver.resolve("{{env.NODE_ENV}}")
        assert result == "production"

    def test_resolve_array_index(self):
        context = {
            "items": ["first", "second", "third"]
        }
        resolver = VariableResolver(context=context)
        result = resolver.resolve("{{items[1]}}")
        assert result == "second"

    def test_resolve_array_out_of_bounds(self):
        context = {
            "items": ["first"]
        }
        resolver = VariableResolver(context=context)
        result = resolver.resolve("{{items[10]}}")
        assert result == "{{items[10]}}"  # Keeps original when not found

    def test_resolve_quoted_key(self):
        context = {
            "data": {"special-key": "value", "key with space": "spaced"}
        }
        resolver = VariableResolver(context=context)
        assert resolver.resolve('{{data["special-key"]}}') == "value"
        assert resolver.resolve("{{data['key with space']}}") == "spaced"

    def test_resolve_default_filter(self):
        context = {}
        resolver = VariableResolver(context=context)
        result = resolver.resolve("{{missing | default('fallback')}}")
        assert result == "fallback"

    def test_resolve_default_not_used(self):
        context = {"value": "exists"}
        resolver = VariableResolver(context=context)
        result = resolver.resolve("{{value | default('fallback')}}")
        assert result == "exists"

    def test_resolve_raw_mode_object(self):
        context = {
            "data": {"nested": {"key": "value"}}
        }
        resolver = VariableResolver(context=context)
        result = resolver.resolve("{{data.nested}}", mode=ResolutionMode.RAW)
        assert isinstance(result, dict)
        assert result == {"key": "value"}

    def test_resolve_string_mode_object(self):
        context = {
            "data": {"key": "value"}
        }
        resolver = VariableResolver(context=context)
        result = resolver.resolve("{{data}}", mode=ResolutionMode.STRING)
        assert isinstance(result, str)
        assert '"key": "value"' in result

    def test_resolve_in_template(self):
        context = {
            "name": "World",
            "count": 5
        }
        resolver = VariableResolver(context=context)
        result = resolver.resolve("Hello {{name}}, you have {{count}} items")
        assert result == "Hello World, you have 5 items"

    def test_resolve_strict_mode_error(self):
        context = {}
        resolver = VariableResolver(context=context)
        with pytest.raises(VariableNotFoundError):
            resolver.resolve("{{missing}}", strict=True)

    def test_resolve_dict_recursively(self):
        context = {"value": "resolved"}
        resolver = VariableResolver(context=context)
        data = {
            "field1": "{{value}}",
            "field2": {"nested": "{{value}}"}
        }
        result = resolver.resolve(data)
        assert result["field1"] == "resolved"
        assert result["field2"]["nested"] == "resolved"

    def test_resolve_list_recursively(self):
        context = {"value": "resolved"}
        resolver = VariableResolver(context=context)
        data = ["{{value}}", "literal", "{{value}}"]
        result = resolver.resolve(data)
        assert result == ["resolved", "literal", "resolved"]


class TestConditionEvaluation:
    """Tests for condition evaluation"""

    def test_evaluate_equals(self):
        context = {"status": "active"}
        resolver = VariableResolver(context=context)
        assert resolver.evaluate_condition("{{status}} == active")
        assert not resolver.evaluate_condition("{{status}} == inactive")

    def test_evaluate_not_equals(self):
        context = {"status": "active"}
        resolver = VariableResolver(context=context)
        assert resolver.evaluate_condition("{{status}} != inactive")
        assert not resolver.evaluate_condition("{{status}} != active")

    def test_evaluate_greater_than(self):
        context = {"count": "10"}
        resolver = VariableResolver(context=context)
        assert resolver.evaluate_condition("{{count}} > 5")
        assert not resolver.evaluate_condition("{{count}} > 15")

    def test_evaluate_less_than(self):
        context = {"count": "10"}
        resolver = VariableResolver(context=context)
        assert resolver.evaluate_condition("{{count}} < 15")
        assert not resolver.evaluate_condition("{{count}} < 5")

    def test_evaluate_contains(self):
        context = {"text": "hello world"}
        resolver = VariableResolver(context=context)
        assert resolver.evaluate_condition("{{text}} contains world")
        assert not resolver.evaluate_condition("{{text}} contains foo")

    def test_evaluate_not_contains(self):
        context = {"text": "hello world"}
        resolver = VariableResolver(context=context)
        assert resolver.evaluate_condition("{{text}} !contains foo")
        assert not resolver.evaluate_condition("{{text}} !contains world")

    def test_evaluate_boolean_truthy(self):
        context = {}
        resolver = VariableResolver(context=context)
        assert resolver.evaluate_condition("true")
        assert resolver.evaluate_condition("yes")
        assert resolver.evaluate_condition("1")

    def test_evaluate_boolean_falsy(self):
        context = {}
        resolver = VariableResolver(context=context)
        assert not resolver.evaluate_condition("false")
        assert not resolver.evaluate_condition("no")
        assert not resolver.evaluate_condition("0")


class TestCreateResolver:
    """Tests for create_resolver factory"""

    def test_create_resolver_basic(self):
        context = {"data": "value"}
        resolver = create_resolver(context=context)
        assert resolver.resolve("{{data}}") == "value"

    def test_create_resolver_with_params(self):
        context = {}
        params = {"key": "value"}
        resolver = create_resolver(context=context, params=params)
        assert resolver.resolve("{{params.key}}") == "value"

    def test_create_resolver_with_workflow_metadata(self):
        context = {}
        metadata = {"id": "wf123", "name": "Test Workflow"}
        resolver = create_resolver(context=context, workflow_metadata=metadata)
        result = resolver.resolve("{{global.workflow.id}}")
        assert result == "wf123"
