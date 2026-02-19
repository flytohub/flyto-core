# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""API Routes"""

from .modules import router as modules_router
from .workflows import router as workflows_router
from .replay import router as replay_router
from .mcp import router as mcp_router

__all__ = ["modules_router", "workflows_router", "replay_router", "mcp_router"]
