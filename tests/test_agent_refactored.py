"""
Tests for Refactored Agent Loop

Tests the full llm_agent function with mocked ChatModel and AgentTool objects.
Verifies the new protocol-based architecture works end-to-end.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.modules.atomic.llm._interfaces import ChatResponse, ToolCall, ToolCallRequest
from core.modules.atomic.llm.agent import (
    _resolve_chat_model, _resolve_memory, _resolve_tools, _summarize_tool_result,
)


async def _run_agent(context):
    """Run the llm.agent module using the engine's pattern (class-based wrapper)."""
    from core.modules.registry import ModuleRegistry
    import core.modules.atomic  # ensure registered

    module_class = ModuleRegistry.get("llm.agent")
    instance = module_class(context.get("params", {}), context)
    return await instance.execute()


# ── Mock Factories ───────────────────────────────────────────────


def make_mock_chat_model(responses):
    """Create a mock ChatModel that returns responses in sequence."""
    model = MagicMock()
    model.provider = "mock"
    model.model_name = "mock-1"
    model.chat = AsyncMock(side_effect=responses)
    return model


def make_mock_tool(name="test--tool", result=None):
    """Create a mock AgentTool."""
    tool = MagicMock()
    tool.name = name
    tool.module_id = name.replace("--", ".")
    tool.description = f"Mock tool {name}"
    tool.to_tool_call_request.return_value = ToolCallRequest(
        name=name, description=f"Mock tool {name}",
        parameters={"type": "object", "properties": {"arg": {"type": "string"}}},
    )
    tool.invoke = AsyncMock(return_value=result or {"ok": True, "data": "mock result"})
    return tool


# ── _resolve_chat_model ─────────────────────────────────────────


class TestResolveChatModel:
    def test_new_protocol(self):
        """New-style: reads chat_model object from input."""
        mock_model = MagicMock()
        mock_model.provider = "openai"
        mock_model.model_name = "gpt-4o"
        context = {"inputs": {"model": {"__data_type__": "ai_model", "chat_model": mock_model}}}
        result = _resolve_chat_model(context)
        assert result is mock_model

    def test_backward_compat_config(self):
        """Old-style: builds ChatModel from config dict."""
        context = {"inputs": {"model": {
            "__data_type__": "ai_model",
            "config": {"provider": "openai", "model": "gpt-4o", "api_key": "test-key", "temperature": 0.5},
        }}}
        result = _resolve_chat_model(context)
        assert result is not None
        assert result.provider == "openai"

    def test_no_model_connected(self):
        context = {"inputs": {}}
        assert _resolve_chat_model(context) is None

    def test_wrong_data_type(self):
        context = {"inputs": {"model": {"__data_type__": "ai_tool"}}}
        assert _resolve_chat_model(context) is None

    def test_inline_params_with_api_key(self):
        """Inline mode: no sub-node, model built from agent's own params."""
        context = {
            "inputs": {},
            "params": {"provider": "openai", "model": "gpt-4o-mini", "api_key": "test-key", "temperature": 0.5},
        }
        result = _resolve_chat_model(context)
        assert result is not None
        assert result.provider == "openai"
        assert result.model_name == "gpt-4o-mini"

    def test_inline_params_from_env(self):
        """Inline mode: API key from environment variable."""
        import os
        os.environ["OPENAI_API_KEY"] = "env-test-key"
        try:
            context = {
                "inputs": {},
                "params": {"provider": "openai", "model": "gpt-4o"},
            }
            result = _resolve_chat_model(context)
            assert result is not None
            assert result.provider == "openai"
        finally:
            os.environ.pop("OPENAI_API_KEY", None)

    def test_inline_params_no_key_returns_none(self):
        """Inline mode: no API key anywhere → returns None."""
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        context = {
            "inputs": {},
            "params": {"provider": "openai", "model": "gpt-4o"},
        }
        assert _resolve_chat_model(context) is None

    def test_subnode_overrides_inline(self):
        """Sub-node connected → inline params ignored."""
        mock_model = MagicMock()
        mock_model.provider = "anthropic"
        mock_model.model_name = "claude"
        context = {
            "inputs": {"model": {"__data_type__": "ai_model", "chat_model": mock_model}},
            "params": {"provider": "openai", "model": "gpt-4o", "api_key": "inline-key"},
        }
        result = _resolve_chat_model(context)
        assert result is mock_model  # sub-node wins, not inline


# ── _resolve_memory ──────────────────────────────────────────────


class TestResolveMemory:
    def test_with_messages(self):
        context = {"inputs": {"memory": {
            "__data_type__": "ai_memory",
            "messages": [{"role": "user", "content": "hi"}],
        }}}
        result = _resolve_memory(context)
        assert len(result) == 1

    def test_no_memory(self):
        assert _resolve_memory({"inputs": {}}) == []


# ── _resolve_tools ───────────────────────────────────────────────


class TestResolveTools:
    def test_new_protocol(self):
        """New-style: reads AgentTool objects."""
        mock_tool = MagicMock()
        mock_tool.module_id = "http.request"
        context = {"inputs": {"tools": [
            {"__data_type__": "ai_tool", "tool": mock_tool, "module_id": "http.request"},
        ]}}
        result = _resolve_tools(context)
        assert len(result) == 1
        assert result[0] is mock_tool

    def test_backward_compat_module_id(self):
        """Old-style: builds ModuleAgentTool from module_id."""
        context = {"inputs": {"tools": [
            {"__data_type__": "ai_tool", "module_id": "http.request"},
        ]}}
        result = _resolve_tools(context)
        assert len(result) == 1
        assert result[0].module_id == "http.request"

    def test_empty_tools(self):
        """No tools connected returns empty list."""
        result = _resolve_tools({"inputs": {}})
        assert len(result) == 0

    def test_single_tool_not_list(self):
        """Single tool input (not wrapped in list)."""
        mock_tool = MagicMock()
        mock_tool.module_id = "test"
        context = {"inputs": {"tools": {"__data_type__": "ai_tool", "tool": mock_tool}}}
        result = _resolve_tools(context)
        assert len(result) == 1


# ── _summarize_tool_result ───────────────────────────────────────


class TestSummarizeToolResult:
    def test_short_string_unchanged(self):
        assert _summarize_tool_result("hello") == "hello"

    def test_long_string_truncated(self):
        long = "x" * 600
        result = _summarize_tool_result(long)
        assert len(result) < 600
        assert result.endswith("...")

    def test_dict_large_values_summarized(self):
        result = _summarize_tool_result({"html": "x" * 1000, "ok": True})
        assert result["ok"] is True
        assert "chars" in result["html"]
        assert result["_summary"] is True

    def test_non_dict_non_string(self):
        assert _summarize_tool_result(42) == 42
        assert _summarize_tool_result(None) is None


# ── Full Agent Loop ──────────────────────────────────────────────


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_simple_chat_no_tools(self):
        """Agent with no tools — single LLM call, direct answer."""
        pass  # using _run_agent helper

        mock_model = make_mock_chat_model([
            ChatResponse(content="The answer is 42", tokens_used=50),
        ])

        context = {
            "params": {"prompt_source": "manual", "task": "What is 6*7?", "tools": [], "system_prompt": "Be helpful", "max_iterations": 5},
            "inputs": {"model": {"__data_type__": "ai_model", "chat_model": mock_model}},
        }
        result = await _run_agent(context)
        assert result["ok"] is True
        assert "The answer is 42" in (result.get("data", {}).get("result", "") or result.get("result", ""))
        assert result["data"]["tool_calls"] == 0

    @pytest.mark.asyncio
    async def test_tool_call_then_answer(self):
        """Agent calls a tool, then gives final answer."""
        pass  # using _run_agent helper

        mock_model = make_mock_chat_model([
            # First call: tool call
            ChatResponse(
                tool_calls=[ToolCall(id="tc1", name="http--request", arguments='{"url": "https://example.com"}')],
                tokens_used=30,
            ),
            # Second call: final answer
            ChatResponse(content="The page says hello", tokens_used=20),
        ])

        mock_tool = make_mock_tool("http--request", {"ok": True, "data": {"body": "hello"}})

        context = {
            "params": {"prompt_source": "manual", "task": "Fetch example.com", "tools": [], "system_prompt": "Use tools", "max_iterations": 5},
            "inputs": {
                "model": {"__data_type__": "ai_model", "chat_model": mock_model},
                "tools": [{"__data_type__": "ai_tool", "tool": mock_tool, "module_id": "http.request"}],
            },
        }
        result = await _run_agent(context)
        assert result["ok"] is True
        assert result["data"]["tool_calls"] == 1
        assert result["data"]["tokens_used"] == 50
        mock_tool.invoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_max_iterations_reached(self):
        """Agent hits max iterations."""
        pass  # using _run_agent helper

        # Always returns tool calls, never final answer
        mock_model = make_mock_chat_model([
            ChatResponse(tool_calls=[ToolCall(id=f"tc{i}", name="test--tool", arguments="{}")], tokens_used=10)
            for i in range(3)
        ])
        mock_tool = make_mock_tool("test--tool")

        context = {
            "params": {"prompt_source": "manual", "task": "Loop", "tools": [], "system_prompt": "x", "max_iterations": 3},
            "inputs": {
                "model": {"__data_type__": "ai_model", "chat_model": mock_model},
                "tools": [{"__data_type__": "ai_tool", "tool": mock_tool}],
            },
        }
        result = await _run_agent(context)
        assert result["ok"] is True
        assert result["data"]["warning"] == "max_iterations_reached"

    @pytest.mark.asyncio
    async def test_recursion_guard(self):
        """Agent rejects execution when depth exceeded."""
        pass  # using _run_agent helper

        context = {
            "params": {"prompt_source": "manual", "task": "x", "tools": []},
            "inputs": {"model": {"__data_type__": "ai_model", "chat_model": MagicMock()}},
            "_agent_depth": 3,
        }
        result = await _run_agent(context)
        assert result["ok"] is False
        assert result["error_code"] == "RECURSION_LIMIT"

    @pytest.mark.asyncio
    async def test_missing_model(self):
        """Agent fails gracefully when no model connected."""
        pass  # using _run_agent helper

        context = {
            "params": {"prompt_source": "manual", "task": "test", "tools": []},
            "inputs": {},
        }
        result = await _run_agent(context)
        assert result["ok"] is False
        assert result["error_code"] == "MISSING_MODEL"

    @pytest.mark.asyncio
    async def test_llm_error_handled(self):
        """Agent handles LLM call failure."""
        pass  # using _run_agent helper

        mock_model = MagicMock()
        mock_model.provider = "openai"
        mock_model.model_name = "gpt-4o"
        mock_model.chat = AsyncMock(side_effect=RuntimeError("API down"))

        context = {
            "params": {"prompt_source": "manual", "task": "test", "tools": [], "system_prompt": "x", "max_iterations": 1},
            "inputs": {"model": {"__data_type__": "ai_model", "chat_model": mock_model}},
        }
        result = await _run_agent(context)
        assert result["ok"] is False
        assert "LLM call failed" in result["error"]

    @pytest.mark.asyncio
    async def test_inline_model_no_subnode(self):
        """Agent works with inline params (no ai.model sub-node needed)."""
        # Patch create_chat_model to return our mock
        mock_model = make_mock_chat_model([
            ChatResponse(content="Inline works!", tokens_used=25),
        ])
        with patch("core.modules.atomic.llm.agent.create_chat_model", return_value=mock_model):
            context = {
                "params": {
                    "prompt_source": "manual", "task": "Hello",
                    "provider": "openai", "model": "gpt-4o", "api_key": "test-key",
                    "tools": [], "system_prompt": "Be brief", "max_iterations": 3,
                },
                "inputs": {},  # NO model sub-node
            }
            result = await _run_agent(context)
            assert result["ok"] is True
            assert "Inline works!" in str(result.get("data", {}).get("result", ""))

    @pytest.mark.asyncio
    async def test_notify_callback_called(self):
        """Agent calls notify callback for tool events."""
        pass  # using _run_agent helper

        notify = AsyncMock()
        mock_model = make_mock_chat_model([
            ChatResponse(tool_calls=[ToolCall(id="tc1", name="test--tool", arguments="{}")], tokens_used=10),
            ChatResponse(content="done", tokens_used=5),
        ])
        mock_tool = make_mock_tool("test--tool")

        context = {
            "params": {"prompt_source": "manual", "task": "test", "tools": [], "system_prompt": "x", "max_iterations": 5},
            "inputs": {
                "model": {"__data_type__": "ai_model", "chat_model": mock_model},
                "tools": [{"__data_type__": "ai_tool", "tool": mock_tool}],
            },
            "_agent_notify": notify,
        }
        await _run_agent(context)

        # Should have iteration + tool_call + tool_result events
        event_types = [call.args[0] for call in notify.call_args_list]
        assert "agent:iteration" in event_types
        assert "agent:tool_call" in event_types
        assert "agent:tool_result" in event_types
