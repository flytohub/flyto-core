"""
Plugin API Module

Provides API endpoints for plugin management.
"""

from .service import PluginService, get_plugin_service
from .routes import create_plugin_router

__all__ = [
    "PluginService",
    "get_plugin_service",
    "create_plugin_router",
]
