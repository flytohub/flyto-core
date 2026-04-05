"""
Tests for ModuleAgentTool (_agent_tool.py)

Tests schema conversion, tool name mapping, and mocked execution.
"""

import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.modules.atomic.llm._interfaces import ToolCallRequest
from core.modules.atomic.llm._agent_tool import ModuleAgentTool, _params_to_json_schema


# ── Schema Conversion ────────────────────────────────────────────


class TestParamsToJsonSchema:
    def test_basic_string(self):
        schema = _params_to_json_schema({"url": {"type": "string", "description": "URL", "required": True}})
        assert schema["properties"]["url"]["type"] == "string"
        assert "url" in schema["required"]

    def test_array_gets_items(self):
        schema = _params_to_json_schema({"tags": {"type": "array", "description": "Tags"}})
        assert schema["properties"]["tags"]["items"] == {"type": "string"}

    def test_array_with_custom_items(self):
        schema = _params_to_json_schema({"data": {"type": "array", "items": {"type": "object"}}})
        assert schema["properties"]["data"]["items"] == {"type": "object"}

    def test_select_to_enum(self):
        schema = _params_to_json_schema({
            "method": {
                "type": "select",
                "options": [{"value": "GET", "label": "GET"}, {"value": "POST", "label": "POST"}],
            }
        })
        assert schema["properties"]["method"]["type"] == "string"
        assert schema["properties"]["method"]["enum"] == ["GET", "POST"]

    def test_object_with_properties(self):
        schema = _params_to_json_schema({
            "config": {"type": "object", "properties": {"key": {"type": "string"}}},
        })
        assert "key" in schema["properties"]["config"]["properties"]

    def test_list_format(self):
        schema = _params_to_json_schema([
            {"name": "url", "type": "string", "required": True},
            {"name": "timeout", "type": "number", "default": 30},
        ])
        assert "url" in schema["properties"]
        assert schema["properties"]["timeout"]["default"] == 30

    def test_empty_schema(self):
        schema = _params_to_json_schema({})
        assert schema == {"type": "object", "properties": {}, "required": []}

    def test_none_schema(self):
        schema = _params_to_json_schema(None)
        assert schema["type"] == "object"


# ── ModuleAgentTool ──────────────────────────────────────────────


class TestModuleAgentTool:
    def _mock_registry(self, module_id="http.request", metadata=None):
        """Create a mock registry with a single module."""
        mock_reg = MagicMock()
        mock_reg.has.return_value = True
        mock_reg.get_metadata.return_value = metadata or {
            "description": "Make HTTP requests",
            "params_schema": {"url": {"type": "string", "required": True, "description": "URL"}},
        }
        return mock_reg

    def test_name_format(self):
        tool = ModuleAgentTool(module_id="browser.click")
        assert tool.name == "browser--click"

    def test_module_id_property(self):
        tool = ModuleAgentTool(module_id="http.request")
        assert tool.module_id == "http.request"

    def test_custom_description(self):
        tool = ModuleAgentTool(module_id="http.request", description="Custom desc")
        assert tool.description == "Custom desc"

    def test_description_from_metadata(self):
        tool = ModuleAgentTool(module_id="http.request")
        with patch("core.modules.atomic.llm._agent_tool._get_registry") as mock:
            mock.return_value = self._mock_registry()
            assert tool.description == "Make HTTP requests"

    def test_to_tool_call_request(self):
        tool = ModuleAgentTool(module_id="http.request")
        with patch("core.modules.atomic.llm._agent_tool._get_registry") as mock:
            mock.return_value = self._mock_registry()
            req = tool.to_tool_call_request()
            assert isinstance(req, ToolCallRequest)
            assert req.name == "http--request"
            assert "url" in req.parameters["properties"]

    def test_name_roundtrip(self):
        """module_id → tool name → module_id round-trip."""
        original = "api.google_sheets.read"
        tool = ModuleAgentTool(module_id=original)
        assert tool.name == "api--google_sheets--read"
        recovered = tool.name.replace("--", ".")
        assert recovered == original

    @pytest.mark.asyncio
    async def test_invoke_success(self):
        mock_module_class = MagicMock()
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value={"ok": True, "data": "result"})
        mock_module_class.return_value = mock_instance

        mock_reg = MagicMock()
        mock_reg.has.return_value = True
        mock_reg.get.return_value = mock_module_class

        tool = ModuleAgentTool(module_id="http.request", parent_context={"variables": {}})
        with patch("core.modules.atomic.llm._agent_tool._get_registry", return_value=mock_reg):
            result = await tool.invoke({"url": "https://example.com"})
            assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_invoke_module_not_found(self):
        mock_reg = MagicMock()
        mock_reg.has.return_value = False

        tool = ModuleAgentTool(module_id="nonexistent.module")
        with patch("core.modules.atomic.llm._agent_tool._get_registry", return_value=mock_reg):
            result = await tool.invoke({})
            assert result["ok"] is False
            assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_invoke_with_agent_context_override(self):
        mock_module_class = MagicMock()
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value={"ok": True})
        mock_module_class.return_value = mock_instance

        mock_reg = MagicMock()
        mock_reg.has.return_value = True
        mock_reg.get.return_value = mock_module_class

        parent_ctx = {"variables": {"old": True}, "_agent_depth": 0}
        agent_ctx = {"variables": {"new": True}, "_agent_depth": 2, "browser": "mock"}

        tool = ModuleAgentTool(module_id="test.tool", parent_context=parent_ctx)
        with patch("core.modules.atomic.llm._agent_tool._get_registry", return_value=mock_reg):
            await tool.invoke({"arg": 1}, agent_context=agent_ctx)
            # Verify agent_context was used, not parent_context
            call_args = mock_module_class.call_args
            ctx = call_args[0][1]  # second positional arg is context
            assert ctx["_agent_depth"] == 2
            assert ctx["browser"] == "mock"
