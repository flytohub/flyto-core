"""
Module Registry - Registration and Management

Re-exports all public APIs for backward compatibility.
"""

from .core import (
    ModuleRegistry,
    get_localized_value,
    PluginInfo,
    RegistrySnapshot,
    REGISTRY_VERSION,
)
from .decorators import register_module
from ..express import module, mod, ParamHelper, create_simple_module
from .ports import generate_dynamic_ports, slugify
from .catalog import ModuleCatalogManager, get_catalog_manager
from .quality_validator import (
    ModuleQualityValidator,
    QualityReport,
    validate_module_quality,
)
from .validation_types import (
    ValidationMode,
    ValidationIssue,
    Severity,
    get_validation_mode,
)

# Keep the old function name for backward compatibility
_get_localized_value = get_localized_value
_slugify = slugify


def get_module(module_id: str):
    """
    Get a module class by ID.

    Convenience function that wraps ModuleRegistry.get().

    Args:
        module_id: The module identifier (e.g., 'browser.launch')

    Returns:
        Module class if found, None otherwise
    """
    return ModuleRegistry.get(module_id)


def get_registry():
    """
    Get the ModuleRegistry instance.

    Returns:
        ModuleRegistry instance
    """
    return ModuleRegistry()


__all__ = [
    # Core
    'ModuleRegistry',
    'REGISTRY_VERSION',

    # Plugin System (Open Core)
    'PluginInfo',
    'RegistrySnapshot',

    # Decorators
    'register_module',

    # Express Mode (simplified decorator)
    'module',
    'mod',
    'ParamHelper',
    'create_simple_module',

    # Convenience functions
    'get_module',
    'get_registry',

    # Localization
    'get_localized_value',
    '_get_localized_value',  # Deprecated alias

    # Ports
    'generate_dynamic_ports',
    'slugify',
    '_slugify',  # Deprecated alias

    # Catalog
    'ModuleCatalogManager',
    'get_catalog_manager',

    # Quality Validation
    'ModuleQualityValidator',
    'ValidationIssue',
    'QualityReport',
    'Severity',
    'validate_module_quality',
]
