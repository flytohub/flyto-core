"""
Tests for AI Agent Protocol Interfaces (_interfaces.py)

Verifies:
- Dataclass construction and field defaults
- Protocol isinstance checks with @runtime_checkable
- ChatResponse / ToolCall / ToolCallRequest serialization
"""

import json
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.modules.atomic.llm._interfaces import (
    ChatModel, AgentTool, ChatResponse, ToolCall, ToolCallRequest,
)


class TestToolCallRequest:
    def test_defaults(self):
        req = ToolCallRequest(name="test")
        assert req.name == "test"
        assert req.description == ""
        assert req.parameters == {"type": "object", "properties": {}}

    def test_full_construction(self):
        req = ToolCallRequest(
            name="browser--click",
            description="Click an element",
            parameters={"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]},
        )
        assert req.name == "browser--click"
        assert "selector" in req.parameters["properties"]

    def test_independent_defaults(self):
        """Each instance gets its own default dict (no shared mutable default)."""
        a = ToolCallRequest(name="a")
        b = ToolCallRequest(name="b")
        a.parameters["test"] = True
        assert "test" not in b.parameters


class TestToolCall:
    def test_construction(self):
        tc = ToolCall(id="call_1", name="browser--click", arguments='{"selector": "#btn"}')
        assert tc.id == "call_1"
        assert tc.name == "browser--click"
        assert json.loads(tc.arguments) == {"selector": "#btn"}


class TestChatResponse:
    def test_defaults(self):
        resp = ChatResponse()
        assert resp.content == ""
        assert resp.model == ""
        assert resp.tokens_used == 0
        assert resp.finish_reason == "stop"
        assert resp.tool_calls == []

    def test_with_tool_calls(self):
        tc = ToolCall(id="1", name="test", arguments="{}")
        resp = ChatResponse(content="", tool_calls=[tc], tokens_used=100)
        assert len(resp.tool_calls) == 1
        assert resp.tokens_used == 100

    def test_independent_tool_calls_list(self):
        a = ChatResponse()
        b = ChatResponse()
        a.tool_calls.append(ToolCall(id="1", name="t", arguments="{}"))
        assert len(b.tool_calls) == 0


class TestChatModelProtocol:
    def test_isinstance_check(self):
        """A class with the right methods satisfies ChatModel protocol."""
        class MockModel:
            @property
            def provider(self): return "mock"
            @property
            def model_name(self): return "mock-1"
            async def chat(self, messages, temperature=0.7, max_tokens=None, tools=None, tool_choice=None):
                return ChatResponse(content="hi")

        assert isinstance(MockModel(), ChatModel)

    def test_non_conforming_rejected(self):
        """A class missing methods does NOT satisfy ChatModel."""
        class Bad:
            pass
        assert not isinstance(Bad(), ChatModel)


class TestAgentToolProtocol:
    def test_isinstance_check(self):
        class MockTool:
            @property
            def name(self): return "test"
            @property
            def description(self): return "desc"
            def to_tool_call_request(self): return ToolCallRequest(name="test")
            async def invoke(self, arguments, agent_context=None): return {"ok": True}

        assert isinstance(MockTool(), AgentTool)

    def test_non_conforming_rejected(self):
        class Bad:
            pass
        assert not isinstance(Bad(), AgentTool)
