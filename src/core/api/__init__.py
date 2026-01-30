"""
Core API Module

Provides API services and routes for core functionality.
"""

from .plugins import (
    PluginService,
    get_plugin_service,
    create_plugin_router,
)

__all__ = [
    "PluginService",
    "get_plugin_service",
    "create_plugin_router",
]
