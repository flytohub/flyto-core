"""
AI Agent Modules

DEPRECATED: This file is maintained for backwards compatibility.
Please import from core.modules.third_party.ai.agents instead:

    from core.modules.third_party.ai.agents import (
        AutonomousAgentModule,
        ChainAgentModule,
    )

All functionality has been split into:
- core/modules/third_party/ai/agents/llm_client.py - LLM calling mixin
- core/modules/third_party/ai/agents/autonomous.py - Autonomous agent
- core/modules/third_party/ai/agents/chain.py - Chain agent
"""

# Re-export for backwards compatibility
from .agents import (
    LLMClientMixin,
    AutonomousAgentModule,
    ChainAgentModule,
)

__all__ = [
    "LLMClientMixin",
    "AutonomousAgentModule",
    "ChainAgentModule",
]
