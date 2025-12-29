"""
Flow Control Module Detection and Constants

Provides utilities for identifying and handling flow control modules
(branch, switch, goto, loop, foreach) in workflows.

This module should be the single source of truth for flow control
module identification, avoiding hardcoded module IDs in multiple places.
"""
from typing import Set, FrozenSet


# =============================================================================
# Flow Control Module IDs
# =============================================================================

# Primary flow control module identifiers
FLOW_CONTROL_MODULES: FrozenSet[str] = frozenset([
    # Modern namespaced IDs
    'flow.branch',
    'flow.switch',
    'flow.goto',
    'flow.loop',
    'flow.foreach',
    'flow.fork',
    'flow.merge',
    'flow.container',
    'flow.breakpoint',

    # Core namespaced IDs
    'core.flow.branch',
    'core.flow.switch',
    'core.flow.goto',
    'core.flow.loop',
    'core.flow.foreach',
    'core.flow.fork',
    'core.flow.merge',
    'core.flow.container',
    'core.flow.breakpoint',

    # Legacy short names (backward compatibility)
    'loop',
    'foreach',
    'branch',
    'switch',
    'goto',
])

# Modules that can change execution flow (jump to different step)
FLOW_JUMPING_MODULES: FrozenSet[str] = frozenset([
    'flow.branch',
    'flow.switch',
    'flow.goto',
    'core.flow.branch',
    'core.flow.switch',
    'core.flow.goto',
    'branch',
    'switch',
    'goto',
])

# Modules that iterate (execute child steps multiple times)
FLOW_ITERATION_MODULES: FrozenSet[str] = frozenset([
    'flow.loop',
    'flow.foreach',
    'core.flow.loop',
    'core.flow.foreach',
    'loop',
    'foreach',
])

# Modules that create parallel execution paths
FLOW_PARALLEL_MODULES: FrozenSet[str] = frozenset([
    'flow.fork',
    'flow.merge',
    'core.flow.fork',
    'core.flow.merge',
])


# =============================================================================
# Helper Functions
# =============================================================================

def is_flow_control_module(module_id: str) -> bool:
    """
    Check if a module ID represents a flow control module.

    Args:
        module_id: The module identifier to check

    Returns:
        True if the module is a flow control module
    """
    return module_id in FLOW_CONTROL_MODULES


def is_flow_jumping_module(module_id: str) -> bool:
    """
    Check if a module can jump to a different step.

    Args:
        module_id: The module identifier to check

    Returns:
        True if the module can change execution flow
    """
    return module_id in FLOW_JUMPING_MODULES


def is_iteration_module(module_id: str) -> bool:
    """
    Check if a module performs iteration.

    Args:
        module_id: The module identifier to check

    Returns:
        True if the module iterates over items
    """
    return module_id in FLOW_ITERATION_MODULES


def is_parallel_module(module_id: str) -> bool:
    """
    Check if a module creates parallel execution paths.

    Args:
        module_id: The module identifier to check

    Returns:
        True if the module handles parallel execution
    """
    return module_id in FLOW_PARALLEL_MODULES


def normalize_module_id(module_id: str) -> str:
    """
    Normalize a module ID to its canonical form.

    Handles legacy short names and different namespace patterns.

    Args:
        module_id: The module identifier to normalize

    Returns:
        Normalized module ID
    """
    # Map legacy names to modern namespaced versions
    legacy_map = {
        'loop': 'flow.loop',
        'foreach': 'flow.foreach',
        'branch': 'flow.branch',
        'switch': 'flow.switch',
        'goto': 'flow.goto',
    }

    if module_id in legacy_map:
        return legacy_map[module_id]

    # Strip 'core.' prefix if present for consistency
    if module_id.startswith('core.'):
        return module_id[5:]  # Remove 'core.' prefix

    return module_id


def get_flow_control_type(module_id: str) -> str:
    """
    Get the type of flow control for a module.

    Args:
        module_id: The module identifier

    Returns:
        One of: 'jumping', 'iteration', 'parallel', 'container', 'none'
    """
    normalized = normalize_module_id(module_id)

    if normalized in ('flow.branch', 'flow.switch', 'flow.goto'):
        return 'jumping'
    elif normalized in ('flow.loop', 'flow.foreach'):
        return 'iteration'
    elif normalized in ('flow.fork', 'flow.merge'):
        return 'parallel'
    elif normalized in ('flow.container', 'flow.breakpoint'):
        return 'container'
    else:
        return 'none'
