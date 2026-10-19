#!/usr/bin/env python3
# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Flyto2 Core MCP Server — STDIO Transport

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

import asyncio
import contextlib
import os
import sys
from typing import Any, Dict

from core.mcp_handler import execute_module as _handler_execute_module
from core.mcp_handler import handle_jsonrpc_request
from core.mcp_protocol import serve_stdio
from core.session_reaper import reaper_loop

# Browser session store — persists BrowserDriver across MCP tool calls (STDIO-specific)
_browser_sessions: Dict[str, Any] = {}

# Debugger session store — persists ReverseSession (CDP debugger) across MCP tool
# calls (STDIO-specific). Process-local like _browser_sessions: the live
# CDPSession object only exists in this process, so no other transport process
# could act on it anyway.
_debugger_sessions: Dict[str, Any] = {}

# Last-used timestamp per session id (either store) — feeds the idle-timeout
# reaper below so an abandoned session doesn't leak a Chromium process/CDP
# session for the life of this server process. See session_reaper.py.
_session_activity: Dict[str, float] = {}

# ============================================================
# Host allowlist — caller MUST opt in
# ============================================================
# Earlier versions defaulted FLYTO_ALLOWED_HOSTS to
# "localhost,127.0.0.1" so the dev experience was friction-free. That
# turned MCP into a confused-deputy SSRF: an LLM client (Claude
# Desktop, Claude Code, anything else over STDIO) could ask the
# server to navigate to the host machine's own services without the
# operator ever opting in.
#
# Now we leave FLYTO_ALLOWED_HOSTS unset unless the caller sets it
# explicitly via the MCP client config:
#
#   "env": { "FLYTO_ALLOWED_HOSTS": "yourdomain.com" }
#
# Local-dev convenience is preserved by setting
# FLYTO_MCP_ALLOW_LOCALHOST=1 on your shell — opt-in, not implicit.
if os.environ.get('FLYTO_MCP_ALLOW_LOCALHOST') == '1':
    os.environ.setdefault('FLYTO_ALLOWED_HOSTS', 'localhost,127.0.0.1')


async def execute_module(module_id, params, context=None):
    """Backward-compatible wrapper that injects STDIO _browser_sessions."""
    return await _handler_execute_module(
        module_id, params, context=context,
        browser_sessions=_browser_sessions,
        debugger_sessions=_debugger_sessions,
        session_activity=_session_activity,
    )


async def async_main():
    """MCP Server main loop — persistent event loop for browser session survival."""
    reaper_task = asyncio.create_task(
        reaper_loop(_browser_sessions, _debugger_sessions, _session_activity)
    )

    async def dispatch(request):
        return await handle_jsonrpc_request(
            request, _browser_sessions, _debugger_sessions, _session_activity,
        )

    def write_line(text):
        print(text, flush=True)

    await serve_stdio(dispatch, read_line=sys.stdin.readline, write_line=write_line)

    reaper_task.cancel()
    await asyncio.gather(reaper_task, return_exceptions=True)

    # Cleanup: detach any remaining debugger sessions first — detach() is
    # best-effort and safe even mid-pause. The idle-timeout reaper above
    # catches sessions abandoned mid-workflow; this is the final backstop
    # for whatever's still open at process EOF.
    for reverse_session in list(_debugger_sessions.values()):
        with contextlib.suppress(Exception):
            await reverse_session.detach()
    _debugger_sessions.clear()

    # Cleanup: close all browser sessions to prevent zombie Chromium processes
    for driver in list(_browser_sessions.values()):
        with contextlib.suppress(Exception):
            await driver.close()
    _browser_sessions.clear()


def main():
    """Entry point — runs the async main loop."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
