"""
Context Layers

Security-isolated context management for workflow execution.

Usage:
    from core.engine.context import create_context, LayeredContext

    ctx = create_context(
        params={"key": "value"},
        user_id="user123",
        credentials={"OPENAI_API_KEY": "sk-..."},
    )
"""

from .layers import (
    # Constants
    ENV_ALLOWLIST,
    PRIVATE_PREFIX,
    SECRET_PATTERNS,
    # Exceptions
    ContextAccessError,
    SecretExposureError,
    # Classes
    ContextBuilder,
    LayeredContext,
    # Functions
    create_context,
    merge_node_output,
)

__all__ = [
    # Constants
    "ENV_ALLOWLIST",
    "PRIVATE_PREFIX",
    "SECRET_PATTERNS",
    # Exceptions
    "ContextAccessError",
    "SecretExposureError",
    # Classes
    "ContextBuilder",
    "LayeredContext",
    # Functions
    "create_context",
    "merge_node_output",
]
