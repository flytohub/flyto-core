"""
MCP Streamable HTTP Transport

POST /mcp  — JSON-RPC request/response (single or batch)
GET  /mcp  — 405 (server-initiated SSE not supported yet)
DELETE /mcp — Session termination

Implements MCP Streamable HTTP transport (2025-03-26 spec).
No Bearer token required — MCP clients don't send auth headers.
"""

import secrets
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from core.mcp_handler import handle_jsonrpc_request

router = APIRouter(tags=["mcp"])

# Session store: session_id -> {"initialized": True}
_mcp_sessions: Dict[str, dict] = {}


def _validate_accept(request: Request) -> Optional[Response]:
    """Validate Accept header per MCP spec. Returns error response or None."""
    accept = request.headers.get("accept", "*/*")
    valid = any(t in accept for t in ("application/json", "text/event-stream", "*/*"))
    if not valid:
        return JSONResponse(
            status_code=406,
            content={"error": "Not Acceptable: must accept application/json or text/event-stream"},
        )
    return None


def _validate_session(request: Request, required: bool = False) -> Optional[Response]:
    """Validate Mcp-Session-Id header. Returns error response or None."""
    session_id = request.headers.get("mcp-session-id")
    if session_id and session_id not in _mcp_sessions:
        return JSONResponse(
            status_code=404,
            content={"error": f"Session not found: {session_id}"},
        )
    if required and not session_id:
        return JSONResponse(
            status_code=400,
            content={"error": "Missing Mcp-Session-Id header"},
        )
    return None


def _is_notification(item: dict) -> bool:
    """A JSON-RPC notification has no 'id' field."""
    return "id" not in item


def _is_initialize(item: dict) -> bool:
    return item.get("method") == "initialize"


@router.post("")
async def mcp_post(request: Request):
    # Validate Accept header
    err = _validate_accept(request)
    if err:
        return err

    # Validate session if provided
    err = _validate_session(request)
    if err:
        return err

    # Parse body
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}},
        )

    # Normalize to list for uniform processing
    is_batch = isinstance(body, list)
    items: List[dict] = body if is_batch else [body]

    if not items:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "error": {"code": -32600, "message": "Empty batch"}},
        )

    # Get browser sessions from app state
    browser_sessions: Dict[str, Any] = request.app.state.server.browser_sessions

    # Process each item
    responses = []
    new_session_id = None

    for item in items:
        result = await handle_jsonrpc_request(item, browser_sessions)

        # On successful initialize, create a session
        if _is_initialize(item) and result and "result" in result:
            new_session_id = secrets.token_urlsafe(32)
            _mcp_sessions[new_session_id] = {"initialized": True}

        if result is not None:
            responses.append(result)

    # All notifications, no responses needed
    if not responses:
        return Response(status_code=202)

    # Build response
    content = responses if is_batch else responses[0]
    resp = JSONResponse(content=content)

    # Set session header on initialize
    if new_session_id:
        resp.headers["Mcp-Session-Id"] = new_session_id

    return resp


@router.get("")
async def mcp_get():
    return JSONResponse(
        status_code=405,
        content={"error": "Server-initiated SSE not supported. Use POST for JSON-RPC requests."},
    )


@router.delete("")
async def mcp_delete(request: Request):
    session_id = request.headers.get("mcp-session-id")
    if not session_id or session_id not in _mcp_sessions:
        return JSONResponse(
            status_code=404,
            content={"error": "Session not found"},
        )

    del _mcp_sessions[session_id]
    return Response(status_code=200)
