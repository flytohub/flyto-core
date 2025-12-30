"""
Execution Environment Configuration

Environment restrictions and validation.
"""

from typing import Dict, Set

from .enums import ExecutionEnvironment


# LOCAL_ONLY categories: These modules CANNOT run safely in cloud
# - Security risk (arbitrary code execution, file access)
# - Resource intensive (browser automation)
# - Requires local resources (filesystem, local apps)
LOCAL_ONLY_CATEGORIES: Set[str] = {
    # Browser automation - requires real browser, heavy resources
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
MODULE_ENVIRONMENT_OVERRIDES: Dict[str, ExecutionEnvironment] = {
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
