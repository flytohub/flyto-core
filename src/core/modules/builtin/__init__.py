"""
Builtin Modules

Core modules that run in-process and are essential for workflow execution.
These modules handle flow control and cannot be moved to plugins.

Phase 4: Core Minimal
- Only flow control modules remain in core
- All other modules should be plugins

Flow Modules:
- flow.branch    - Conditional branching (if/then)
- flow.switch    - Multi-way branching (switch/case)
- flow.loop      - Iteration control
- flow.foreach   - List iteration
- flow.goto      - Unconditional jump
- flow.fork      - Parallel split
- flow.merge     - Combine inputs
- flow.join      - Wait for parallel branches
- flow.start     - Workflow entry point
- flow.end       - Workflow exit point
- flow.trigger   - Event triggers
- flow.invoke    - Subflow execution
- flow.container - Embedded subflow
- flow.subflow   - External workflow reference
- flow.breakpoint - Human approval
"""

import logging
from typing import Dict, List, Type, Set

logger = logging.getLogger(__name__)

# List of builtin module IDs (flow control only)
BUILTIN_MODULE_IDS: Set[str] = {
    # Core flow control
    "flow.branch",
    "flow.switch",
    "flow.loop",
    "flow.foreach",
    "flow.goto",

    # Parallel execution
    "flow.fork",
    "flow.merge",
    "flow.join",

    # Workflow lifecycle
    "flow.start",
    "flow.end",
    "flow.trigger",

    # Subflows
    "flow.invoke",
    "flow.container",
    "flow.subflow",

    # Advanced
    "flow.breakpoint",
}


def is_builtin_module(module_id: str) -> bool:
    """
    Check if a module ID is a builtin module.

    Builtin modules run in-process and are essential for workflow execution.
    All other modules should be plugins.

    Args:
        module_id: Module ID to check

    Returns:
        True if builtin, False if should be plugin
    """
    return module_id in BUILTIN_MODULE_IDS


def get_builtin_module_ids() -> List[str]:
    """Get list of all builtin module IDs."""
    return sorted(BUILTIN_MODULE_IDS)


def register_builtin_modules():
    """
    Register all builtin modules with the registry.

    This should be called during core initialization.
    """
    from ..registry import ModuleRegistry

    # Import flow modules to trigger registration
    try:
        from ..atomic.flow import (
            branch,
            switch,
            goto,
            fork,
            merge,
            join,
            start,
            end,
            trigger,
            invoke,
            container,
            subflow_ref,
            breakpoint,
        )
        from ..atomic.flow.loop import module as loop_module

        logger.info(f"Registered {len(BUILTIN_MODULE_IDS)} builtin modules")

    except ImportError as e:
        logger.warning(f"Failed to import some builtin modules: {e}")


def get_module_category(module_id: str) -> str:
    """
    Get the category for a module ID.

    Returns:
        'builtin' for flow modules, 'plugin' for others
    """
    if is_builtin_module(module_id):
        return "builtin"
    return "plugin"


# Module metadata for UI
BUILTIN_MODULE_META = {
    "flow.branch": {
        "label": "Branch",
        "description": "Conditional branching (if/then)",
        "icon": "GitBranch",
        "color": "#F59E0B",
    },
    "flow.switch": {
        "label": "Switch",
        "description": "Multi-way branching (switch/case)",
        "icon": "GitMerge",
        "color": "#F59E0B",
    },
    "flow.loop": {
        "label": "Loop",
        "description": "Repeat N times",
        "icon": "Repeat",
        "color": "#F59E0B",
    },
    "flow.foreach": {
        "label": "For Each",
        "description": "Iterate over a list",
        "icon": "List",
        "color": "#F59E0B",
    },
    "flow.goto": {
        "label": "Goto",
        "description": "Jump to another step",
        "icon": "CornerDownRight",
        "color": "#F59E0B",
    },
    "flow.fork": {
        "label": "Fork",
        "description": "Split into parallel branches",
        "icon": "GitFork",
        "color": "#8B5CF6",
    },
    "flow.merge": {
        "label": "Merge",
        "description": "Combine multiple inputs",
        "icon": "GitMerge",
        "color": "#8B5CF6",
    },
    "flow.join": {
        "label": "Join",
        "description": "Wait for parallel branches",
        "icon": "GitPullRequest",
        "color": "#8B5CF6",
    },
    "flow.start": {
        "label": "Start",
        "description": "Workflow entry point",
        "icon": "Play",
        "color": "#10B981",
    },
    "flow.end": {
        "label": "End",
        "description": "Workflow exit point",
        "icon": "Square",
        "color": "#EF4444",
    },
    "flow.trigger": {
        "label": "Trigger",
        "description": "Workflow trigger",
        "icon": "Zap",
        "color": "#10B981",
    },
    "flow.invoke": {
        "label": "Invoke Workflow",
        "description": "Execute subflow",
        "icon": "ExternalLink",
        "color": "#6366F1",
    },
    "flow.container": {
        "label": "Container",
        "description": "Embedded subflow",
        "icon": "Box",
        "color": "#6366F1",
    },
    "flow.subflow": {
        "label": "Subflow",
        "description": "Reference workflow",
        "icon": "Link",
        "color": "#6366F1",
    },
    "flow.breakpoint": {
        "label": "Breakpoint",
        "description": "Human approval",
        "icon": "UserCheck",
        "color": "#EC4899",
    },
}


def get_builtin_module_meta(module_id: str) -> Dict:
    """Get UI metadata for a builtin module."""
    return BUILTIN_MODULE_META.get(module_id, {
        "label": module_id,
        "description": "",
        "icon": "Box",
        "color": "#6B7280",
    })
