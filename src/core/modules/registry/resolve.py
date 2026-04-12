# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Module Configuration Resolution

Auto-detection and resolution of module configuration values.
Handles tier, visibility, context, ports, connection rules, timeout, and start-node logic.
"""

import logging
import warnings
from typing import Dict, Any, Optional, List

from ..types import (
    ModuleLevel,
    ModuleTier,
    UIVisibility,
    ExecutionEnvironment,
    NodeType,
    DEFAULT_CONTEXT_REQUIREMENTS,
    DEFAULT_CONTEXT_PROVISIONS,
    get_default_visibility,
    get_module_environment,
    get_default_ports,
)
from ..connection_rules import get_default_connection_rules

logger = logging.getLogger(__name__)


def resolve_tier(
    tier: Optional[ModuleTier],
    level: ModuleLevel,
    tags: Optional[List[str]],
    category: str,
    subcategory: Optional[str] = None,
    module_id: Optional[str] = None,
) -> ModuleTier:
    """
    Resolve module tier based on explicit value or auto-detection.

    Priority:
    1. Explicit tier parameter (if provided)
    2. INTERNAL for system/internal categories
    3. TOOLKIT for low-level utility categories (string, array, object, math, etc.)
       - Checks category, subcategory, and module_id prefix
    4. TOOLKIT for 'advanced' tag
    5. FEATURED for template level
    6. STANDARD for user-facing categories (browser, api, ai, etc.)
    """
    if tier is not None:
        return tier

    # Internal categories are always INTERNAL
    internal_categories = {'meta', 'testing', 'debug', 'training'}
    if category in internal_categories:
        return ModuleTier.INTERNAL

    # Low-level utility categories -> TOOLKIT (collapsed by default)
    toolkit_categories = {
        # Data manipulation
        'string', 'array', 'object', 'math', 'datetime',
        # Type operations
        'validate', 'encode', 'convert', 'check', 'logic',
        # Text processing
        'text', 'regex', 'format', 'hash',
        # Collections
        'set', 'stats',
        # Low-level utilities
        'utility', 'random', 'crypto', 'path',
        # Development/testing tools
        'shell', 'process', 'port',
        # Vector/embedding utilities
        'vector',
    }

    if category in toolkit_categories:
        return ModuleTier.TOOLKIT

    if subcategory and subcategory in toolkit_categories:
        return ModuleTier.TOOLKIT

    if module_id:
        id_prefix = module_id.split('.')[0]
        if id_prefix in toolkit_categories:
            return ModuleTier.TOOLKIT

    if tags and 'advanced' in tags:
        return ModuleTier.TOOLKIT

    if level == ModuleLevel.TEMPLATE:
        return ModuleTier.FEATURED

    return ModuleTier.STANDARD


def enrich_port_handle_metadata(port: dict, port_type: str, node_type: NodeType) -> dict:
    """Auto-fill handle_id and position if not explicitly set."""
    if 'handle_id' in port:
        return port

    enriched = dict(port)
    pid = port['id']

    if port_type == 'input':
        enriched.setdefault('position', 'left')
        if pid == 'input':
            enriched['handle_id'] = 'in' if node_type == NodeType.LOOP else 'target'
        else:
            enriched['handle_id'] = 'target-%s' % pid
    else:  # output
        enriched.setdefault('position', 'right')
        if pid in ('success', 'trigger', 'start', 'output'):
            enriched['handle_id'] = 'output'
        elif pid == 'iterate':
            enriched['handle_id'] = 'body_out'
        elif pid == 'done':
            enriched['handle_id'] = 'done_out'
        else:
            enriched['handle_id'] = 'source-%s' % pid

    return enriched


def resolve_can_be_start(
    can_be_start: Optional[bool],
    node_type: NodeType,
    input_types: Optional[List[str]],
    requires_context: List[str],
    can_receive_from: Optional[List[str]],
) -> bool:
    """Resolve whether a module can be used as a workflow start node."""
    if can_be_start is not None:
        return can_be_start

    if node_type in (NodeType.START, NodeType.TRIGGER):
        return True
    if node_type in (NodeType.SWITCH, NodeType.MERGE, NodeType.LOOP, NodeType.JOIN, NodeType.END, NodeType.BRANCH, NodeType.FORK):
        return False
    if input_types and input_types != ['*']:
        return False
    if requires_context:
        return False
    if can_receive_from:
        return any(
            pattern == 'start' or pattern.startswith('start.')
            for pattern in can_receive_from
        )
    return True


def resolve_timeout_ms(
    timeout_ms: Optional[int],
    timeout: Optional[int],
    module_id: str,
) -> Optional[int]:
    """
    Resolve timeout_ms, handling deprecated timeout (seconds) parameter.

    Semantics:
    - None: no timeout configured (inherits from engine defaults)
    - 0: explicitly no timeout (wait indefinitely)
    - >0: timeout in milliseconds
    - <0: rejected (ValueError)
    """
    if timeout_ms is not None:
        if timeout_ms < 0:
            raise ValueError(
                f"[{module_id}] timeout_ms must be non-negative, got {timeout_ms}. "
                f"Use 0 for no timeout, or None to inherit engine defaults."
            )
        # 0 means "no timeout" — normalize to None for downstream consumers
        return None if timeout_ms == 0 else timeout_ms
    if timeout is None:
        return None
    if timeout < 0:
        raise ValueError(
            f"[{module_id}] timeout must be non-negative, got {timeout}. "
            f"Use 0 for no timeout, or None to inherit engine defaults."
        )
    if timeout == 0:
        return None

    resolved = timeout * 1000
    warnings.warn(
        f"[{module_id}] 'timeout' (seconds) is deprecated. "
        f"Use 'timeout_ms={resolved}' instead.",
        DeprecationWarning,
        stacklevel=5
    )
    logger.warning(
        f"[{module_id}] 'timeout' is deprecated. "
        f"Use 'timeout_ms={resolved}' instead."
    )
    return resolved


def resolve_module_config(
    module_id: str,
    level: ModuleLevel,
    category: Optional[str],
    subcategory: Optional[str],
    tags: Optional[List[str]],
    ui_visibility: Optional[UIVisibility],
    requires_context: Optional[List[str]],
    provides_context: Optional[List[str]],
    execution_environment: Optional[ExecutionEnvironment],
    node_type: NodeType,
    input_ports: Optional[List[Dict[str, Any]]],
    output_ports: Optional[List[Dict[str, Any]]],
    input_types: Optional[List[str]],
    can_receive_from: Optional[List[str]],
    can_connect_to: Optional[List[str]],
    can_be_start: Optional[bool],
    tier: Optional[ModuleTier],
    timeout_ms: Optional[int],
    timeout: Optional[int],
) -> Dict[str, Any]:
    """
    Resolve all auto-detected / defaulted config values for a module registration.

    Returns a dict with keys: category, visibility, requires_context, provides_context,
    execution_env, input_ports, output_ports, can_receive_from, can_connect_to,
    can_be_start, tier, timeout_ms.
    """
    resolved_category = category or module_id.split('.')[0]

    resolved_visibility = ui_visibility
    if resolved_visibility is None:
        resolved_visibility = get_default_visibility(resolved_category)

    resolved_requires_context = requires_context
    resolved_provides_context = provides_context

    if resolved_requires_context is None:
        resolved_requires_context = DEFAULT_CONTEXT_REQUIREMENTS.get(resolved_category, [])

    if resolved_provides_context is None:
        resolved_provides_context = DEFAULT_CONTEXT_PROVISIONS.get(resolved_category, [])

    resolved_execution_env = execution_environment
    if resolved_execution_env is None:
        resolved_execution_env = get_module_environment(module_id, resolved_category)

    default_ports = get_default_ports(node_type)
    resolved_input_ports = input_ports if input_ports is not None else default_ports.get("input", [])
    resolved_output_ports = output_ports if output_ports is not None else default_ports.get("output", [])

    resolved_input_ports = [
        enrich_port_handle_metadata(p, 'input', node_type) for p in resolved_input_ports
    ]
    resolved_output_ports = [
        enrich_port_handle_metadata(p, 'output', node_type) for p in resolved_output_ports
    ]

    default_can_connect, default_can_receive = get_default_connection_rules(resolved_category)
    resolved_can_connect_to = can_connect_to if can_connect_to is not None else default_can_connect
    resolved_can_receive_from = can_receive_from if can_receive_from is not None else default_can_receive

    resolved_can_be_start = resolve_can_be_start(
        can_be_start=can_be_start,
        node_type=node_type,
        input_types=input_types,
        requires_context=resolved_requires_context,
        can_receive_from=resolved_can_receive_from,
    )

    resolved_tier = resolve_tier(
        tier=tier,
        level=level,
        tags=tags,
        category=resolved_category,
        subcategory=subcategory,
        module_id=module_id,
    )

    resolved_timeout_ms = resolve_timeout_ms(timeout_ms, timeout, module_id)

    return {
        "category": resolved_category,
        "visibility": resolved_visibility,
        "requires_context": resolved_requires_context,
        "provides_context": resolved_provides_context,
        "execution_env": resolved_execution_env,
        "input_ports": resolved_input_ports,
        "output_ports": resolved_output_ports,
        "can_receive_from": resolved_can_receive_from,
        "can_connect_to": resolved_can_connect_to,
        "can_be_start": resolved_can_be_start,
        "tier": resolved_tier,
        "timeout_ms": resolved_timeout_ms,
    }
