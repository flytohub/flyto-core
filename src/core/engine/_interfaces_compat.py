# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Compatibility layer for using ChatModel in engine components.
Avoids circular imports between engine and modules.
"""

from typing import Any, Callable, Dict, List


def get_simple_chat(chat_model) -> Callable:
    """Get a simple async chat function from a ChatModel.

    Returns an async function that takes messages and returns content string.
    Works with any object satisfying the ChatModel protocol.
    """
    async def chat_fn(messages: List[Dict[str, Any]]) -> str:
        response = await chat_model.chat(messages)
        return response.content

    return chat_fn
