# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

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
    'flow.end',  # Terminal node - signals workflow end

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
    'core.flow.end',

    # Legacy short names (backward compatibility)
    'loop',
    'foreach',
    'branch',
    'switch',
    'goto',
    'end',
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


# ---------------------------------------------------------------------------
# Step execution-setting spellings
# ---------------------------------------------------------------------------

# Legacy camelCase spellings of the per-step execution settings, mapped to the
# canonical key the engine reads.
#
# The template builder's settings panel writes the canonical key today
# (NodeExecutionSettingsSimplified.vue), but every template saved before that
# change still carries the camelCase one, and the engine only ever read the
# canonical spelling. The result was silent: a step saying `onError: continue`
# was parsed without complaint and then behaved as `stop`, because the key the
# engine looked for was simply absent.
#
# This table is the panel's own `canonicalField` map, minus `timeoutMs`.
# `timeoutMs` is deliberately NOT aliased to `timeout`: the panel's value is in
# milliseconds (its input is labelled "ms") while the engine's `timeout` is in
# seconds — it is handed straight to `asyncio.wait_for`, and StepTimeoutError
# reports it as seconds. Aliasing the two would silently reinterpret a 30000 ms
# (30 second) budget as 30000 seconds, turning a missing timeout into an
# 8-hour hang. That pair needs a unit conversion agreed with the frontend, not
# a rename, so it is left alone rather than papered over here.
LEGACY_STEP_SETTING_KEYS = {
    'onError': 'on_error',
    'runIf': 'when',
    'foreachAs': 'as',
}


def normalize_step_settings(step_config):
    """Return a step config the engine's canonical settings readers understand.

    Adds the canonical spelling for any legacy execution-setting key present.
    The canonical key wins when both spellings are set, matching how the
    settings panel reads them back (``d.on_error ?? d.onError``).

    The input is never mutated: callers may hold a stored template definition,
    and normalising in place would write the engine's preferred shape back into
    the user's saved data. A shallow copy is returned only when there is
    something to add; otherwise the original object is passed straight through.
    """
    if not isinstance(step_config, dict):
        return step_config

    additions = [
        (legacy, canonical)
        for legacy, canonical in LEGACY_STEP_SETTING_KEYS.items()
        if legacy in step_config and canonical not in step_config
    ]
    if not additions:
        return step_config

    normalized = dict(step_config)
    for legacy, canonical in additions:
        normalized[canonical] = step_config[legacy]
    return normalized


def normalize_step_settings_list(steps):
    """Apply :func:`normalize_step_settings` across a list of step configs."""
    if not isinstance(steps, list):
        return steps
    return [normalize_step_settings(step) for step in steps]
