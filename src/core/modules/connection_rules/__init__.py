"""
Connection Rules Package

Provides connection validation and rule management for workflow modules.
"""

from .models import ConnectionCategory, ConnectionRule
from .rules import CONNECTION_RULES, SPECIAL_NODES
from .validation import (
    can_connect,
    get_connection_rules,
    get_module_category,
    matches_pattern,
    validate_edge,
    validate_workflow_connections,
)
from .management import (
    add_connection_rule,
    get_acceptable_sources,
    get_all_rules,
    get_default_connection_rules,
    get_suggested_connections,
)

__all__ = [
    # Models
    "ConnectionCategory",
    "ConnectionRule",
    # Rules
    "CONNECTION_RULES",
    "SPECIAL_NODES",
    # Validation
    "can_connect",
    "get_connection_rules",
    "get_module_category",
    "matches_pattern",
    "validate_edge",
    "validate_workflow_connections",
    # Management
    "add_connection_rule",
    "get_acceptable_sources",
    "get_all_rules",
    "get_default_connection_rules",
    "get_suggested_connections",
]
