"""
Tests for Serialization Safety

Verifies that sub-node results containing Python objects (ChatModel, AgentTool)
don't crash serialization paths (JSON.dumps, WebSocket, SQLite).
"""

import json
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.modules.atomic.llm._interfaces import ChatResponse, ToolCallRequest
from core.modules.atomic.llm._chat_models import OpenAIChatModel, AnthropicChatModel
from core.modules.atomic.llm._agent_tool import ModuleAgentTool


class TestChatModelNotSerializable:
    """Verify that ChatModel objects break plain json.dumps but are handled safely."""

    def test_openai_model_not_json_serializable(self):
        model = OpenAIChatModel(api_key="test", model="gpt-4o")
        with pytest.raises(TypeError):
            json.dumps({"chat_model": model})

    def test_openai_model_safe_with_default_str(self):
        model = OpenAIChatModel(api_key="test", model="gpt-4o")
        result = json.dumps({"chat_model": model}, default=str)
        assert "OpenAIChatModel" in result

    def test_anthropic_model_not_json_serializable(self):
        model = AnthropicChatModel(api_key="test")
        with pytest.raises(TypeError):
            json.dumps({"chat_model": model})


class TestStripTransientKeys:
    """Test the engine's _strip_transient_keys helper."""

    def test_strips_chat_model(self):
        from core.engine.workflow.engine import _strip_transient_keys

        model = OpenAIChatModel(api_key="test")
        result = {
            "ok": True, "__data_type__": "ai_model",
            "provider": "openai", "config": {"key": "val"},
            "chat_model": model,
        }
        safe = _strip_transient_keys(result)
        assert "chat_model" not in safe
        assert safe["ok"] is True
        assert safe["provider"] == "openai"
        # Verify it's JSON-serializable now
        json.dumps(safe)

    def test_strips_tool_object(self):
        from core.engine.workflow.engine import _strip_transient_keys

        result = {
            "ok": True, "__data_type__": "ai_tool",
            "module_id": "http.request",
            "tool": object(),  # non-serializable
        }
        safe = _strip_transient_keys(result)
        assert "tool" not in safe
        assert safe["module_id"] == "http.request"
        json.dumps(safe)

    def test_non_dict_passthrough(self):
        from core.engine.workflow.engine import _strip_transient_keys
        assert _strip_transient_keys("hello") == "hello"
        assert _strip_transient_keys(42) == 42

    def test_no_transient_keys_unchanged(self):
        from core.engine.workflow.engine import _strip_transient_keys
        result = {"ok": True, "data": "test"}
        assert _strip_transient_keys(result) == result


class TestAiModelSubNodeOutput:
    """Test that ai.model output is safe for the full pipeline."""

    @pytest.mark.asyncio
    async def test_output_contains_both_config_and_chat_model(self):
        """ai.model returns both serializable config and ChatModel object."""
        import os
        os.environ["OPENAI_API_KEY"] = "test-key-for-test"
        try:
            from core.modules.registry import ModuleRegistry
            import core.modules.atomic

            module_class = ModuleRegistry.get("ai.model")
            instance = module_class(
                {"provider": "openai", "model": "gpt-4o", "temperature": 0.7},
                {"params": {"provider": "openai", "model": "gpt-4o", "temperature": 0.7}},
            )
            result = await instance.execute()

            # Has both old and new fields
            assert result["ok"] is True
            assert result["config"]["provider"] == "openai"
            assert result["chat_model"] is not None
            assert result["chat_model"].provider == "openai"

            # Stripped version is JSON-safe
            from core.engine.workflow.engine import _strip_transient_keys
            safe = _strip_transient_keys(result)
            serialized = json.dumps(safe)
            assert "openai" in serialized
        finally:
            os.environ.pop("OPENAI_API_KEY", None)


class TestAiToolSubNodeOutput:
    """Test that ai.tool output is safe for the full pipeline."""

    @pytest.mark.asyncio
    async def test_output_contains_both_module_id_and_tool(self):
        """ai.tool returns both module_id string and AgentTool object."""
        from core.modules.registry import ModuleRegistry
        import core.modules.atomic

        module_class = ModuleRegistry.get("ai.tool")
        params = {"module_id": "string.uppercase"}
        instance = module_class(
            params,
            {"params": params},
        )
        result = await instance.execute()

        assert result["ok"] is True
        assert result["module_id"] == "string.uppercase"
        assert result["tool"] is not None
        assert result["tool"].name == "string--uppercase"

        # Stripped version is JSON-safe
        from core.engine.workflow.engine import _strip_transient_keys
        safe = _strip_transient_keys(result)
        serialized = json.dumps(safe)
        assert "string.uppercase" in serialized


class TestBackwardCompatibility:
    """Test that old-style sub-node outputs (no chat_model/tool) still work."""

    def test_resolve_chat_model_from_config_only(self):
        from core.modules.atomic.llm.agent import _resolve_chat_model

        # Old format: no chat_model key
        context = {"inputs": {"model": {
            "__data_type__": "ai_model",
            "config": {"provider": "openai", "model": "gpt-4o", "api_key": "test", "temperature": 0.5},
        }}}
        model = _resolve_chat_model(context)
        assert model is not None
        assert model.provider == "openai"
        assert model.model_name == "gpt-4o"

    def test_resolve_tools_from_module_id_only(self):
        from core.modules.atomic.llm.agent import _resolve_tools

        # Old format: no tool key
        context = {"inputs": {"tools": [
            {"__data_type__": "ai_tool", "module_id": "http.request"},
            {"__data_type__": "ai_tool", "module_id": "data.json_parse"},
        ]}}
        tools = _resolve_tools(context, [])
        assert len(tools) == 2
        assert tools[0].module_id == "http.request"
        assert tools[1].module_id == "data.json_parse"
