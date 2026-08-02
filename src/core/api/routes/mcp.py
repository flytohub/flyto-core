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

import base64
import binascii
import json
import secrets
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from core.mcp_handler import (
    MODERN_PROTOCOL_VERSION,
    handle_jsonrpc_request,
)

from ..security import require_auth

router = APIRouter(tags=["mcp"])

# Session store: session_id -> {"initialized": True}
_mcp_sessions: Dict[str, dict] = {}
_PROTOCOL_VERSION_META_KEY = "io.modelcontextprotocol/protocolVersion"
_NAMED_METHOD_FIELDS = {"tools/call": "name"}


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


def _payload_uses_modern_protocol(request: Request, payload: dict) -> bool:
    params = payload.get("params")
    metadata = params.get("_meta") if isinstance(params, dict) else None
    return (
        isinstance(metadata, dict)
        and _PROTOCOL_VERSION_META_KEY in metadata
    ) or request.headers.get("MCP-Protocol-Version") == MODERN_PROTOCOL_VERSION


def _decode_mcp_header(value: str) -> str:
    """Decode the Base64 sentinel form supported by MCP name headers."""
    prefix = "=?base64?"
    suffix = "?="
    if not value.startswith(prefix):
        return value
    if not value.endswith(suffix):
        raise ValueError("malformed Base64 sentinel")
    encoded = value[len(prefix):-len(suffix)]
    try:
        return base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("invalid Base64 header value") from exc


def _header_mismatch(payload: dict, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": payload.get("id"),
        "error": {
            "code": -32020,
            "message": f"Header mismatch: {message}",
        },
    }


def _validate_modern_http_headers(request: Request, payload: dict) -> Optional[dict]:
    """Validate the mirrored HTTP headers required by MCP 2026-07-28."""
    params = payload.get("params")
    metadata = params.get("_meta") if isinstance(params, dict) else None
    body_version = (
        metadata.get(_PROTOCOL_VERSION_META_KEY)
        if isinstance(metadata, dict)
        else None
    )
    header_version = request.headers.get("MCP-Protocol-Version")

    if not isinstance(body_version, str):
        return _header_mismatch(
            payload,
            "request metadata is missing MCP protocol version",
        )
    if header_version is None:
        return _header_mismatch(
            payload,
            "required MCP-Protocol-Version header is missing",
        )
    if header_version != body_version:
        return _header_mismatch(
            payload,
            "MCP-Protocol-Version header does not match request metadata",
        )

    method = payload.get("method")
    method_header = request.headers.get("Mcp-Method")
    if not isinstance(method, str) or not method_header:
        return _header_mismatch(payload, "required Mcp-Method header is missing")
    if method_header != method:
        return _header_mismatch(
            payload,
            "Mcp-Method header does not match the JSON-RPC method",
        )

    name_field = _NAMED_METHOD_FIELDS.get(method)
    if name_field is None:
        return None
    expected_name = params.get(name_field) if isinstance(params, dict) else None
    name_header = request.headers.get("Mcp-Name")
    if not isinstance(expected_name, str) or not name_header:
        return _header_mismatch(payload, "required Mcp-Name header is missing")
    try:
        decoded_name = _decode_mcp_header(name_header)
    except ValueError:
        # Header decoding errors are intentionally opaque to remote callers.
        # The decoder's exception chain may contain implementation details.
        return _header_mismatch(payload, "invalid Mcp-Name header encoding")
    if decoded_name != expected_name:
        return _header_mismatch(
            payload,
            "Mcp-Name header does not match the request body",
        )
    return None


@router.post("", dependencies=[Depends(require_auth)])
async def mcp_post(request: Request):
    # Validate Accept header
    err = _validate_accept(request)
    if err:
        return err

    # Parse body
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError, RuntimeError):
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

    if not all(isinstance(item, dict) for item in items):
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "error": {"code": -32600, "message": "Invalid JSON-RPC request"},
            },
        )

    modern = any(_payload_uses_modern_protocol(request, item) for item in items)
    if modern and is_batch:
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "error": {
                    "code": -32600,
                    "message": "MCP 2026-07-28 accepts one JSON-RPC request per POST",
                },
            },
        )
    if modern:
        header_error = _validate_modern_http_headers(request, items[0])
        if header_error is not None:
            return JSONResponse(status_code=400, content=header_error)
        if request.headers.get("mcp-session-id"):
            return JSONResponse(
                status_code=400,
                content=_header_mismatch(
                    items[0],
                    "Mcp-Session-Id is not used by MCP 2026-07-28",
                ),
            )
    else:
        err = _validate_session(request)
        if err:
            return err

    # Get browser and debugger sessions from app state
    browser_sessions: Dict[str, Any] = request.app.state.server.browser_sessions
    debugger_sessions: Dict[str, Any] = request.app.state.server.debugger_sessions
    session_activity: Dict[str, float] = request.app.state.server.session_activity

    # Process each item
    responses = []
    new_session_id = None

    for item in items:
        result = await handle_jsonrpc_request(
            item,
            browser_sessions,
            debugger_sessions,
            session_activity,
        )

        # Only handshake-era clients receive a protocol session.
        if not modern and _is_initialize(item) and result and "result" in result:
            new_session_id = secrets.token_urlsafe(32)
            _mcp_sessions[new_session_id] = {"initialized": True}

        if result is not None:
            responses.append(result)

    # All notifications, no responses needed
    if not responses:
        return Response(status_code=202)

    # Build response
    content = responses if is_batch else responses[0]
    status_code = 200
    if not is_batch and isinstance(content, dict):
        error = content.get("error")
        error_code = error.get("code") if isinstance(error, dict) else None
        if error_code in {-32020, -32021, -32022}:
            status_code = 400
    resp = JSONResponse(status_code=status_code, content=content)

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
