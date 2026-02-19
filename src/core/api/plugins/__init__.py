# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

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
