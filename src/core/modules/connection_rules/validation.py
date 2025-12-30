"""
Connection Rules Validation

Functions for validating module connections.
"""

from typing import Any, Dict, List, Optional, Tuple

from ..types import get_context_error_message, is_context_compatible
from .models import ConnectionRule
from .rules import CONNECTION_RULES, SPECIAL_NODES


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

    Performs three levels of validation:
    1. Special node rules
    2. Category-based connection rules (can_connect_to / can_receive_from)
    3. Context compatibility (does source provide what target requires?)

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

    # ==========================================================================
    # Check 1: Context Compatibility (most important for preventing bad UX)
    # ==========================================================================
    if not is_context_compatible(source_category, target_category):
        error_message = get_context_error_message(source_category, target_category)
        return False, error_message

    # ==========================================================================
    # Check 2: Category-based connection rules
    # ==========================================================================
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
    source_module = source_node.get(
        "module_id",
        source_node.get("data", {}).get("module_id", "unknown")
    )
    target_module = target_node.get(
        "module_id",
        target_node.get("data", {}).get("module_id", "unknown")
    )

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
                "error": f"Invalid edge: missing node "
                         f"{source_id if not source_node else target_id}",
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
