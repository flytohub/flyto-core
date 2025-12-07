"""
Module Types

Defines core types for module system including:
- ModuleLevel: Priority and trust classification
- UIVisibility: UI display behavior
- ContextType: Module context requirements
- ExecutionEnvironment: Where modules can safely run
"""
from enum import Enum
from typing import List, Optional, Set


class ExecutionEnvironment(str, Enum):
    """
    Execution environment - determines where modules can safely run.

    LOCAL: Only safe to run on user's local machine
           (browser automation, file system access, etc.)
    CLOUD: Safe to run in cloud environment
           (API calls, data processing, pure functions)
    ALL: Can run in both environments (default for most modules)
    """
    LOCAL = "local"
    CLOUD = "cloud"
    ALL = "all"


class ModuleLevel(str, Enum):
    """
    Module level - determines priority and trust level.

    ATOMIC: Level 2 - Core atomic modules (building blocks, expert mode)
    COMPOSITE: Level 3 - Composite modules (normal user visible)
    TEMPLATE: Level 1 - Workflow templates (one-click solutions)
    PATTERN: Level 4 - Advanced patterns (system internal)
    THIRD_PARTY: Third-party API integrations
    AI_TOOL: AI tools for analysis
    EXTERNAL: External services (MCP, remote agents)
    """
    ATOMIC = "atomic"
    COMPOSITE = "composite"
    TEMPLATE = "template"
    PATTERN = "pattern"
    THIRD_PARTY = "third_party"
    AI_TOOL = "ai_tool"
    EXTERNAL = "external"


class UIVisibility(str, Enum):
    """
    UI visibility level for modules.

    DEFAULT: Show in normal mode (templates, composites)
    EXPERT: Show only in expert collapsed section (atomic modules)
    HIDDEN: Never show in UI (internal system modules)
    """
    DEFAULT = "default"
    EXPERT = "expert"
    HIDDEN = "hidden"


class ContextType(str, Enum):
    """
    Context types that modules can require or provide.

    Used for connection validation between modules.
    """
    BROWSER = "browser"
    PAGE = "page"
    FILE = "file"
    DATA = "data"
    API_RESPONSE = "api_response"
    DATABASE = "database"
    SESSION = "session"


# Priority order for module selection (lower = higher priority)
LEVEL_PRIORITY = {
    ModuleLevel.ATOMIC: 1,
    ModuleLevel.COMPOSITE: 2,
    ModuleLevel.TEMPLATE: 3,
    ModuleLevel.PATTERN: 4,
    ModuleLevel.THIRD_PARTY: 5,
    ModuleLevel.AI_TOOL: 6,
    ModuleLevel.EXTERNAL: 7,
}


# Default context requirements by category
# Used when module does not explicitly declare requires_context
DEFAULT_CONTEXT_REQUIREMENTS = {
    "page": [ContextType.BROWSER],
    "scraper": [ContextType.BROWSER],
    "element": [ContextType.BROWSER],
}


# Default context provisions by category
# Used when module does not explicitly declare provides_context
DEFAULT_CONTEXT_PROVISIONS = {
    "browser": [ContextType.BROWSER],
    "file": [ContextType.FILE],
    "api": [ContextType.API_RESPONSE],
    "data": [ContextType.DATA],
}


# Default UI visibility by category (ADR-001)
# Categories listed here will default to DEFAULT (shown to normal users)
# Categories NOT listed will default to EXPERT (advanced users only)
#
# DEFAULT categories: Complete, user-facing features that work standalone
# EXPERT categories: Low-level operations requiring programming knowledge
DEFAULT_VISIBILITY_CATEGORIES = {
    # AI & Chat - Complete AI integrations
    "ai": UIVisibility.DEFAULT,
    "agent": UIVisibility.DEFAULT,

    # Communication & Notifications - Send messages to users
    "notification": UIVisibility.DEFAULT,
    "communication": UIVisibility.DEFAULT,

    # Cloud Storage - Upload/download files
    "cloud": UIVisibility.DEFAULT,

    # Database - Data operations
    "database": UIVisibility.DEFAULT,
    "db": UIVisibility.DEFAULT,

    # Productivity Tools - External service integrations
    "productivity": UIVisibility.DEFAULT,
    "payment": UIVisibility.DEFAULT,

    # API - HTTP requests and external APIs
    "api": UIVisibility.DEFAULT,

    # High-level browser operations (Launch, Screenshot, Extract)
    # Note: Low-level browser ops (click, type) stay EXPERT
    "browser": UIVisibility.DEFAULT,

    # Image processing - Complete operations
    "image": UIVisibility.DEFAULT,

    # --- EXPERT categories (low-level/programming) ---
    # These are explicitly set to EXPERT for clarity

    # String manipulation - programming primitives
    "string": UIVisibility.EXPERT,
    "text": UIVisibility.EXPERT,

    # Array/Object operations - programming primitives
    "array": UIVisibility.EXPERT,
    "object": UIVisibility.EXPERT,

    # Math operations - programming primitives
    "math": UIVisibility.EXPERT,

    # DateTime manipulation - often needs composition
    "datetime": UIVisibility.EXPERT,

    # File system - low-level ops
    "file": UIVisibility.EXPERT,

    # DOM/Element operations - requires browser knowledge
    "element": UIVisibility.EXPERT,

    # Flow control - programming constructs
    "flow": UIVisibility.EXPERT,

    # Data parsing - technical operations
    "data": UIVisibility.EXPERT,

    # Utility/Meta - system internals
    "utility": UIVisibility.EXPERT,
    "meta": UIVisibility.EXPERT,

    # Testing - developer tools
    "test": UIVisibility.EXPERT,
    "atomic": UIVisibility.EXPERT,
}


def get_default_visibility(category: str) -> UIVisibility:
    """
    Get default UI visibility for a category.

    Args:
        category: Module category name

    Returns:
        UIVisibility.DEFAULT for user-facing categories
        UIVisibility.EXPERT for low-level/programming categories
    """
    return DEFAULT_VISIBILITY_CATEGORIES.get(category, UIVisibility.EXPERT)


# =============================================================================
# Execution Environment Configuration
# =============================================================================
#
# LOCAL_ONLY categories: These modules CANNOT run safely in cloud
# - Security risk (arbitrary code execution, file access)
# - Resource intensive (browser automation)
# - Requires local resources (filesystem, local apps)
#
# When deployment is set to CLOUD mode, these modules will be:
# 1. Hidden from the module selector
# 2. Blocked from execution with clear error message
# =============================================================================

LOCAL_ONLY_CATEGORIES: Set[str] = {
    # Browser automation - requires real browser, heavy resources, security risk
    "browser",
    "page",
    "scraper",
    "element",

    # File system operations - local filesystem access
    "file",

    # Desktop automation (future)
    "desktop",
    "app",
}


# Specific module overrides for environment restrictions
# Use when a module in an otherwise cloud-safe category needs LOCAL_ONLY
# Format: module_id -> ExecutionEnvironment
MODULE_ENVIRONMENT_OVERRIDES = {
    # Database modules with local file access
    "database.sqlite_query": ExecutionEnvironment.LOCAL,
    "database.sqlite_execute": ExecutionEnvironment.LOCAL,

    # Image modules that read local files
    "image.read_local": ExecutionEnvironment.LOCAL,

    # Any module that spawns processes
    "utility.shell_exec": ExecutionEnvironment.LOCAL,
    "utility.run_command": ExecutionEnvironment.LOCAL,
}


def get_module_environment(module_id: str, category: str) -> ExecutionEnvironment:
    """
    Get the execution environment for a module.

    Priority:
    1. Explicit module override (MODULE_ENVIRONMENT_OVERRIDES)
    2. Category default (LOCAL_ONLY_CATEGORIES)
    3. Default to ALL (can run anywhere)

    Args:
        module_id: Full module ID (e.g., "browser.click")
        category: Module category (e.g., "browser")

    Returns:
        ExecutionEnvironment indicating where module can run
    """
    # Check explicit override first
    if module_id in MODULE_ENVIRONMENT_OVERRIDES:
        return MODULE_ENVIRONMENT_OVERRIDES[module_id]

    # Check category
    if category in LOCAL_ONLY_CATEGORIES:
        return ExecutionEnvironment.LOCAL

    # Default: can run anywhere
    return ExecutionEnvironment.ALL


def is_module_allowed_in_environment(
    module_id: str,
    category: str,
    current_env: ExecutionEnvironment
) -> bool:
    """
    Check if a module is allowed to run in the current environment.

    Args:
        module_id: Full module ID
        category: Module category
        current_env: Current execution environment (LOCAL or CLOUD)

    Returns:
        True if module can run in current environment
    """
    module_env = get_module_environment(module_id, category)

    # ALL modules can run anywhere
    if module_env == ExecutionEnvironment.ALL:
        return True

    # LOCAL modules can only run in LOCAL environment
    if module_env == ExecutionEnvironment.LOCAL:
        return current_env == ExecutionEnvironment.LOCAL

    # CLOUD modules can run in both (rare case)
    if module_env == ExecutionEnvironment.CLOUD:
        return True

    return False
