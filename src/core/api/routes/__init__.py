# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Aggregates the Core HTTP API routers that the API server mounts.

Re-exports exactly one `APIRouter` per route module — modules, workflows,
replay, MCP, and extensions — so `src/core/api/server.py` mounts an explicit,
single-source list instead of importing each submodule by hand.

This package initializer defines no route, prefix, dependency, or handler:
it only binds names. Nothing about request handling or auth depends on it.
"""

from .extensions import router as extensions_router
from .mcp import router as mcp_router
from .modules import router as modules_router
from .replay import router as replay_router
from .workflows import router as workflows_router

__all__ = [
    "modules_router",
    "workflows_router",
    "replay_router",
    "mcp_router",
    "extensions_router",
]
