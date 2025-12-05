"""
Module System - Core Registration and Execution

Organized by architecture:
- Atomic: Core building blocks, no external dependencies (Level 1)
- Third-party: External service integrations (Level 2)
- AI Tools: AI-powered analysis tools (Level 3)
- External: MCP and remote agents (Level 4)
- Composite: High-level workflow templates (v1.1)
"""

from .registry import ModuleRegistry
from .base import BaseModule
from .types import ModuleLevel, LEVEL_PRIORITY

# Import atomic modules
from .atomic import browser_ops
from .atomic import data
from .atomic import utility

# Import legacy atomic modules (to be migrated)
from . import atomic

# Import third-party integration modules
from .third_party import ai
from .third_party import communication
from .third_party import database
from .third_party import cloud
from .third_party import productivity
from .third_party import developer

# Composite modules (coming in v1.1)
from . import composite

__all__ = [
    'ModuleRegistry',
    'BaseModule',
    'ModuleLevel',
    'LEVEL_PRIORITY',
    # Atomic
    'browser_ops',
    'data',
    'utility',
    # Third-party
    'ai',
    'communication',
    'database',
    'cloud',
    'productivity',
    'developer',
    # Composite
    'composite',
]
