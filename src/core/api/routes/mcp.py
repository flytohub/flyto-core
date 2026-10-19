# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
MCP Streamable HTTP Transport

POST /mcp  — JSON-RPC request/response
GET  /mcp  — 405 (server-initiated SSE not supported yet)
DELETE /mcp — Legacy session termination

Implements stateless MCP Streamable HTTP (2026-07-28) while preserving the
handshake and session behavior needed by older clients.

Auth: this transport exposes module execution (`tools/call` -> `execute_module`)
and is therefore protected by the same Execution-API bearer token as the rest
of the API (deny-by-default). MCP clients connecting over HTTP must send
`Authorization: Bearer <token>`; the token is minted by `init_auth` at startup.
See GHSA-h9f9-h6gm-wc85.
"""

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from core import mcp_protocol
from core.mcp_handler import handle_jsonrpc_request

from ..security import require_auth

router = APIRouter(tags=["mcp"])

# Session store: session_id -> {"initialized": True}
_mcp_sessions: Dict[str, dict] = {}


def _is_notification(item: dict) -> bool:
    """A JSON-RPC notification has no 'id' field."""
    return "id" not in item


def _is_initialize(item: dict) -> bool:
    return item.get("method") == "initialize"


@router.post("", dependencies=[Depends(require_auth)])
async def mcp_post(request: Request):
    # The POST rules (Accept, batches, the 2026-07-28 mirrored headers,
    # handshake sessions) are core.mcp_protocol's, shared with the
    # standalone pack server.
    try:
        body: Any = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError, RuntimeError):
        body = mcp_protocol.PARSE_ERROR

    server = request.app.state.server
    browser_sessions: Dict[str, Any] = server.browser_sessions
    debugger_sessions: Dict[str, Any] = server.debugger_sessions
    session_activity: Dict[str, float] = server.session_activity

    async def dispatch(item: dict):
        return await handle_jsonrpc_request(item, browser_sessions, debugger_sessions, session_activity)

    status, content, headers = await mcp_protocol.handle_http_post(request.headers, body, dispatch, _mcp_sessions)
    if content is None:
        return Response(status_code=status)
    return JSONResponse(status_code=status, content=content, headers=headers)


@router.get("")
async def mcp_get():
    return JSONResponse(
        status_code=405,
        content={"error": "Server-initiated SSE not supported. Use POST for JSON-RPC requests."},
    )


@router.delete("", dependencies=[Depends(require_auth)])
async def mcp_delete(request: Request):
    session_id = request.headers.get("mcp-session-id")
    if not session_id or session_id not in _mcp_sessions:
        return JSONResponse(
            status_code=404,
            content={"error": "Session not found"},
        )

    del _mcp_sessions[session_id]
    return Response(status_code=200)
