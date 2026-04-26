# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
AI Agent Protocol Interfaces

Defines the contracts between AI Agent sub-nodes and the agent loop.
Sub-nodes return objects implementing these protocols instead of config dicts.

Design:
- ChatModel: wraps LLM provider, agent calls .chat()
- AgentTool: wraps module execution, agent calls .invoke()
- Uses Python Protocol (PEP 544) for structural typing — flyto-pro's
  ILLMService satisfies ChatModel without inheriting from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ── Data Classes ─────────────────────────────────────────────────


@dataclass
class ToolCallRequest:
    """Tool definition passed to the LLM for function calling."""

    name: str
    description: str = ""
    parameters: Dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )


@dataclass
class ToolCall:
    """A tool invocation returned by the LLM."""

    id: str
    name: str
    arguments: str  # JSON string — matches OpenAI format


@dataclass
class ChatResponse:
    """Standardized LLM chat response.

    Token accounting exposes BOTH the provider-reported split
    (input_tokens + output_tokens + cached_input_tokens) and the
    legacy `tokens_used` rollup. Callers that cost per-direction
    (output tokens are typically priced 2-3× higher than input)
    should read the split; older callers reading `tokens_used`
    keep working unchanged — the rollup is the sum.
    """

    content: str = ""
    model: str = ""
    tokens_used: int = 0          # sum = input + output (legacy / display)
    input_tokens: int = 0         # prompt / request tokens
    output_tokens: int = 0        # completion / response tokens
    cached_input_tokens: int = 0  # providers that expose prompt-cache reuse
    finish_reason: str = "stop"
    tool_calls: List[ToolCall] = field(default_factory=list)


# ── Protocols ────────────────────────────────────────────────────


@runtime_checkable
class ChatModel(Protocol):
    """
    Protocol for LLM chat models.

    Implementations:
    - OpenAIChatModel (flyto-core)
    - AnthropicChatModel (flyto-core)
    - OpenAILLMService (flyto-pro, structurally compatible)
    """

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[ToolCallRequest]] = None,
        tool_choice: Optional[str] = None,
    ) -> ChatResponse: ...

    @property
    def provider(self) -> str: ...

    @property
    def model_name(self) -> str: ...


@runtime_checkable
class AgentTool(Protocol):
    """
    Protocol for tools available to the AI Agent.

    Implementations:
    - ModuleAgentTool (wraps any flyto module as a tool)
    """

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    def to_tool_call_request(self) -> ToolCallRequest: ...

    async def invoke(
        self,
        arguments: Dict[str, Any],
        agent_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]: ...
