# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Module Metadata Builder

Constructs the full metadata dictionary for module registration.
"""

from typing import Dict, Any, Optional, List

from ..types import (
    ModuleLevel,
    ModuleTier,
    UIVisibility,
    ExecutionEnvironment,
    NodeType,
    StabilityLevel,
)


def build_module_metadata(
    module_id: str,
    version: str,
    stability: StabilityLevel,
    level: ModuleLevel,
    resolved: Dict[str, Any],
    subcategory: Optional[str],
    tags: Optional[List[str]],
    ui_label: Optional[Any],
    ui_label_key: Optional[str],
    ui_description: Optional[Any],
    ui_description_key: Optional[str],
    ui_group: Optional[str],
    ui_icon: Optional[str],
    ui_color: Optional[str],
    ui_help: Optional[str],
    ui_help_key: Optional[str],
    label: Optional[Any],
    label_key: Optional[str],
    description: Optional[Any],
    description_key: Optional[str],
    icon: Optional[str],
    color: Optional[str],
    input_types: Optional[List[str]],
    output_types: Optional[List[str]],
    input_type_labels: Optional[Dict[str, str]],
    input_type_descriptions: Optional[Dict[str, str]],
    output_type_labels: Optional[Dict[str, str]],
    output_type_descriptions: Optional[Dict[str, str]],
    suggested_predecessors: Optional[List[str]],
    suggested_successors: Optional[List[str]],
    connection_error_messages: Optional[Dict[str, str]],
    params_schema: Optional[Dict[str, Any]],
    output_schema: Optional[Dict[str, Any]],
    retryable: bool,
    max_retries: int,
    concurrent_safe: bool,
    requires_credentials: bool,
    handles_sensitive_data: bool,
    required_permissions: Optional[List[str]],
    credential_keys: Optional[List[str]],
    required_secrets: Optional[List[str]],
    env_vars: Optional[List[str]],
    node_type: NodeType,
    dynamic_ports: Optional[Dict[str, Dict[str, Any]]],
    container_config: Optional[Dict[str, Any]],
    start_requires_params: Optional[List[str]],
    requires: Optional[List[str]],
    permissions: Optional[List[str]],
    examples: Optional[List[Dict[str, Any]]],
    docs_url: Optional[str],
    author: Optional[str],
    license_str: str,
    required_tier: Optional[str],
    required_feature: Optional[str],
) -> Dict[str, Any]:
    """Build the full metadata dict for a module registration."""
    resolved_visibility = resolved["visibility"]
    resolved_tier = resolved["tier"]
    resolved_execution_env = resolved["execution_env"]

    return {
        "module_id": module_id,
        "version": version,
        "stability": stability.value if isinstance(stability, StabilityLevel) else stability,
        "level": level.value if isinstance(level, ModuleLevel) else level,
        "category": resolved["category"],
        "subcategory": subcategory,
        "tags": tags or [],
        "tier": resolved_tier.value if isinstance(resolved_tier, ModuleTier) else resolved_tier,

        # Context for connection validation
        "requires_context": resolved["requires_context"],
        "provides_context": resolved["provides_context"],

        # UI metadata (prefer new ui_* fields, fallback to legacy)
        "ui_visibility": resolved_visibility.value if isinstance(resolved_visibility, UIVisibility) else resolved_visibility,
        "ui_label": ui_label or label or module_id,
        "ui_label_key": ui_label_key or label_key,
        "ui_description": ui_description or description or "",
        "ui_description_key": ui_description_key or description_key,
        "ui_group": ui_group,
        "ui_icon": ui_icon or icon,
        "ui_color": ui_color or color,

        # Extended UI help
        "ui_help": ui_help,
        "ui_help_key": ui_help_key,

        # Connection types
        "input_types": input_types or [],
        "output_types": output_types or [],
        "can_receive_from": resolved["can_receive_from"],
        "can_connect_to": resolved["can_connect_to"],

        # Type labels and descriptions (for UI display)
        "input_type_labels": input_type_labels or {},
        "input_type_descriptions": input_type_descriptions or {},
        "output_type_labels": output_type_labels or {},
        "output_type_descriptions": output_type_descriptions or {},

        # Connection suggestions
        "suggested_predecessors": suggested_predecessors or [],
        "suggested_successors": suggested_successors or [],

        # Connection error messages
        "connection_error_messages": connection_error_messages or {},

        # Schema
        "params_schema": params_schema or {},
        "output_schema": output_schema or {},

        # Execution settings
        "timeout_ms": resolved["timeout_ms"],
        "retryable": retryable,
        # If retryable=False, max_retries should be 0 (consistency fix)
        "max_retries": max_retries if retryable else 0,
        "concurrent_safe": concurrent_safe,

        # Security settings
        "requires_credentials": requires_credentials,
        "handles_sensitive_data": handles_sensitive_data,
        "required_permissions": required_permissions or [],
        "credential_keys": credential_keys or [],
        "required_secrets": required_secrets or [],
        "env_vars": env_vars or [],

        # Execution environment
        "execution_environment": resolved_execution_env.value if isinstance(resolved_execution_env, ExecutionEnvironment) else resolved_execution_env,

        # Workflow Spec v1.1 - Node & Port Configuration
        "node_type": node_type.value if isinstance(node_type, NodeType) else node_type,
        "input_ports": resolved["input_ports"],
        "output_ports": resolved["output_ports"],
        "dynamic_ports": dynamic_ports,
        "container_config": container_config,

        # Start node configuration
        "can_be_start": resolved["can_be_start"],
        "start_requires_params": start_requires_params or [],

        # Advanced
        "requires": requires or [],
        "permissions": permissions or [],
        "examples": examples or [],
        "docs_url": docs_url,
        "author": author,
        "license": license_str,

        # License tier requirement
        "required_tier": required_tier,
        "required_feature": required_feature,
    }
