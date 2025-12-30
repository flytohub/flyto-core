"""
UI Visibility Configuration

Default visibility settings by category.
"""

from typing import Dict

from .enums import UIVisibility


# Default UI visibility by category (ADR-001)
# DEFAULT categories: Complete, user-facing features that work standalone
# EXPERT categories: Low-level operations requiring programming knowledge
DEFAULT_VISIBILITY_CATEGORIES: Dict[str, UIVisibility] = {
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
    "browser": UIVisibility.DEFAULT,

    # Image processing - Complete operations
    "image": UIVisibility.DEFAULT,

    # --- EXPERT categories (low-level/programming) ---

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
