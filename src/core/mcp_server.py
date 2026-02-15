#!/usr/bin/env python3
"""
Flyto Core MCP Server — STDIO Transport

Thin shell over mcp_handler.py for STDIO-based MCP communication.

Usage:
    python -m core.mcp_server

Claude Code config (~/.claude/mcp_servers.json):
{
    "flyto-core": {
        "command": "python",
        "args": ["-m", "core.mcp_server"],
        "cwd": "/path/to/flyto-core/src"
    }
}
"""

import json
import sys
import os
import asyncio
from typing import Any, Dict

from core.mcp_handler import (
    handle_jsonrpc_request,
    execute_module as _handler_execute_module,
    TOOLS,
    SERVER_VERSION,
)

# Browser session store — persists BrowserDriver across MCP tool calls (STDIO-specific)
_browser_sessions: Dict[str, Any] = {}

# ============================================================
# Local Development: Allow localhost for browser testing
# ============================================================
os.environ.setdefault('FLYTO_ALLOWED_HOSTS', 'localhost,127.0.0.1')


async def execute_module(module_id, params, context=None):
    """Backward-compatible wrapper that injects STDIO _browser_sessions."""
    return await _handler_execute_module(
        module_id, params, context=context, browser_sessions=_browser_sessions,
    )


async def async_main():
    """MCP Server main loop — persistent event loop for browser session survival."""
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break  # EOF
        try:
            request = json.loads(line.strip())
            response = await handle_jsonrpc_request(request, _browser_sessions)
            if response is not None:
                print(json.dumps(response), flush=True)
        except json.JSONDecodeError:
            pass
        except Exception as e:
            print(json.dumps({"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}}), flush=True)

    # Cleanup: close all browser sessions to prevent zombie Chromium processes
    for session_id, driver in list(_browser_sessions.items()):
        try:
            await driver.close()
        except Exception:
            pass
    _browser_sessions.clear()


def main():
    """Entry point — runs the async main loop."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
