# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
AI Sub-Modules

n8n-style sub-nodes for AI Agent:
- ai.model: LLM model configuration
- ai.memory: Conversation memory (buffer/window/summary)
- ai.memory.vector: Vector-based semantic memory
- ai.memory.entity: Entity extraction and tracking
- ai.memory.redis: Redis persistent memory
- ai.tool: Tool wrapper for AI Agent
- ai.vision.analyze: Image analysis via LLM vision
- ai.extract: Structured data extraction via LLM
- ai.embed: Text embedding generation
"""

from .model import ai_model
from .memory import ai_memory
from .memory_vector import ai_memory_vector
from .memory_entity import ai_memory_entity
from .memory_redis import ai_memory_redis
from .tool import ai_tool
from .vision_analyze import ai_vision_analyze
from .extract import ai_extract
from .embed import ai_embed

__all__ = [
    'ai_model',
    'ai_memory',
    'ai_memory_vector',
    'ai_memory_entity',
    'ai_memory_redis',
    'ai_tool',
    'ai_vision_analyze',
    'ai_extract',
    'ai_embed',
]
