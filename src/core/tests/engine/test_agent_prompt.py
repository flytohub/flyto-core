"""
Unit Tests for AI Agent Prompt Resolution

Tests the n8n-style prompt source handling in llm.agent module.
"""

import pytest
import json
from typing import Any, Dict

# Import the helper functions from llm.agent
import sys
import os

# Add the module path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'modules', 'atomic', 'llm'))

from core.modules.atomic.llm.agent import (
    _resolve_task_prompt,
    _resolve_from_input,
    _simple_resolve,
    _substitute_variables,
    _join_array,
    _stringify_value,
)


# =============================================================================
# Test Fixtures
# =============================================================================

def create_context_with_input(input_data: Any) -> Dict[str, Any]:
    """Create a context with input data"""
    return {
        "inputs": {
            "input": input_data,
            "main": input_data,
        },
    }


def create_context_with_node_output(node_id: str, output: Any) -> Dict[str, Any]:
    """Create a context with a node output"""
    return {
        node_id: output,
        "inputs": {
            "input": output,
        },
    }


# =============================================================================
# _stringify_value Tests
# =============================================================================

class TestStringifyValue:
    """Tests for _stringify_value function"""

    def test_stringify_string(self):
        result = _stringify_value("hello world", 1000)
        assert result == "hello world"

    def test_stringify_number(self):
        result = _stringify_value(42, 1000)
        assert result == "42"

    def test_stringify_float(self):
        result = _stringify_value(3.14, 1000)
        assert result == "3.14"

    def test_stringify_boolean_true(self):
        result = _stringify_value(True, 1000)
        assert result == "true"

    def test_stringify_boolean_false(self):
        result = _stringify_value(False, 1000)
        assert result == "false"

    def test_stringify_none(self):
        result = _stringify_value(None, 1000)
        assert result == ""

    def test_stringify_dict(self):
        result = _stringify_value({"key": "value"}, 1000)
        assert '"key"' in result
        assert '"value"' in result

    def test_stringify_list(self):
        result = _stringify_value([1, 2, 3], 1000)
        assert "1" in result
        assert "2" in result
        assert "3" in result

    def test_stringify_truncation(self):
        long_string = "a" * 1000
        result = _stringify_value(long_string, 100)
        assert len(result) < 200  # Truncated with message
        assert "truncated" in result

    def test_stringify_dict_truncation(self):
        large_dict = {"key": "value" * 1000}
        result = _stringify_value(large_dict, 100)
        assert len(result) < 200


# =============================================================================
# _join_array Tests
# =============================================================================

class TestJoinArray:
    """Tests for _join_array function"""

    def test_join_first_strategy(self):
        arr = ["first", "second", "third"]
        result = _join_array(arr, "first", "", 1000)
        assert result == "first"

    def test_join_newline_strategy(self):
        arr = ["line1", "line2", "line3"]
        result = _join_array(arr, "newline", "", 1000)
        assert "line1\nline2\nline3" == result

    def test_join_separator_strategy(self):
        arr = ["a", "b", "c"]
        result = _join_array(arr, "separator", " | ", 1000)
        assert result == "a | b | c"

    def test_join_json_strategy(self):
        arr = [{"id": 1}, {"id": 2}]
        result = _join_array(arr, "json", "", 1000)
        parsed = json.loads(result)
        assert len(parsed) == 2
        assert parsed[0]["id"] == 1

    def test_join_empty_array(self):
        result = _join_array([], "first", "", 1000)
        assert result == ""

    def test_join_single_item(self):
        result = _join_array(["only"], "newline", "", 1000)
        assert result == "only"

    def test_join_with_truncation(self):
        arr = ["a" * 100, "b" * 100, "c" * 100]
        result = _join_array(arr, "newline", "", 50)
        assert len(result) <= 50


# =============================================================================
# _simple_resolve Tests
# =============================================================================

class TestSimpleResolve:
    """Tests for _simple_resolve function"""

    def test_resolve_input(self):
        context = create_context_with_input("hello")
        result = _simple_resolve(context, "{{input}}")
        assert result == "hello"

    def test_resolve_input_field(self):
        context = create_context_with_input({"message": "hello"})
        result = _simple_resolve(context, "{{input.message}}")
        assert result == "hello"

    def test_resolve_nested_field(self):
        context = create_context_with_input({
            "data": {
                "user": {
                    "name": "John"
                }
            }
        })
        result = _simple_resolve(context, "{{input.data.user.name}}")
        assert result == "John"

    def test_resolve_inputs_port(self):
        context = {
            "inputs": {
                "secondary": {"value": 42}
            }
        }
        result = _simple_resolve(context, "{{inputs.secondary.value}}")
        assert result == 42

    def test_resolve_node_output(self):
        context = create_context_with_node_output("fetch", {"ok": True})
        result = _simple_resolve(context, "{{fetch.ok}}")
        assert result is True

    def test_resolve_missing_returns_none(self):
        context = {}
        result = _simple_resolve(context, "{{missing}}")
        assert result is None

    def test_resolve_invalid_path_returns_none(self):
        context = create_context_with_input({"key": "value"})
        result = _simple_resolve(context, "{{input.nonexistent}}")
        assert result is None

    def test_resolve_without_braces_returns_none(self):
        context = create_context_with_input("hello")
        result = _simple_resolve(context, "input")
        assert result is None


# =============================================================================
# _substitute_variables Tests
# =============================================================================

class TestSubstituteVariables:
    """Tests for _substitute_variables function"""

    def test_substitute_single_variable(self):
        context = create_context_with_input("World")
        result = _substitute_variables("Hello {{input}}", context, 1000)
        assert result == "Hello World"

    def test_substitute_multiple_variables(self):
        context = {
            "name": "Alice",
            "count": 5,
        }
        result = _substitute_variables("{{name}} has {{count}} items", context, 1000)
        assert result == "Alice has 5 items"

    def test_substitute_nested_variable(self):
        context = create_context_with_input({"user": {"name": "Bob"}})
        result = _substitute_variables("User: {{input.user.name}}", context, 1000)
        assert result == "User: Bob"

    def test_preserve_missing_variable(self):
        context = {}
        result = _substitute_variables("Hello {{missing}}", context, 1000)
        assert result == "Hello {{missing}}"

    def test_substitute_object_to_json(self):
        context = create_context_with_input({"key": "value"})
        result = _substitute_variables("Data: {{input}}", context, 1000)
        assert '"key"' in result
        assert '"value"' in result


# =============================================================================
# _resolve_from_input Tests
# =============================================================================

class TestResolveFromInput:
    """Tests for _resolve_from_input function"""

    def test_resolve_simple_input(self):
        context = create_context_with_input("hello world")
        result = _resolve_from_input(
            context=context,
            prompt_path="{{input}}",
            join_strategy="first",
            join_separator="",
            max_input_size=1000,
        )
        assert result == "hello world"

    def test_resolve_object_input(self):
        context = create_context_with_input({"message": "hello"})
        result = _resolve_from_input(
            context=context,
            prompt_path="{{input.message}}",
            join_strategy="first",
            join_separator="",
            max_input_size=1000,
        )
        assert result == "hello"

    def test_resolve_array_first_strategy(self):
        context = create_context_with_input(["first", "second", "third"])
        result = _resolve_from_input(
            context=context,
            prompt_path="{{input}}",
            join_strategy="first",
            join_separator="",
            max_input_size=1000,
        )
        assert result == "first"

    def test_resolve_array_newline_strategy(self):
        context = create_context_with_input(["line1", "line2"])
        result = _resolve_from_input(
            context=context,
            prompt_path="{{input}}",
            join_strategy="newline",
            join_separator="",
            max_input_size=1000,
        )
        assert "line1\nline2" == result

    def test_resolve_missing_keeps_placeholder(self):
        context = {}
        result = _resolve_from_input(
            context=context,
            prompt_path="{{missing}}",
            join_strategy="first",
            join_separator="",
            max_input_size=1000,
        )
        # When variable is missing, placeholder is preserved (useful for debugging)
        assert result == "{{missing}}"


# =============================================================================
# _resolve_task_prompt Tests
# =============================================================================

class TestResolveTaskPrompt:
    """Tests for _resolve_task_prompt function"""

    def test_manual_mode_returns_task(self):
        context = {}
        params = {"task": "Do something"}
        result = _resolve_task_prompt(
            context=context,
            params=params,
            prompt_source="manual",
            prompt_path="{{input}}",
            join_strategy="first",
            join_separator="",
            max_input_size=1000,
        )
        assert result == "Do something"

    def test_manual_mode_with_variable_substitution(self):
        context = create_context_with_input("World")
        params = {"task": "Hello {{input}}"}
        result = _resolve_task_prompt(
            context=context,
            params=params,
            prompt_source="manual",
            prompt_path="{{input}}",
            join_strategy="first",
            join_separator="",
            max_input_size=1000,
        )
        assert result == "Hello World"

    def test_auto_mode_from_input(self):
        context = create_context_with_input("Analyze this data")
        params = {}
        result = _resolve_task_prompt(
            context=context,
            params=params,
            prompt_source="auto",
            prompt_path="{{input}}",
            join_strategy="first",
            join_separator="",
            max_input_size=1000,
        )
        assert result == "Analyze this data"

    def test_auto_mode_custom_path(self):
        context = create_context_with_input({"prompt": "Custom prompt"})
        params = {}
        result = _resolve_task_prompt(
            context=context,
            params=params,
            prompt_source="auto",
            prompt_path="{{input.prompt}}",
            join_strategy="first",
            join_separator="",
            max_input_size=1000,
        )
        assert result == "Custom prompt"

    def test_auto_mode_array_join(self):
        context = create_context_with_input(["task1", "task2"])
        params = {}
        result = _resolve_task_prompt(
            context=context,
            params=params,
            prompt_source="auto",
            prompt_path="{{input}}",
            join_strategy="newline",
            join_separator="",
            max_input_size=1000,
        )
        assert "task1" in result
        assert "task2" in result

    def test_auto_mode_missing_input_keeps_placeholder(self):
        context = {}
        params = {}
        result = _resolve_task_prompt(
            context=context,
            params=params,
            prompt_source="auto",
            prompt_path="{{input}}",
            join_strategy="first",
            join_separator="",
            max_input_size=1000,
        )
        # When input is missing, placeholder is preserved
        assert result == "{{input}}"

    def test_manual_mode_empty_task(self):
        context = {}
        params = {"task": ""}
        result = _resolve_task_prompt(
            context=context,
            params=params,
            prompt_source="manual",
            prompt_path="{{input}}",
            join_strategy="first",
            join_separator="",
            max_input_size=1000,
        )
        assert result == ""


# =============================================================================
# Integration Tests
# =============================================================================

class TestPromptResolutionIntegration:
    """Integration tests for the complete prompt resolution flow"""

    def test_n8n_style_auto_from_chat(self):
        """Simulate n8n-style AI Agent receiving chat input"""
        context = create_context_with_input({
            "chatInput": "What is the weather today?",
            "sessionId": "session123",
        })
        params = {}

        # Using chatInput field
        result = _resolve_task_prompt(
            context=context,
            params=params,
            prompt_source="auto",
            prompt_path="{{input.chatInput}}",
            join_strategy="first",
            join_separator="",
            max_input_size=1000,
        )
        assert result == "What is the weather today?"

    def test_n8n_style_manual_with_template(self):
        """Simulate n8n-style AI Agent with template"""
        context = create_context_with_input({
            "document": "Long document content here...",
            "question": "Summarize this",
        })
        params = {"task": "Based on the document:\n{{input.document}}\n\nAnswer: {{input.question}}"}

        result = _resolve_task_prompt(
            context=context,
            params=params,
            prompt_source="manual",
            prompt_path="{{input}}",
            join_strategy="first",
            join_separator="",
            max_input_size=1000,
        )
        assert "Long document content here..." in result
        assert "Summarize this" in result

    def test_batch_processing_with_array(self):
        """Test processing multiple items from upstream node"""
        context = create_context_with_input([
            {"title": "Article 1", "content": "Content 1"},
            {"title": "Article 2", "content": "Content 2"},
        ])
        params = {}

        # JSON strategy for structured data
        result = _resolve_task_prompt(
            context=context,
            params=params,
            prompt_source="auto",
            prompt_path="{{input}}",
            join_strategy="json",
            join_separator="",
            max_input_size=10000,
        )
        parsed = json.loads(result)
        assert len(parsed) == 2
        assert parsed[0]["title"] == "Article 1"
