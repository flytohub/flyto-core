"""
Core API Module

Provides API services, routes, and the HTTP Execution API server.

Usage:
    python -m core.api          # Start HTTP server
    flyto serve                 # Via CLI
"""

from .plugins import (
    PluginService,
    get_plugin_service,
    create_plugin_router,
)
from .server import create_app, main

__all__ = [
    "PluginService",
    "get_plugin_service",
    "create_plugin_router",
    "create_app",
    "main",
]
