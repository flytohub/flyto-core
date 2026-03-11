# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Connection Rules Package

Provides connection rule management for workflow modules.
Validation is handled by validation/connection.py (the single validation entry point).
"""

from .models import ConnectionCategory, ConnectionRule
from .rules import CONNECTION_RULES, SPECIAL_NODES
from .management import (
    add_connection_rule,
    get_acceptable_sources,
    get_all_rules,
    get_connection_rules,
    get_default_connection_rules,
    get_module_category,
    get_suggested_connections,
    matches_pattern,
)

__all__ = [
    # Models
    "ConnectionCategory",
    "ConnectionRule",
    # Rules
    "CONNECTION_RULES",
    "SPECIAL_NODES",
    # Management (includes helpers moved from deleted validation.py)
    "add_connection_rule",
    "get_acceptable_sources",
    "get_all_rules",
    "get_connection_rules",
    "get_default_connection_rules",
    "get_module_category",
    "get_suggested_connections",
    "matches_pattern",
]
