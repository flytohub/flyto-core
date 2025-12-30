"""
Connection Rules Management

Functions for managing and querying connection rules.
"""

import logging
from typing import Dict, List, Tuple

from .models import ConnectionRule
from .rules import CONNECTION_RULES, SPECIAL_NODES
from .validation import get_connection_rules, get_module_category

logger = logging.getLogger(__name__)


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
