# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
ChatModel Implementations

Concrete LLM provider implementations satisfying the ChatModel protocol.
Each class encapsulates provider-specific HTTP calls, message format conversion,
and tool definition formatting.

Migrated from _providers.py to eliminate provider dispatch in agent.py.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ._interfaces import ChatResponse, ToolCall, ToolCallRequest

logger = logging.getLogger(__name__)


def _tool_requests_to_openai(tools: List[ToolCallRequest]) -> List[Dict]:
    """Convert ToolCallRequest list to OpenAI function calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def _tool_requests_to_anthropic(tools: List[ToolCallRequest]) -> List[Dict]:
    """Convert ToolCallRequest list to Anthropic tool format."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters,
        }
        for t in tools
    ]


def _messages_to_anthropic(messages: List[Dict]) -> tuple:
    """Convert OpenAI-format messages to Anthropic format.

    Returns (system_prompt, anthropic_messages).
    """
    system = None
    anthropic_messages = []

    for msg in messages:
        if msg["role"] == "system":
            system = msg["content"]
        elif msg["role"] == "tool":
            anthropic_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_call_id", "unknown"),
                            "content": msg["content"],
                        }
                    ],
                }
            )
        elif msg.get("tool_calls"):
            content = []
            for tc in msg["tool_calls"]:
                args = tc.get("arguments") or tc.get("function", {}).get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                content.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id", tc.get("name", "unknown")),
                        "name": tc.get("name") or tc.get("function", {}).get("name", "unknown"),
                        "input": args,
                    }
                )
            anthropic_messages.append({"role": "assistant", "content": content})
        else:
            anthropic_messages.append(msg)

    return system, anthropic_messages


async def _http_post(url: str, headers: Dict, payload: Dict) -> Dict:
    """HTTP POST with httpx, aiohttp fallback. Validates response status."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 500:
                raise RuntimeError(f"Server error (HTTP {response.status_code}): {response.text[:200]}")
            return response.json()
    except ImportError:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status >= 500:
                    text = await response.text()
                    raise RuntimeError(f"Server error (HTTP {response.status}): {text[:200]}")
                return await response.json()


# ── OpenAI ───────────────────────────────────────────────────────


class OpenAIChatModel:
    """ChatModel implementation for OpenAI-compatible APIs."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        temperature: float = 0.7,
        base_url: Optional[str] = None,
        max_tokens: int = 4096,
    ):
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self._max_tokens = max_tokens

    @property
    def provider(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[ToolCallRequest]] = None,
        tool_choice: Optional[str] = None,
    ) -> ChatResponse:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature or self._temperature,
            "max_tokens": max_tokens or self._max_tokens,
        }

        if tools:
            payload["tools"] = _tool_requests_to_openai(tools)
            payload["tool_choice"] = tool_choice or "auto"

        result = await _http_post(url, headers, payload)

        if "error" in result:
            raise RuntimeError(f"OpenAI API error: {result['error'].get('message', result['error'])}")

        choices = result.get("choices")
        if not choices:
            raise RuntimeError(f"OpenAI API returned empty choices: {json.dumps(result)[:300]}")
        choice = choices[0]
        message = choice.get("message", {})
        tokens = result.get("usage", {}).get("total_tokens", 0)

        tool_calls = []
        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                tool_calls.append(
                    ToolCall(
                        id=tc["id"],
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"],  # keep as JSON string
                    )
                )

        return ChatResponse(
            content=message.get("content", "") or "",
            model=self._model,
            tokens_used=tokens,
            finish_reason=choice.get("finish_reason", "stop"),
            tool_calls=tool_calls,
        )


# ── Anthropic ────────────────────────────────────────────────────


class AnthropicChatModel:
    """ChatModel implementation for Anthropic API."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    @property
    def provider(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[ToolCallRequest]] = None,
        tool_choice: Optional[str] = None,
    ) -> ChatResponse:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        system, anthropic_messages = _messages_to_anthropic(messages)

        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens or self._max_tokens,
            "temperature": temperature or self._temperature,
        }

        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = _tool_requests_to_anthropic(tools)

        result = await _http_post(url, headers, payload)

        if "error" in result:
            raise RuntimeError(f"Anthropic API error: {result['error'].get('message', result['error'])}")

        tool_calls = []
        text_content = ""

        for block in result.get("content", []):
            if block["type"] == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block["id"],
                        name=block["name"],
                        arguments=json.dumps(block["input"], ensure_ascii=False),
                    )
                )
            elif block["type"] == "text":
                text_content += block["text"]

        usage = result.get("usage", {})
        tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

        return ChatResponse(
            content=text_content,
            model=self._model,
            tokens_used=tokens,
            finish_reason=result.get("stop_reason", "end_turn"),
            tool_calls=tool_calls,
        )


# ── Factory ──────────────────────────────────────────────────────


def create_chat_model(
    provider: str,
    api_key: str,
    model: str,
    temperature: float = 0.7,
    base_url: Optional[str] = None,
    max_tokens: int = 4096,
) -> "OpenAIChatModel | AnthropicChatModel":
    """Create a ChatModel from provider config.

    Routing:
    - 'anthropic' → AnthropicChatModel (different API format)
    - Everything else → OpenAIChatModel (openai, groq, deepseek, ollama, google, custom, azure)
      These all use OpenAI-compatible /chat/completions endpoint via base_url.
    """
    if provider == "anthropic":
        return AnthropicChatModel(
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    # OpenAI-compatible (covers openai, groq, deepseek, ollama, google, custom, etc.)
    return OpenAIChatModel(
        api_key=api_key,
        model=model,
        temperature=temperature,
        base_url=base_url,
        max_tokens=max_tokens,
    )
