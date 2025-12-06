"""
Module Types

Defines core types for module system including:
- ModuleLevel: Priority and trust classification
- UIVisibility: UI display behavior
- ContextType: Module context requirements
"""
from enum import Enum
from typing import List, Optional


class ModuleLevel(str, Enum):
    """
    Module level - determines priority and trust level.

    ATOMIC: Level 2 - Core atomic modules (building blocks, expert mode)
    COMPOSITE: Level 3 - Composite modules (normal user visible)
    TEMPLATE: Level 1 - Workflow templates (one-click solutions)
    PATTERN: Level 4 - Advanced patterns (system internal)
    THIRD_PARTY: Third-party API integrations
    AI_TOOL: AI tools for analysis
    EXTERNAL: External services (MCP, remote agents)
    """
    ATOMIC = "atomic"
    COMPOSITE = "composite"
    TEMPLATE = "template"
    PATTERN = "pattern"
    THIRD_PARTY = "third_party"
    AI_TOOL = "ai_tool"
    EXTERNAL = "external"


class UIVisibility(str, Enum):
    """
    UI visibility level for modules.

    DEFAULT: Show in normal mode (templates, composites)
    EXPERT: Show only in expert collapsed section (atomic modules)
    HIDDEN: Never show in UI (internal system modules)
    """
    DEFAULT = "default"
    EXPERT = "expert"
    HIDDEN = "hidden"


class ContextType(str, Enum):
    """
    Context types that modules can require or provide.

    Used for connection validation between modules.
    """
    BROWSER = "browser"
    PAGE = "page"
    FILE = "file"
    DATA = "data"
    API_RESPONSE = "api_response"
    DATABASE = "database"
    SESSION = "session"


# Priority order for module selection (lower = higher priority)
LEVEL_PRIORITY = {
    ModuleLevel.ATOMIC: 1,
    ModuleLevel.COMPOSITE: 2,
    ModuleLevel.TEMPLATE: 3,
    ModuleLevel.PATTERN: 4,
    ModuleLevel.THIRD_PARTY: 5,
    ModuleLevel.AI_TOOL: 6,
    ModuleLevel.EXTERNAL: 7,
}


# Default context requirements by category
# Used when module does not explicitly declare requires_context
DEFAULT_CONTEXT_REQUIREMENTS = {
    "page": [ContextType.BROWSER],
    "scraper": [ContextType.BROWSER],
    "element": [ContextType.BROWSER],
}


# Default context provisions by category
# Used when module does not explicitly declare provides_context
DEFAULT_CONTEXT_PROVISIONS = {
    "browser": [ContextType.BROWSER],
    "file": [ContextType.FILE],
    "api": [ContextType.API_RESPONSE],
    "data": [ContextType.DATA],
}


# Default UI visibility by category (ADR-001)
# Categories listed here will default to DEFAULT (shown to normal users)
# Categories NOT listed will default to EXPERT (advanced users only)
#
# DEFAULT categories: Complete, user-facing features that work standalone
# EXPERT categories: Low-level operations requiring programming knowledge
DEFAULT_VISIBILITY_CATEGORIES = {
    # AI & Chat - Complete AI integrations
    "ai": UIVisibility.DEFAULT,
    "agent": UIVisibility.DEFAULT,

    # Communication & Notifications - Send messages to users
    "notification": UIVisibility.DEFAULT,
    "communication": UIVisibility.DEFAULT,

    # Cloud Storage - Upload/download files
    "cloud": UIVisibility.DEFAULT,

    # Database - Data operations
    "database": UIVisibility.DEFAULT,
    "db": UIVisibility.DEFAULT,

    # Productivity Tools - External service integrations
    "productivity": UIVisibility.DEFAULT,
    "payment": UIVisibility.DEFAULT,

    # API - HTTP requests and external APIs
    "api": UIVisibility.DEFAULT,

    # High-level browser operations (Launch, Screenshot, Extract)
    # Note: Low-level browser ops (click, type) stay EXPERT
    "browser": UIVisibility.DEFAULT,

    # Image processing - Complete operations
    "image": UIVisibility.DEFAULT,

    # --- EXPERT categories (low-level/programming) ---
    # These are explicitly set to EXPERT for clarity

    # String manipulation - programming primitives
    "string": UIVisibility.EXPERT,
    "text": UIVisibility.EXPERT,

    # Array/Object operations - programming primitives
    "array": UIVisibility.EXPERT,
    "object": UIVisibility.EXPERT,

    # Math operations - programming primitives
    "math": UIVisibility.EXPERT,

    # DateTime manipulation - often needs composition
    "datetime": UIVisibility.EXPERT,

    # File system - low-level ops
    "file": UIVisibility.EXPERT,

    # DOM/Element operations - requires browser knowledge
    "element": UIVisibility.EXPERT,

    # Flow control - programming constructs
    "flow": UIVisibility.EXPERT,

    # Data parsing - technical operations
    "data": UIVisibility.EXPERT,

    # Utility/Meta - system internals
    "utility": UIVisibility.EXPERT,
    "meta": UIVisibility.EXPERT,

    # Testing - developer tools
    "test": UIVisibility.EXPERT,
    "atomic": UIVisibility.EXPERT,
}


def get_default_visibility(category: str) -> UIVisibility:
    """
    Get default UI visibility for a category.

    Args:
        category: Module category name

    Returns:
        UIVisibility.DEFAULT for user-facing categories
        UIVisibility.EXPERT for low-level/programming categories
    """
    return DEFAULT_VISIBILITY_CATEGORIES.get(category, UIVisibility.EXPERT)
