"""
Module Types

Defines core types for module system.
"""
from enum import Enum


class ModuleLevel(str, Enum):
    """
    Module level - determines priority and trust level.

    ATOMIC: Level 1 - Our own atomic modules (most trusted, highest priority)
    THIRD_PARTY: Level 2 - Third-party APIs (requires API key)
    AI_TOOL: Level 3 - AI tools for analysis (Claude/GPT)
    EXTERNAL: Level 4 - External services (MCP, remote agents)
    """
    ATOMIC = "atomic"
    THIRD_PARTY = "third_party"
    AI_TOOL = "ai_tool"
    EXTERNAL = "external"


# Priority order for module selection (lower = higher priority)
LEVEL_PRIORITY = {
    ModuleLevel.ATOMIC: 1,
    ModuleLevel.THIRD_PARTY: 2,
    ModuleLevel.AI_TOOL: 3,
    ModuleLevel.EXTERNAL: 4,
}
