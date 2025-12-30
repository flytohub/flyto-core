"""
LLM Interaction Modules
AI model interaction for code generation, analysis, and autonomous operations
"""

from .chat import llm_chat
from .code_fix import llm_code_fix

__all__ = ['llm_chat', 'llm_code_fix']
