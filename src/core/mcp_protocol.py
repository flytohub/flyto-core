# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""MCP protocol plumbing, independent of which tools a server offers.

One implementation of the JSON-RPC dispatch (protocol-era selection,
``initialize``/``server/discover``, ``tools/list``, ``tools/call``) and of the
Streamable HTTP POST handling (Accept check, batch rules, the mirrored
headers MCP 2026-07-28 requires, handshake-era sessions), so every MCP server
flyto-core runs speaks the protocol the same way:

* ``core.mcp_handler`` — the catalog server (``list_modules``,
  ``execute_module`` …), over STDIO (``core.mcp_server``) and HTTP
  (``core.api.routes.mcp``);
* ``core.pack.standalone`` — one portable pack's operations as tools.

A server supplies a :class:`McpServer`: its identity, its instructions, the
tool list and an async ``call_tool``. Nothing here knows any tool.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import secrets
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Mapping, MutableMapping, Optional, Tuple

__all__ = [
    "MODERN_PROTOCOL_VERSION",
    "LEGACY_PROTOCOL_VERSIONS",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "McpServer",
    "negotiate_protocol_version",
    "negotiate_legacy_protocol_version",
    "jsonrpc_error",
    "jsonrpc_result",
    "request_protocol_era",
    "tool_call_body",
    "dispatch_jsonrpc",
    "decode_mcp_header",
    "validate_modern_http_headers",
    "payload_uses_modern_protocol",
    "accepts_mcp_response",
    "handle_http_post",
    "serve_stdio",
]

# MCP 2026-07-28 is stateless and selected on every request through `_meta`.
# Older revisions keep the initialize handshake for compatibility.
# Reference:
# https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning
MODERN_PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)
SUPPORTED_PROTOCOL_VERSIONS = (
    MODERN_PROTOCOL_VERSION,
    *LEGACY_PROTOCOL_VERSIONS,
)
PROTOCOL_VERSION_META_KEY = "io.modelcontextprotocol/protocolVersion"
CLIENT_CAPABILITIES_META_KEY = "io.modelcontextprotocol/clientCapabilities"
CLIENT_INFO_META_KEY = "io.modelcontextprotocol/clientInfo"
SERVER_INFO_META_KEY = "io.modelcontextprotocol/serverInfo"
DISCOVERY_TTL_MS = 60_000
STATIC_LIST_TTL_MS = 60_000
#: Header-validation failures MCP 2026-07-28 answers with HTTP 400.
HEADER_ERROR_CODES = frozenset({-32020, -32021, -32022})
#: JSON-RPC methods whose target is mirrored in the ``Mcp-Name`` header.
NAMED_METHOD_FIELDS = {"tools/call": "name"}


@dataclass(frozen=True)
class McpServer:
    """What one MCP server is: identity, instructions, tools, and the call."""

    server_info: Callable[[], Dict[str, Any]]
    instructions: str
    #: The tools; may be a coroutine when the list depends on who is asking.
    list_tools: Callable[[], Any]
    #: ``(request_id, params, modern) -> JSON-RPC response``.
    call_tool: Callable[[Any, Any, bool], Awaitable[Dict[str, Any]]]
    tools_list_changed: bool = False
    #: Whether ``tools/list`` is the same for every caller, so a modern
    #: result may carry a public cache hint. A per-credential list carries none.
    tools_list_public: bool = True

    def capabilities(self) -> Dict[str, Any]:
        return {"tools": {"listChanged": self.tools_list_changed}}

    def initialize_response(self, client_version: Optional[str]) -> Dict[str, Any]:
        return {
            "protocolVersion": negotiate_legacy_protocol_version(client_version),
            "capabilities": self.capabilities(),
            "serverInfo": self.server_info(),
        }


def negotiate_protocol_version(client_version: Optional[str]) -> str:
    """Select a supported version, preferring the latest revision."""
    if client_version and client_version in SUPPORTED_PROTOCOL_VERSIONS:
        return client_version
    return SUPPORTED_PROTOCOL_VERSIONS[0]


def negotiate_legacy_protocol_version(client_version: Optional[str]) -> str:
    """Select a handshake revision without crossing into stateless MCP."""
    if client_version and client_version in LEGACY_PROTOCOL_VERSIONS:
        return client_version
    return LEGACY_PROTOCOL_VERSIONS[0]


def jsonrpc_error(request_id: Any, code: int, message: str, data: Optional[dict] = None) -> dict:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def modern_result(
    result: dict,
    server_info: Dict[str, Any],
    *,
    ttl_ms: Optional[int] = None,
    cache_scope: Optional[str] = None,
) -> dict:
    """Add the fields required on successful MCP 2026-07-28 results."""
    out = dict(result)
    out.setdefault("resultType", "complete")
    meta = out.get("_meta")
    meta = dict(meta) if isinstance(meta, dict) else {}
    meta.setdefault(SERVER_INFO_META_KEY, server_info)
    out["_meta"] = meta
    if ttl_ms is not None and cache_scope is not None:
        out["ttlMs"] = ttl_ms
        out["cacheScope"] = cache_scope
    return out


def jsonrpc_result(
    request_id: Any,
    result: dict,
    *,
    modern: bool,
    server_info: Callable[[], Dict[str, Any]],
    ttl_ms: Optional[int] = None,
    cache_scope: Optional[str] = None,
) -> dict:
    if modern:
        result = modern_result(result, server_info(), ttl_ms=ttl_ms, cache_scope=cache_scope)
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def request_protocol_era(request_id: Any, method: str, params: Any) -> Tuple[Optional[str], Optional[dict]]:
    """Return the request era plus a structured error when metadata is invalid."""
    if not isinstance(params, dict):
        if method == "server/discover":
            return None, jsonrpc_error(request_id, -32602, "Request params must be an object")
        return "legacy", None

    metadata = params.get("_meta")
    has_version = isinstance(metadata, dict) and PROTOCOL_VERSION_META_KEY in metadata
    if not has_version:
        if method == "server/discover":
            return None, jsonrpc_error(
                request_id, -32602, f"Missing required request metadata: {PROTOCOL_VERSION_META_KEY}"
            )
        return "legacy", None

    requested = metadata.get(PROTOCOL_VERSION_META_KEY)
    if not isinstance(requested, str):
        return None, jsonrpc_error(request_id, -32602, f"{PROTOCOL_VERSION_META_KEY} must be a string")
    if requested != MODERN_PROTOCOL_VERSION:
        return None, jsonrpc_error(
            request_id,
            -32022,
            "Unsupported protocol version",
            {"requested": requested, "supported": list(SUPPORTED_PROTOCOL_VERSIONS)},
        )

    client_capabilities = metadata.get(CLIENT_CAPABILITIES_META_KEY)
    if not isinstance(client_capabilities, dict):
        return None, jsonrpc_error(
            request_id, -32602, f"Missing or invalid request metadata: {CLIENT_CAPABILITIES_META_KEY}"
        )
    client_info = metadata.get(CLIENT_INFO_META_KEY)
    if client_info is not None and (
        not isinstance(client_info, dict)
        or not isinstance(client_info.get("name"), str)
        or not isinstance(client_info.get("version"), str)
    ):
        return None, jsonrpc_error(request_id, -32602, f"Invalid request metadata: {CLIENT_INFO_META_KEY}")
    return "modern", None


def tool_call_body(result: Any) -> Dict[str, Any]:
    """The ``tools/call`` result for one tool's return value."""
    is_error = isinstance(result, dict) and (result.get("error") is not None or result.get("ok") is False)
    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
        "structuredContent": result,
        "isError": is_error,
    }


async def dispatch_jsonrpc(server: McpServer, request: dict) -> Optional[dict]:
    """Handle one JSON-RPC request. ``None`` for a notification."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})
    era, protocol_error = request_protocol_era(req_id, method, params)
    if protocol_error is not None:
        return protocol_error
    modern = era == "modern"

    def result(body: dict, **cache: Any) -> dict:
        return jsonrpc_result(req_id, body, modern=modern, server_info=server.server_info, **cache)

    if method == "initialize" and not modern:
        client_version = params.get("protocolVersion") if isinstance(params, dict) else None
        return result(server.initialize_response(client_version))

    if method == "server/discover" and modern:
        return result(
            {
                "supportedVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
                "capabilities": server.capabilities(),
                "instructions": server.instructions,
            },
            ttl_ms=DISCOVERY_TTL_MS,
            cache_scope="public",
        )

    if modern and method in {"initialize", "ping", "logging/setLevel"}:
        return jsonrpc_error(req_id, -32601, f"Method not found: {method}")

    if method == "tools/list":
        tools = server.list_tools()
        if asyncio.iscoroutine(tools):
            tools = await tools
        if not server.tools_list_public:
            return result({"tools": tools})
        return result({"tools": tools}, ttl_ms=STATIC_LIST_TTL_MS, cache_scope="public")

    if method == "tools/call":
        return await server.call_tool(req_id, params, modern)

    if method == "ping":
        return jsonrpc_result(req_id, {}, modern=False, server_info=server.server_info)

    if method.startswith("notifications/"):
        return None

    if req_id is not None:
        return jsonrpc_error(req_id, -32601, f"Method not found: {method}")
    return None


# ---------------------------------------------------------------------------
# Streamable HTTP
# ---------------------------------------------------------------------------


def decode_mcp_header(value: str) -> str:
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


def header_mismatch(payload: dict, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": payload.get("id"), "error": {"code": -32020, "message": f"Header mismatch: {message}"}}


def validate_modern_http_headers(headers: Mapping[str, str], payload: dict) -> Optional[dict]:
    """Validate the mirrored HTTP headers required by MCP 2026-07-28.

    ``headers`` must look names up case-insensitively, as both Starlette's
    and aiohttp's request headers do.
    """
    params = payload.get("params")
    metadata = params.get("_meta") if isinstance(params, dict) else None
    body_version = metadata.get(PROTOCOL_VERSION_META_KEY) if isinstance(metadata, dict) else None
    header_version = headers.get("MCP-Protocol-Version")

    if not isinstance(body_version, str):
        return header_mismatch(payload, "request metadata is missing MCP protocol version")
    if header_version is None:
        return header_mismatch(payload, "required MCP-Protocol-Version header is missing")
    if header_version != body_version:
        return header_mismatch(payload, "MCP-Protocol-Version header does not match request metadata")

    method = payload.get("method")
    method_header = headers.get("Mcp-Method")
    if not isinstance(method, str) or not method_header:
        return header_mismatch(payload, "required Mcp-Method header is missing")
    if method_header != method:
        return header_mismatch(payload, "Mcp-Method header does not match the JSON-RPC method")

    name_field = NAMED_METHOD_FIELDS.get(method)
    if name_field is None:
        return None
    expected_name = params.get(name_field) if isinstance(params, dict) else None
    name_header = headers.get("Mcp-Name")
    if not isinstance(expected_name, str) or not name_header:
        return header_mismatch(payload, "required Mcp-Name header is missing")
    try:
        decoded_name = decode_mcp_header(name_header)
    except ValueError:
        # Header decoding errors are intentionally opaque to remote callers.
        # The decoder's exception chain may contain implementation details.
        return header_mismatch(payload, "invalid Mcp-Name header encoding")
    if decoded_name != expected_name:
        return header_mismatch(payload, "Mcp-Name header does not match the request body")
    return None


def payload_uses_modern_protocol(headers: Mapping[str, str], payload: dict) -> bool:
    params = payload.get("params")
    metadata = params.get("_meta") if isinstance(params, dict) else None
    return (
        isinstance(metadata, dict) and PROTOCOL_VERSION_META_KEY in metadata
    ) or headers.get("MCP-Protocol-Version") == MODERN_PROTOCOL_VERSION


def accepts_mcp_response(accept: Optional[str]) -> bool:
    """The ``Accept`` header admits a JSON or event-stream answer."""
    accept = accept if accept is not None else "*/*"
    return any(kind in accept for kind in ("application/json", "text/event-stream", "*/*"))


def _rpc_error(code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "error": {"code": code, "message": message}}


async def handle_http_post(
    headers: Mapping[str, str],
    body: Any,
    dispatch: Callable[[dict], Awaitable[Optional[dict]]],
    sessions: MutableMapping[str, dict],
) -> Tuple[int, Any, Dict[str, str]]:
    """One Streamable HTTP POST: ``(status, JSON content or None, extra headers)``.

    ``body`` is the parsed JSON, or :data:`PARSE_ERROR` when it did not parse.
    ``sessions`` holds the handshake-era sessions this endpoint minted.
    """
    if not accepts_mcp_response(headers.get("accept")):
        return 406, {"error": "Not Acceptable: must accept application/json or text/event-stream"}, {}
    if body is PARSE_ERROR:
        return 400, _rpc_error(-32700, "Parse error"), {}

    is_batch = isinstance(body, list)
    items: List[Any] = body if is_batch else [body]
    if not items:
        return 400, _rpc_error(-32600, "Empty batch"), {}
    if not all(isinstance(item, dict) for item in items):
        return 400, _rpc_error(-32600, "Invalid JSON-RPC request"), {}

    modern = any(payload_uses_modern_protocol(headers, item) for item in items)
    if modern and is_batch:
        return 400, _rpc_error(-32600, "MCP 2026-07-28 accepts one JSON-RPC request per POST"), {}
    if modern:
        header_error = validate_modern_http_headers(headers, items[0])
        if header_error is not None:
            return 400, header_error, {}
        if headers.get("mcp-session-id"):
            return 400, header_mismatch(items[0], "Mcp-Session-Id is not used by MCP 2026-07-28"), {}
    else:
        session_id = headers.get("mcp-session-id")
        if session_id and session_id not in sessions:
            return 404, {"error": f"Session not found: {session_id}"}, {}

    responses = []
    new_session_id = None
    for item in items:
        result = await dispatch(item)
        # Only handshake-era clients receive a protocol session.
        if not modern and item.get("method") == "initialize" and result and "result" in result:
            new_session_id = secrets.token_urlsafe(32)
            sessions[new_session_id] = {"initialized": True}
        if result is not None:
            responses.append(result)

    if not responses:
        return 202, None, {}
    content = responses if is_batch else responses[0]
    status = 200
    if not is_batch and isinstance(content, dict):
        error = content.get("error")
        if (error.get("code") if isinstance(error, dict) else None) in HEADER_ERROR_CODES:
            status = 400
    return status, content, ({"Mcp-Session-Id": new_session_id} if new_session_id else {})


class _ParseError:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "PARSE_ERROR"


#: The ``body`` :func:`handle_http_post` receives when the request did not parse.
PARSE_ERROR: Any = _ParseError()


# ---------------------------------------------------------------------------
# STDIO
# ---------------------------------------------------------------------------


async def serve_stdio(
    dispatch: Callable[[dict], Awaitable[Optional[dict]]],
    *,
    read_line: Callable[[], str],
    write_line: Callable[[str], None],
) -> None:
    """Newline-delimited JSON-RPC until EOF: one request per line, one response per line.

    A line that is not JSON is skipped. A request the dispatcher raises on is
    answered with a JSON-RPC error rather than ending the loop.
    """
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, read_line)
        if not line:
            break
        try:
            request = json.loads(line.strip())
            response = await dispatch(request)
            if response is not None:
                write_line(json.dumps(response))
        except json.JSONDecodeError:
            pass
        except Exception as exc:  # noqa: BLE001 - the loop answers and keeps serving
            write_line(json.dumps({"jsonrpc": "2.0", "error": {"code": -32000, "message": str(exc)}}))
