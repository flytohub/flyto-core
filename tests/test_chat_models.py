"""
Tests for ChatModel Implementations (_chat_models.py)

Tests OpenAIChatModel and AnthropicChatModel with mocked HTTP calls.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.modules.atomic.llm._interfaces import ChatResponse, ToolCall, ToolCallRequest
from core.modules.atomic.llm._chat_models import (
    OpenAIChatModel, AnthropicChatModel, create_chat_model,
    _tool_requests_to_openai, _tool_requests_to_anthropic, _messages_to_anthropic,
)


# ── Helper factories ─────────────────────────────────────────────


def _openai_response(content="Hello", tool_calls=None, tokens=50):
    msg = {"content": content, "role": "assistant"}
    if tool_calls:
        msg["tool_calls"] = tool_calls
        msg["content"] = None
    return {
        "choices": [{"message": msg, "finish_reason": "stop"}],
        "usage": {"total_tokens": tokens},
    }


def _anthropic_response(text="Hello", tool_uses=None, tokens_in=10, tokens_out=20):
    content = []
    if text:
        content.append({"type": "text", "text": text})
    if tool_uses:
        content.extend(tool_uses)
    return {
        "content": content,
        "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out},
        "stop_reason": "end_turn",
    }


# ── Tool format conversion ──────────────────────────────────────


class TestToolFormatConversion:
    def test_to_openai(self):
        req = ToolCallRequest(name="test", description="desc", parameters={"type": "object", "properties": {}})
        result = _tool_requests_to_openai([req])
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "test"

    def test_to_anthropic(self):
        req = ToolCallRequest(name="test", description="desc", parameters={"type": "object", "properties": {}})
        result = _tool_requests_to_anthropic([req])
        assert len(result) == 1
        assert result[0]["name"] == "test"
        assert "input_schema" in result[0]


class TestMessageConversion:
    def test_system_extracted(self):
        messages = [
            {"role": "system", "content": "Be helpful"},
            {"role": "user", "content": "Hi"},
        ]
        system, msgs = _messages_to_anthropic(messages)
        assert system == "Be helpful"
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_tool_messages_converted(self):
        messages = [
            {"role": "tool", "tool_call_id": "tc1", "content": '{"ok": true}'},
        ]
        _, msgs = _messages_to_anthropic(messages)
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"][0]["type"] == "tool_result"

    def test_assistant_tool_calls_converted(self):
        messages = [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc1", "name": "test", "arguments": {"x": 1}}
            ]},
        ]
        _, msgs = _messages_to_anthropic(messages)
        assert msgs[0]["role"] == "assistant"
        assert msgs[0]["content"][0]["type"] == "tool_use"


# ── OpenAIChatModel ─────────────────────────────────────────────


class TestOpenAIChatModel:
    @pytest.mark.asyncio
    async def test_simple_chat(self):
        model = OpenAIChatModel(api_key="test-key", model="gpt-4o")
        with patch("core.modules.atomic.llm._chat_models._http_post", new_callable=AsyncMock) as mock:
            mock.return_value = _openai_response("Hello world", tokens=42)
            resp = await model.chat([{"role": "user", "content": "hi"}])
            assert isinstance(resp, ChatResponse)
            assert resp.content == "Hello world"
            assert resp.tokens_used == 42
            assert resp.tool_calls == []

    @pytest.mark.asyncio
    async def test_with_tool_calls(self):
        model = OpenAIChatModel(api_key="test-key")
        tc = [{"id": "tc1", "type": "function", "function": {"name": "browser--click", "arguments": '{"selector": "#btn"}'}}]
        with patch("core.modules.atomic.llm._chat_models._http_post", new_callable=AsyncMock) as mock:
            mock.return_value = _openai_response(tool_calls=tc, tokens=100)
            resp = await model.chat([{"role": "user", "content": "click"}])
            assert len(resp.tool_calls) == 1
            assert resp.tool_calls[0].name == "browser--click"
            assert resp.tool_calls[0].arguments == '{"selector": "#btn"}'

    @pytest.mark.asyncio
    async def test_api_error(self):
        model = OpenAIChatModel(api_key="test-key")
        with patch("core.modules.atomic.llm._chat_models._http_post", new_callable=AsyncMock) as mock:
            mock.return_value = {"error": {"message": "Rate limited"}}
            with pytest.raises(RuntimeError, match="Rate limited"):
                await model.chat([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_tools_passed_in_payload(self):
        model = OpenAIChatModel(api_key="test-key")
        tool = ToolCallRequest(name="test", description="d", parameters={"type": "object", "properties": {}})
        with patch("core.modules.atomic.llm._chat_models._http_post", new_callable=AsyncMock) as mock:
            mock.return_value = _openai_response("ok")
            await model.chat([{"role": "user", "content": "hi"}], tools=[tool])
            payload = mock.call_args[0][2]  # url, headers, payload
            assert "tools" in payload
            assert payload["tools"][0]["function"]["name"] == "test"

    def test_properties(self):
        model = OpenAIChatModel(api_key="k", model="gpt-4o-mini")
        assert model.provider == "openai"
        assert model.model_name == "gpt-4o-mini"


# ── AnthropicChatModel ──────────────────────────────────────────


class TestAnthropicChatModel:
    @pytest.mark.asyncio
    async def test_simple_chat(self):
        model = AnthropicChatModel(api_key="test-key", model="claude-sonnet-4-6")
        with patch("core.modules.atomic.llm._chat_models._http_post", new_callable=AsyncMock) as mock:
            mock.return_value = _anthropic_response("Hello from Claude")
            resp = await model.chat([{"role": "user", "content": "hi"}])
            assert resp.content == "Hello from Claude"
            assert resp.tokens_used == 30  # 10 + 20

    @pytest.mark.asyncio
    async def test_with_tool_use(self):
        model = AnthropicChatModel(api_key="test-key")
        tool_block = {"type": "tool_use", "id": "tu1", "name": "browser--click", "input": {"selector": "#btn"}}
        with patch("core.modules.atomic.llm._chat_models._http_post", new_callable=AsyncMock) as mock:
            mock.return_value = _anthropic_response(text="", tool_uses=[tool_block])
            resp = await model.chat([{"role": "user", "content": "click"}])
            assert len(resp.tool_calls) == 1
            assert resp.tool_calls[0].name == "browser--click"
            args = json.loads(resp.tool_calls[0].arguments)
            assert args["selector"] == "#btn"

    @pytest.mark.asyncio
    async def test_api_error(self):
        model = AnthropicChatModel(api_key="test-key")
        with patch("core.modules.atomic.llm._chat_models._http_post", new_callable=AsyncMock) as mock:
            mock.return_value = {"error": {"message": "Overloaded"}}
            with pytest.raises(RuntimeError, match="Overloaded"):
                await model.chat([{"role": "user", "content": "hi"}])

    def test_properties(self):
        model = AnthropicChatModel(api_key="k", model="claude-sonnet-4-6")
        assert model.provider == "anthropic"
        assert model.model_name == "claude-sonnet-4-6"


# ── Factory ──────────────────────────────────────────────────────


class TestCreateChatModel:
    def test_openai(self):
        m = create_chat_model(provider="openai", api_key="k", model="gpt-4o")
        assert isinstance(m, OpenAIChatModel)

    def test_anthropic(self):
        m = create_chat_model(provider="anthropic", api_key="k", model="claude-sonnet-4-6")
        assert isinstance(m, AnthropicChatModel)

    def test_unknown_defaults_to_openai(self):
        m = create_chat_model(provider="ollama", api_key="k", model="llama3")
        assert isinstance(m, OpenAIChatModel)
