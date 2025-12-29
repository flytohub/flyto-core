"""
Connection Rules - Module Connection Validation

Defines rules for which modules can connect to which other modules.
This prevents illogical connections like browser.click -> database.query
without an intermediate data transformation.

Design Philosophy:
- Flow control modules (flow.*) are universal connectors
- Data transformation modules (data.*, array.*, etc.) are universal
- Domain-specific modules (browser.*, database.*) have restricted connections
- Start/End nodes have special rules

Usage:
    from core.modules.connection_rules import (
        can_connect,
        get_connection_rules,
        validate_workflow_connections,
    )

    # Check if source can connect to target
    if can_connect('browser.click', 'browser.type'):
        # Valid connection
        pass

    # Validate entire workflow
    errors = validate_workflow_connections(workflow)
"""

from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import fnmatch
import logging

logger = logging.getLogger(__name__)


class ConnectionCategory(str, Enum):
    """Categories for connection rule grouping"""
    BROWSER = "browser"
    FLOW = "flow"
    DATA = "data"
    FILE = "file"
    DATABASE = "database"
    API = "api"
    AI = "ai"
    DOCUMENT = "document"
    NOTIFICATION = "notification"
    ANALYSIS = "analysis"
    UTILITY = "utility"
    ANY = "*"


@dataclass
class ConnectionRule:
    """
    Connection rule for a category of modules.

    Attributes:
        category: Module category (e.g., "browser")
        can_connect_to: List of patterns for allowed targets
        can_receive_from: List of patterns for allowed sources
        description: Human-readable rule description
    """
    category: str
    can_connect_to: List[str]
    can_receive_from: List[str]
    description: str = ""


# =============================================================================
# Connection Rules Definition
# =============================================================================

# Default rules by category
# Pattern format: "category.*" or "category.specific" or "*" for any

CONNECTION_RULES: Dict[str, ConnectionRule] = {
    # -------------------------------------------------------------------------
    # Browser Automation - Must stay in browser context chain
    # -------------------------------------------------------------------------
    "browser": ConnectionRule(
        category="browser",
        can_connect_to=[
            "browser.*",    # Other browser actions
            "flow.*",       # Flow control (if, loop, etc.)
            "data.*",       # Data extraction/transformation
            "file.*",       # Save screenshots, downloads
            "analysis.*",   # Analyze page content
            "ai.*",         # AI analysis of page
        ],
        can_receive_from=[
            "browser.*",    # Chain browser actions
            "flow.*",       # Start from flow control
            "start",        # Can be first node
        ],
        description="Browser modules chain with other browser actions or data processing"
    ),

    # -------------------------------------------------------------------------
    # Flow Control - Universal connectors
    # -------------------------------------------------------------------------
    "flow": ConnectionRule(
        category="flow",
        can_connect_to=["*"],      # Can connect to anything
        can_receive_from=["*"],    # Can receive from anything
        description="Flow control modules are universal connectors"
    ),

    # -------------------------------------------------------------------------
    # Data Transformation - Universal
    # -------------------------------------------------------------------------
    "data": ConnectionRule(
        category="data",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Data transformation modules work with any data source"
    ),

    "array": ConnectionRule(
        category="array",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Array operations work with any data"
    ),

    "object": ConnectionRule(
        category="object",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Object operations work with any data"
    ),

    "string": ConnectionRule(
        category="string",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="String operations work with any data"
    ),

    "math": ConnectionRule(
        category="math",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Math operations work with numeric data"
    ),

    "datetime": ConnectionRule(
        category="datetime",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="DateTime operations work with any data"
    ),

    # -------------------------------------------------------------------------
    # File System
    # -------------------------------------------------------------------------
    "file": ConnectionRule(
        category="file",
        can_connect_to=[
            "file.*",       # Chain file operations
            "flow.*",       # Flow control
            "data.*",       # Process file content
            "document.*",   # Document processing
            "analysis.*",   # Analyze content
        ],
        can_receive_from=["*"],  # Any module can trigger file ops
        description="File operations can be triggered by any module"
    ),

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    "database": ConnectionRule(
        category="database",
        can_connect_to=[
            "database.*",   # Chain queries
            "flow.*",       # Flow control
            "data.*",       # Transform results
            "file.*",       # Export to file
            "api.*",        # Send to API
        ],
        can_receive_from=["*"],
        description="Database modules process and output structured data"
    ),

    # -------------------------------------------------------------------------
    # API / HTTP
    # -------------------------------------------------------------------------
    "api": ConnectionRule(
        category="api",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="API modules are universal data exchangers"
    ),

    "http": ConnectionRule(
        category="http",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="HTTP modules are universal data exchangers"
    ),

    # -------------------------------------------------------------------------
    # AI / Analysis
    # -------------------------------------------------------------------------
    "ai": ConnectionRule(
        category="ai",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="AI modules can process any data"
    ),

    "analysis": ConnectionRule(
        category="analysis",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Analysis modules work with any data"
    ),

    # -------------------------------------------------------------------------
    # Document Processing
    # -------------------------------------------------------------------------
    "document": ConnectionRule(
        category="document",
        can_connect_to=[
            "document.*",
            "flow.*",
            "data.*",
            "file.*",
            "ai.*",
        ],
        can_receive_from=[
            "file.*",
            "flow.*",
            "browser.*",    # Download from browser
            "api.*",        # Receive from API
            "start",
        ],
        description="Document modules process files and output data"
    ),

    # -------------------------------------------------------------------------
    # Notification / Output
    # -------------------------------------------------------------------------
    "notification": ConnectionRule(
        category="notification",
        can_connect_to=[
            "flow.*",       # Continue after notification
            "end",          # End workflow
        ],
        can_receive_from=["*"],  # Any module can trigger notification
        description="Notification modules are typically endpoints"
    ),

    # -------------------------------------------------------------------------
    # Utility / Meta
    # -------------------------------------------------------------------------
    "utility": ConnectionRule(
        category="utility",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Utility modules are universal"
    ),

    "meta": ConnectionRule(
        category="meta",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Meta modules are universal"
    ),

    # -------------------------------------------------------------------------
    # Composite modules follow their internal category
    # -------------------------------------------------------------------------
    "composite": ConnectionRule(
        category="composite",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Composite modules depend on their internal implementation"
    ),
}

# Special nodes
SPECIAL_NODES = {"start", "end", "trigger"}


# =============================================================================
# Validation Functions
# =============================================================================

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


def can_connect(
    source_module_id: str,
    target_module_id: str,
    source_rules: Optional[ConnectionRule] = None,
    target_rules: Optional[ConnectionRule] = None,
) -> Tuple[bool, str]:
    """
    Check if source module can connect to target module.

    Args:
        source_module_id: Source module ID
        target_module_id: Target module ID
        source_rules: Optional pre-fetched rules for source
        target_rules: Optional pre-fetched rules for target

    Returns:
        Tuple of (is_valid, reason)
    """
    # Special nodes always valid
    if source_module_id in SPECIAL_NODES or target_module_id in SPECIAL_NODES:
        return True, "Special node connection"

    # Get categories
    source_category = get_module_category(source_module_id)
    target_category = get_module_category(target_module_id)

    # Get rules
    if source_rules is None:
        source_rules = get_connection_rules(source_category)
    if target_rules is None:
        target_rules = get_connection_rules(target_category)

    # Check source's can_connect_to
    source_can_connect = False
    for pattern in source_rules.can_connect_to:
        if matches_pattern(target_module_id, pattern):
            source_can_connect = True
            break

    if not source_can_connect:
        return False, f"{source_module_id} cannot connect to {target_category} modules"

    # Check target's can_receive_from
    target_can_receive = False
    for pattern in target_rules.can_receive_from:
        if matches_pattern(source_module_id, pattern):
            target_can_receive = True
            break

    if not target_can_receive:
        return False, f"{target_module_id} cannot receive from {source_category} modules"

    return True, "Valid connection"


def validate_edge(
    source_node: Dict[str, Any],
    target_node: Dict[str, Any],
    edge: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Validate a single edge connection.

    Args:
        source_node: Source node data
        target_node: Target node data
        edge: Edge data

    Returns:
        Tuple of (is_valid, error_message)
    """
    source_module = source_node.get("module_id", source_node.get("data", {}).get("module_id", "unknown"))
    target_module = target_node.get("module_id", target_node.get("data", {}).get("module_id", "unknown"))

    # Check module-level rules first
    is_valid, reason = can_connect(source_module, target_module)

    if not is_valid:
        return False, reason

    # Check custom rules from module metadata
    source_custom_rules = source_node.get("data", {}).get("can_connect_to", [])
    target_custom_rules = target_node.get("data", {}).get("can_receive_from", [])

    # If custom rules are defined, they take precedence
    if source_custom_rules:
        custom_valid = False
        for pattern in source_custom_rules:
            if matches_pattern(target_module, pattern):
                custom_valid = True
                break
        if not custom_valid:
            return False, f"Custom rule: {source_module} cannot connect to {target_module}"

    if target_custom_rules:
        custom_valid = False
        for pattern in target_custom_rules:
            if matches_pattern(source_module, pattern):
                custom_valid = True
                break
        if not custom_valid:
            return False, f"Custom rule: {target_module} cannot receive from {source_module}"

    return True, None


def validate_workflow_connections(
    workflow: Dict[str, Any],
    strict: bool = False,
) -> List[Dict[str, Any]]:
    """
    Validate all connections in a workflow.

    Args:
        workflow: Workflow definition with nodes and edges
        strict: If True, return errors; if False, return warnings

    Returns:
        List of validation issues: [{"edge_id": str, "error": str, "severity": str}]
    """
    issues = []
    nodes = {n.get("id"): n for n in workflow.get("nodes", [])}
    edges = workflow.get("edges", [])

    for edge in edges:
        source_id = edge.get("source")
        target_id = edge.get("target")

        source_node = nodes.get(source_id)
        target_node = nodes.get(target_id)

        if not source_node or not target_node:
            issues.append({
                "edge_id": edge.get("id"),
                "error": f"Invalid edge: missing node {source_id if not source_node else target_id}",
                "severity": "error",
            })
            continue

        is_valid, error = validate_edge(source_node, target_node, edge)

        if not is_valid:
            issues.append({
                "edge_id": edge.get("id"),
                "source": source_id,
                "target": target_id,
                "error": error,
                "severity": "error" if strict else "warning",
            })

    return issues


# =============================================================================
# Rule Management
# =============================================================================

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


# =============================================================================
# Export for use in registry decorators
# =============================================================================

def get_default_connection_rules(category: str) -> Tuple[List[str], List[str]]:
    """
    Get default can_connect_to and can_receive_from for a category.

    Used by @register_module and @register_composite when rules not specified.

    Returns:
        Tuple of (can_connect_to, can_receive_from)
    """
    rules = get_connection_rules(category)
    return rules.can_connect_to, rules.can_receive_from
