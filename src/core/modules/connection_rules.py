"""
Connection Rules - Module Connection Validation

DEPRECATED: This file is maintained for backwards compatibility.
Please import from core.modules.connection_rules instead:

    from core.modules.connection_rules import (
        can_connect,
        get_connection_rules,
        validate_workflow_connections,
    )

All functionality has been split into:
- core/modules/connection_rules/models.py - ConnectionCategory, ConnectionRule
- core/modules/connection_rules/rules.py - CONNECTION_RULES, SPECIAL_NODES
- core/modules/connection_rules/validation.py - Validation functions
- core/modules/connection_rules/management.py - Rule management functions

Original design principles:
- Flow control modules (flow.*) are universal connectors
- Data transformation modules (data.*, array.*, etc.) are universal
- Domain-specific modules (browser.*, database.*) have restricted connections
- Start/End nodes have special rules
"""

# Re-export for backwards compatibility
from .connection_rules import (
    # Models
    ConnectionCategory,
    ConnectionRule,
    # Rules
    CONNECTION_RULES,
    SPECIAL_NODES,
    # Validation
    can_connect,
    get_connection_rules,
    get_module_category,
    matches_pattern,
    validate_edge,
    validate_workflow_connections,
    # Management
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
