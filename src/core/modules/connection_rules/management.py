# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Connection Rules Management

Functions for managing and querying connection rules.
Includes helper functions for category extraction and rule lookup.
"""

import logging
from typing import Dict, List, Tuple

from .models import ConnectionRule
from .rules import CONNECTION_RULES, SPECIAL_NODES

logger = logging.getLogger(__name__)


def get_module_category(module_id: str) -> str:
    """
    Extract category from module ID.

    Examples:
        "browser.click" -> "browser"
        "core.browser.click" -> "browser"
        "flow.if" -> "flow"
        "composite.browser.scrape" -> "composite"
    """
    parts = module_id.split(".")

    # Handle namespaced IDs like "core.browser.click"
    if len(parts) >= 2:
        if parts[0] in ("core", "pro", "cloud"):
            return parts[1]
        return parts[0]

    return module_id


def get_connection_rules(category: str) -> ConnectionRule:
    """
    Get connection rules for a category.

    Falls back to universal rules if category not defined.
    """
    return CONNECTION_RULES.get(category, ConnectionRule(
        category=category,
        can_connect_to=["*"],
        can_receive_from=["*"],
        description=f"Default rules for {category}"
    ))


def matches_pattern(module_id: str, pattern: str) -> bool:
    """
    Check if a module ID matches a pattern.

    Patterns:
        "*" - matches anything
        "browser.*" - matches browser.click, browser.type, etc.
        "browser.click" - exact match
        "start", "end" - special node types
    """
    if pattern == "*":
        return True

    if pattern in SPECIAL_NODES:
        return module_id == pattern

    # Glob-style matching
    if pattern.endswith(".*"):
        category = pattern[:-2]
        return get_module_category(module_id) == category

    # Exact match
    return module_id == pattern


def add_connection_rule(category: str, rule: ConnectionRule) -> None:
    """Add or update a connection rule for a category"""
    CONNECTION_RULES[category] = rule
    logger.debug(f"Connection rule added/updated for category: {category}")


def get_all_rules() -> Dict[str, ConnectionRule]:
    """Get all defined connection rules"""
    return CONNECTION_RULES.copy()


def get_suggested_connections(module_id: str) -> List[str]:
    """
    Get list of categories that can be connected from this module.

    Useful for UI hints and autocomplete.
    """
    category = get_module_category(module_id)
    rules = get_connection_rules(category)

    suggestions = set()
    for pattern in rules.can_connect_to:
        if pattern == "*":
            return ["*"]  # Any category
        if pattern.endswith(".*"):
            suggestions.add(pattern[:-2])
        elif pattern not in SPECIAL_NODES:
            suggestions.add(get_module_category(pattern))

    return list(suggestions)


def get_acceptable_sources(module_id: str) -> List[str]:
    """
    Get list of categories that can connect TO this module.

    Useful for UI hints and autocomplete.
    """
    category = get_module_category(module_id)
    rules = get_connection_rules(category)

    sources = set()
    for pattern in rules.can_receive_from:
        if pattern == "*":
            return ["*"]  # Any category
        if pattern.endswith(".*"):
            sources.add(pattern[:-2])
        elif pattern not in SPECIAL_NODES:
            sources.add(get_module_category(pattern))

    return list(sources)


def get_default_connection_rules(category: str) -> Tuple[List[str], List[str]]:
    """
    Get default can_connect_to and can_receive_from for a category.

    Used by @register_module and @register_composite when rules not specified.

    Returns:
        Tuple of (can_connect_to, can_receive_from)
    """
    rules = get_connection_rules(category)
    return rules.can_connect_to, rules.can_receive_from
