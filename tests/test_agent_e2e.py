"""
End-to-End Agent Integration Tests

These tests hit REAL APIs and cost real money.
Only run manually: pytest tests/test_agent_e2e.py -v -s

Required env vars:
  OPENAI_API_KEY — for OpenAI tests
  ANTHROPIC_API_KEY — for Anthropic tests (optional)
"""

import json
import os
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.modules.atomic.llm._interfaces import ChatResponse, ToolCallRequest
from core.modules.atomic.llm._chat_models import OpenAIChatModel, AnthropicChatModel


# Skip all tests if no API key
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set — skip real API tests"
)


class TestOpenAIRealAPI:
    """Real OpenAI API calls — verifies response parsing is correct."""

    @pytest.mark.asyncio
    async def test_simple_chat(self):
        model = OpenAIChatModel(
            api_key=os.environ["OPENAI_API_KEY"],
            model="gpt-4o-mini",
            temperature=0,
        )
        resp = await model.chat([{"role": "user", "content": "Reply with exactly: PONG"}])
        assert isinstance(resp, ChatResponse)
        assert "PONG" in resp.content
        assert resp.tokens_used > 0
        print(f"  tokens: {resp.tokens_used}, content: {resp.content[:100]}")

    @pytest.mark.asyncio
    async def test_tool_calling(self):
        model = OpenAIChatModel(
            api_key=os.environ["OPENAI_API_KEY"],
            model="gpt-4o-mini",
            temperature=0,
        )
        tools = [ToolCallRequest(
            name="get_weather",
            description="Get weather for a city",
            parameters={
                "type": "object",
                "properties": {"city": {"type": "string", "description": "City name"}},
                "required": ["city"],
            },
        )]
        resp = await model.chat(
            [{"role": "user", "content": "What's the weather in Tokyo?"}],
            tools=tools,
        )
        assert isinstance(resp, ChatResponse)
        assert len(resp.tool_calls) > 0, f"Expected tool call, got: {resp.content}"
        tc = resp.tool_calls[0]
        assert tc.name == "get_weather"
        args = json.loads(tc.arguments)
        assert "Tokyo" in args.get("city", "") or "tokyo" in args.get("city", "").lower()
        print(f"  tool_call: {tc.name}({tc.arguments})")

    @pytest.mark.asyncio
    async def test_no_tool_call_when_not_needed(self):
        model = OpenAIChatModel(
            api_key=os.environ["OPENAI_API_KEY"],
            model="gpt-4o-mini",
            temperature=0,
        )
        tools = [ToolCallRequest(
            name="get_weather",
            description="Get weather for a city",
            parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
        )]
        resp = await model.chat(
            [{"role": "user", "content": "What is 2+2?"}],
            tools=tools,
        )
        assert len(resp.tool_calls) == 0, f"Unexpected tool call: {resp.tool_calls}"
        assert "4" in resp.content
        print(f"  content: {resp.content[:100]}")

    @pytest.mark.asyncio
    async def test_multi_turn_with_tool_result(self):
        """Simulate a full agent loop: user → tool call → tool result → final answer."""
        model = OpenAIChatModel(
            api_key=os.environ["OPENAI_API_KEY"],
            model="gpt-4o-mini",
            temperature=0,
        )
        tools = [ToolCallRequest(
            name="get_weather",
            description="Get current weather",
            parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
        )]

        # Step 1: User asks
        messages = [
            {"role": "system", "content": "Use tools when needed."},
            {"role": "user", "content": "What's the weather in Paris?"},
        ]
        resp1 = await model.chat(messages, tools=tools)
        assert resp1.tool_calls, "Expected tool call"
        tc = resp1.tool_calls[0]

        # Step 2: Append tool result
        messages.append({
            "role": "assistant", "content": None,
            "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}}],
        })
        messages.append({
            "role": "tool", "tool_call_id": tc.id,
            "content": json.dumps({"temperature": 18, "condition": "partly cloudy"}),
        })

        # Step 3: Get final answer
        resp2 = await model.chat(messages, tools=tools)
        assert not resp2.tool_calls, f"Expected final answer, got tool calls: {resp2.tool_calls}"
        assert resp2.content
        print(f"  final: {resp2.content[:200]}")


@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set"
)
class TestAnthropicRealAPI:
    """Real Anthropic API calls."""

    @pytest.mark.asyncio
    async def test_simple_chat(self):
        model = AnthropicChatModel(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            model="claude-haiku-4-5-20251001",
            temperature=0,
        )
        resp = await model.chat([{"role": "user", "content": "Reply with exactly: PONG"}])
        assert isinstance(resp, ChatResponse)
        assert "PONG" in resp.content
        assert resp.tokens_used > 0
        print(f"  tokens: {resp.tokens_used}, content: {resp.content[:100]}")

    @pytest.mark.asyncio
    async def test_tool_calling(self):
        model = AnthropicChatModel(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            model="claude-haiku-4-5-20251001",
            temperature=0,
        )
        tools = [ToolCallRequest(
            name="get_weather",
            description="Get weather for a city",
            parameters={
                "type": "object",
                "properties": {"city": {"type": "string", "description": "City name"}},
                "required": ["city"],
            },
        )]
        resp = await model.chat(
            [{"role": "user", "content": "What's the weather in Tokyo?"}],
            tools=tools,
        )
        assert len(resp.tool_calls) > 0, f"Expected tool call, got: {resp.content}"
        tc = resp.tool_calls[0]
        assert tc.name == "get_weather"
        args = json.loads(tc.arguments)
        assert "Tokyo" in args.get("city", "") or "tokyo" in args.get("city", "").lower()
        print(f"  tool_call: {tc.name}({tc.arguments})")

    @pytest.mark.asyncio
    async def test_system_message_handling(self):
        """Verify system message extraction for Anthropic format."""
        model = AnthropicChatModel(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            model="claude-haiku-4-5-20251001",
            temperature=0,
        )
        resp = await model.chat([
            {"role": "system", "content": "You are a pirate. Always say 'Arrr'."},
            {"role": "user", "content": "Hello"},
        ])
        assert "arr" in resp.content.lower() or "ahoy" in resp.content.lower()
        print(f"  pirate: {resp.content[:100]}")


class TestFullAgentLoopE2E:
    """End-to-end test of the full agent loop with real LLM."""

    @pytest.mark.asyncio
    async def test_agent_with_mock_tool_real_llm(self):
        """Real LLM + mock tool — verifies the full loop works."""
        from unittest.mock import MagicMock, AsyncMock
        from core.modules.registry import ModuleRegistry
        import core.modules.atomic

        # Real ChatModel
        chat_model = OpenAIChatModel(
            api_key=os.environ["OPENAI_API_KEY"],
            model="gpt-4o-mini",
            temperature=0,
        )

        # Mock tool
        mock_tool = MagicMock()
        mock_tool.name = "calculator"
        mock_tool.module_id = "calculator"
        mock_tool.description = "Calculate math expressions"
        mock_tool.to_tool_call_request.return_value = ToolCallRequest(
            name="calculator",
            description="Calculate a math expression and return the result",
            parameters={
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "Math expression"}},
                "required": ["expression"],
            },
        )
        mock_tool.invoke = AsyncMock(return_value={"ok": True, "result": "42"})

        # Run agent
        module_class = ModuleRegistry.get("llm.agent")
        context = {
            "params": {
                "prompt_source": "manual",
                "task": "What is 6 times 7? Use the calculator tool.",
                "tools": [],
                "system_prompt": "You must use the calculator tool for math. After getting the result, give the final answer.",
                "max_iterations": 5,
            },
            "inputs": {
                "model": {"__data_type__": "ai_model", "chat_model": chat_model},
                "tools": [{"__data_type__": "ai_tool", "tool": mock_tool}],
            },
        }

        instance = module_class(context.get("params", {}), context)
        result = await instance.execute()

        print(f"\n  Agent result: {json.dumps(result, indent=2, default=str)[:500]}")

        assert result["ok"] is True
        data = result["data"]
        assert "42" in data["result"] or "forty-two" in data["result"].lower()
        assert data["tool_calls"] >= 1
        assert data["tokens_used"] > 0
        print(f"  Tool calls: {data['tool_calls']}, Tokens: {data['tokens_used']}")
