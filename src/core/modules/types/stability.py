"""
Module Stability Helpers

Functions for filtering modules by stability level based on runtime environment.
"""

import os
from typing import Set

from .enums import StabilityLevel


# Environment variable to control stability filtering
# Values: "production", "staging", "development", "local"
FLYTO_ENV_VAR = "FLYTO_ENV"

# Default environment if not set
DEFAULT_ENV = "production"


# Which stability levels are visible in each environment
STABILITY_BY_ENV: dict[str, Set[StabilityLevel]] = {
    "production": {StabilityLevel.STABLE},
    "staging": {StabilityLevel.STABLE, StabilityLevel.BETA},
    "development": {StabilityLevel.STABLE, StabilityLevel.BETA, StabilityLevel.ALPHA},
    "local": {StabilityLevel.STABLE, StabilityLevel.BETA, StabilityLevel.ALPHA, StabilityLevel.DEPRECATED},
}


def get_current_env() -> str:
    """
    Get current runtime environment from FLYTO_ENV variable.

    Returns:
        Environment name: "production", "staging", "development", or "local"
    """
    return os.environ.get(FLYTO_ENV_VAR, DEFAULT_ENV).lower()


def get_allowed_stability_levels(env: str | None = None) -> Set[StabilityLevel]:
    """
    Get stability levels allowed for a given environment.

    Args:
        env: Environment name, or None to use current environment

    Returns:
        Set of allowed StabilityLevel values
    """
    if env is None:
        env = get_current_env()

    return STABILITY_BY_ENV.get(env, STABILITY_BY_ENV["production"])


def is_module_visible(stability: StabilityLevel, env: str | None = None) -> bool:
    """
    Check if a module with given stability should be visible.

    Args:
        stability: Module's stability level
        env: Environment name, or None to use current environment

    Returns:
        True if module should be visible in the environment
    """
    allowed = get_allowed_stability_levels(env)
    return stability in allowed


def get_default_stability() -> StabilityLevel:
    """
    Get default stability level for new modules.

    In development/local: defaults to BETA (so you can test immediately)
    In production/staging: defaults to STABLE

    Returns:
        Default StabilityLevel
    """
    env = get_current_env()
    if env in ("development", "local"):
        return StabilityLevel.BETA
    return StabilityLevel.STABLE
