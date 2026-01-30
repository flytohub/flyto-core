"""
Deprecation Notice for Atomic Modules

As of Phase 4 (Core Minimal), atomic modules are being migrated to plugins.
Only flow control modules remain in the core.

Migration Guide:
- flow.* modules -> Stay in core (builtin)
- llm.* modules -> flyto-official_llm plugin
- browser.* modules -> flyto-official_browser plugin
- database.* modules -> flyto-official_database plugin
- ai.* modules -> flyto-official_ai plugin (planned)
- All other modules -> Individual plugins

The atomic directory will be removed in a future version.
Use the plugin system for new modules.
"""

import warnings
import functools
from typing import Callable

# Modules that are deprecated (should use plugins)
DEPRECATED_CATEGORIES = {
    "llm",
    "browser",
    "database",
    "ai",
    "http",
    "email",
    "slack",
    "github",
}


def deprecation_warning(module_id: str):
    """Issue deprecation warning for non-flow atomic modules."""
    category = module_id.split(".")[0] if "." in module_id else module_id

    if category in DEPRECATED_CATEGORIES:
        warnings.warn(
            f"Module '{module_id}' is deprecated and will be moved to a plugin. "
            f"Use the 'flyto-official_{category}' plugin instead.",
            DeprecationWarning,
            stacklevel=3,
        )


def deprecated_module(category: str) -> Callable:
    """
    Decorator to mark a module class as deprecated.

    Usage:
        @deprecated_module("llm")
        class LlmChat(BaseModule):
            ...
    """
    def decorator(cls):
        original_init = cls.__init__

        @functools.wraps(original_init)
        def new_init(self, *args, **kwargs):
            warnings.warn(
                f"Module class '{cls.__name__}' from category '{category}' is deprecated. "
                f"Use the 'flyto-official_{category}' plugin instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            return original_init(self, *args, **kwargs)

        cls.__init__ = new_init
        cls._deprecated = True
        cls._deprecated_plugin = f"flyto-official_{category}"
        return cls

    return decorator


# List of categories that should remain in core
CORE_CATEGORIES = {"flow"}


def is_core_category(category: str) -> bool:
    """Check if category should remain in core."""
    return category in CORE_CATEGORIES


def should_use_plugin(module_id: str) -> bool:
    """Check if module should use plugin system instead."""
    category = module_id.split(".")[0] if "." in module_id else ""
    return category not in CORE_CATEGORIES
