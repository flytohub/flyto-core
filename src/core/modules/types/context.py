"""
Context Compatibility

Context requirements, provisions, and compatibility checking.
"""

from typing import Dict, List

from .enums import ContextType


# Default context requirements by category
# Used when module does not explicitly declare requires_context
DEFAULT_CONTEXT_REQUIREMENTS: Dict[str, List[ContextType]] = {
    # Browser-related: require browser context
    "page": [ContextType.BROWSER],
    "scraper": [ContextType.BROWSER],
    "element": [ContextType.BROWSER, ContextType.PAGE],
    "browser_find": [ContextType.BROWSER, ContextType.PAGE],
    "browser_ops": [ContextType.BROWSER],

    # Analysis: requires data to analyze
    "analysis": [ContextType.DATA],

    # File processing: requires file context
    "document": [ContextType.FILE],
}


# Default context provisions by category
# Used when module does not explicitly declare provides_context
DEFAULT_CONTEXT_PROVISIONS: Dict[str, List[ContextType]] = {
    # Browser: provides browser context
    "browser": [ContextType.BROWSER, ContextType.PAGE],

    # File: provides file context
    "file": [ContextType.FILE],

    # API: provides response data
    "api": [ContextType.API_RESPONSE, ContextType.DATA],
    "http": [ContextType.API_RESPONSE, ContextType.DATA],

    # Data: provides generic data context
    "data": [ContextType.DATA],
    "array": [ContextType.DATA],
    "object": [ContextType.DATA],
    "string": [ContextType.DATA],

    # AI: provides text data (NOT browser context!)
    "ai": [ContextType.DATA],

    # Database: provides data
    "database": [ContextType.DATA, ContextType.DATABASE],

    # Analysis: provides data insights
    "analysis": [ContextType.DATA],

    # Flow: passes through context (neutral)
    "flow": [],
}


# Context Incompatibility Rules
# Modules from SOURCE category CANNOT directly connect to TARGET categories
CONTEXT_INCOMPATIBLE_PAIRS: Dict[str, List[str]] = {
    # AI/Agent modules don't provide browser context
    "ai": ["browser", "browser_find", "browser_ops", "element", "page", "scraper"],
    "agent": ["browser", "browser_find", "browser_ops", "element", "page", "scraper"],

    # Data modules don't provide browser context
    "data": ["browser_find", "browser_ops", "element"],
    "array": ["browser_find", "browser_ops", "element"],
    "object": ["browser_find", "browser_ops", "element"],
    "string": ["browser_find", "browser_ops", "element"],

    # API modules don't provide browser context
    "api": ["browser_find", "browser_ops", "element"],
    "http": ["browser_find", "browser_ops", "element"],

    # Database doesn't provide browser context
    "database": ["browser_find", "browser_ops", "element"],
}


def is_context_compatible(source_category: str, target_category: str) -> bool:
    """
    Check if source category's output context is compatible with target category's input requirements.

    Args:
        source_category: Category of source module
        target_category: Category of target module

    Returns:
        True if connection is context-compatible
    """
    incompatible_targets = CONTEXT_INCOMPATIBLE_PAIRS.get(source_category, [])
    return target_category not in incompatible_targets


def get_context_error_message(source_category: str, target_category: str) -> str:
    """
    Get human-readable error message for context incompatibility.

    Args:
        source_category: Category of source module
        target_category: Category of target module

    Returns:
        Error message string
    """
    # Get what source provides
    source_provides = DEFAULT_CONTEXT_PROVISIONS.get(source_category, [])
    source_provides_str = ", ".join([c.value for c in source_provides]) if source_provides else "generic data"

    # Get what target requires
    target_requires = DEFAULT_CONTEXT_REQUIREMENTS.get(target_category, [])
    target_requires_str = ", ".join([c.value for c in target_requires]) if target_requires else "none"

    if target_category in ["browser", "browser_find", "browser_ops", "element", "page", "scraper"]:
        return f"This module requires browser context, but the source module only provides {source_provides_str}. Add a browser.open module first to establish browser context."

    return f"Context mismatch: source provides {source_provides_str}, but target requires {target_requires_str}"
