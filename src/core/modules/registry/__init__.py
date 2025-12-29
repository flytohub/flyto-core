"""
Module Registry - Registration and Management

Re-exports all public APIs for backward compatibility.
"""

from .core import ModuleRegistry
from .decorators import register_module
from .localization import get_localized_value
from .ports import generate_dynamic_ports, slugify
from .catalog import ModuleCatalogManager, get_catalog_manager

# Keep the old function name for backward compatibility
_get_localized_value = get_localized_value
_slugify = slugify

__all__ = [
    # Core
    'ModuleRegistry',

    # Decorators
    'register_module',

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
]
