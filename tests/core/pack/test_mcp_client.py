"""The MCP client runs against an in-process fake Streamable HTTP server.

Nothing here reaches a real MCP server. The fake answers the three methods a
consumer needs (``initialize``, ``tools/list``, ``tools/call``), in plain JSON
or as an event stream, and records every request it saw so a test can read
exactly which credential reached it.
"""

import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from core.pack.mcp_client import (
    MCP_FAILURES,
    McpClient,
    normalize_tools,
    tool_digest,
)

RESOURCE_TOKEN = "resource-token-not-real"
INBOUND_TOKEN = "inbound-session-token-not-real"

TOOLS = [
    {"name": "ratings.read", "description": "Read one rating", "inputSchema": {
        "type": "object", "properties": {"company": {"type": "string"}}, "required": ["company"]},
     "annotations": {"readOnlyHint": True, "openWorldHint": True}},
    {"name": "ticket.delete", "description": "Delete a ticket", "inputSchema": {
        "type": "object", "properties": {"id": {"type": "string"}}},
     "annotations": {"destructiveHint": True, "idempotentHint": True, "title": "Delete"}},
]


class FakeMcp(BaseHTTPRequestHandler):
    seen: list = []
    mode = "json"           # json | sse
    behaviour = "ok"        # ok | unauthorized | server_error | slow | redirect | rpc_error | not_json
    page_size = 1

    def log_message(self, *args):
        return None

    def _send(self, status, payload=None, headers=None, raw=None):
        body = raw if raw is not None else (b"" if payload is None else json.dumps(payload).encode())
        self.send_response(status)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        if payload is not None and raw is None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _answer(self, message, session):
        headers = {"Mcp-Session-Id": session}
        if FakeMcp.mode == "sse":
            event = b"event: message\ndata: " + json.dumps(message).encode() + b"\n\n"
            # A notification first: the client must pick the response by id.
            note = b"data: " + json.dumps({"jsonrpc": "2.0", "method": "notifications/progress"}).encode() + b"\n\n"
            headers["Content-Type"] = "text/event-stream"
            self._send(200, headers=headers, raw=note + event)
            return
        self._send(200, message, headers)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length).decode() or "{}")
        FakeMcp.seen.append({
            "method": request.get("method"),
            "auth": self.headers.get("Authorization"),
            "session": self.headers.get("Mcp-Session-Id"),
            "version": self.headers.get("MCP-Protocol-Version"),
            "accept": self.headers.get("Accept"),
            "headers": dict(self.headers.items()),
            "params": request.get("params"),
        })
        behaviour = FakeMcp.behaviour
        if behaviour == "unauthorized":
            self._send(401, {"error": "invalid_token"},
                       {"WWW-Authenticate": 'Bearer resource_metadata="https://as.example/.well-known/x"'})
            return
        if behaviour == "server_error":
            self._send(503, {"error": "down"})
            return
        if behaviour == "redirect":
            self._send(307, None, {"Location": "https://elsewhere.example/mcp"})
            return
        if behaviour == "slow":
            time.sleep(1.5)
        if self.headers.get("Authorization") != f"Bearer {RESOURCE_TOKEN}":
            self._send(401, {"error": "invalid_token"})
            return
        method = request.get("method")
        if method == "notifications/initialized":
            self._send(202)
            return
        if behaviour == "not_json" and method == "tools/call":
            self._send(200, raw=b"<html>", headers={"Content-Type": "application/json"})
            return
        if method == "initialize":
            self._answer({"jsonrpc": "2.0", "id": request["id"], "result": {
                "protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake", "version": "1"}}}, "session-1")
            return
        if self.headers.get("Mcp-Session-Id") != "session-1":
            self._send(400, {"error": "no session"})
            return
        if method == "tools/list":
            cursor = int((request.get("params") or {}).get("cursor") or 0)
            page = TOOLS[cursor:cursor + FakeMcp.page_size]
            result = {"tools": page}
            if cursor + FakeMcp.page_size < len(TOOLS):
                result["nextCursor"] = str(cursor + FakeMcp.page_size)
            self._answer({"jsonrpc": "2.0", "id": request["id"], "result": result}, "session-1")
            return
        if method == "tools/call":
            params = request.get("params") or {}
            if behaviour == "rpc_error":
                self._answer({"jsonrpc": "2.0", "id": request["id"],
                              "error": {"code": -32602, "message": f"Unknown tool: {params.get('name')}"}}, "session-1")
                return
            if params.get("name") == "ticket.delete":
                self._answer({"jsonrpc": "2.0", "id": request["id"], "result": {
                    "isError": True, "content": [{"type": "text", "text": "ticket is locked"}]}}, "session-1")
                return
            self._answer({"jsonrpc": "2.0", "id": request["id"], "result": {
                "content": [{"type": "text", "text": "rating B"}],
                "structuredContent": {"company": params["arguments"]["company"], "rating": "B"}}}, "session-1")
            return
        self._answer({"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32601, "message": "no"}}, "s")


@pytest.fixture
def server(monkeypatch):
    FakeMcp.seen, FakeMcp.mode, FakeMcp.behaviour, FakeMcp.page_size = [], "json", "ok", 1
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeMcp)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    # The SSRF guard admits this loopback server only because the test says so.
    monkeypatch.setenv("FLYTO_ALLOWED_HOSTS", "127.0.0.1")
    monkeypatch.setenv("FLYTO_HTTP_ALLOWED_PORTS", str(port))
    yield f"http://127.0.0.1:{port}/mcp"
    httpd.shutdown()
    httpd.server_close()


def client(url, **kwargs):
    kwargs.setdefault("credential", RESOURCE_TOKEN)
    return McpClient(url, **kwargs)


# -- discovery ---------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["json", "sse"])
async def test_tools_list_reads_every_page_with_schemas_and_hints(server, mode):
    FakeMcp.mode = mode
    answer = await client(server).list_tools()
    assert answer["ok"] is True
    tools = answer["data"]["tools"]
    assert [tool["name"] for tool in tools] == ["ratings.read", "ticket.delete"]
    assert tools[0]["input_schema"]["required"] == ["company"]
    # Only the four behaviour hints are kept, as hints; a title is not one.
    assert tools[0]["hints"] == {"readOnlyHint": True, "openWorldHint": True}
    assert tools[1]["hints"] == {"destructiveHint": True, "idempotentHint": True}
    assert len(tools[0]["digest"]) == 64
    # Initialized, then a session id and the negotiated version on every later request.
    methods = [item["method"] for item in FakeMcp.seen]
    assert methods[:2] == ["initialize", "notifications/initialized"]
    later = [item for item in FakeMcp.seen if item["method"] == "tools/list"]
    assert len(later) == 2 and all(item["session"] == "session-1" for item in later)
    assert all(item["version"] == "2025-06-18" for item in later)
    assert "text/event-stream" in FakeMcp.seen[0]["accept"]


def test_a_changed_schema_or_hint_is_a_different_digest():
    base = normalize_tools(TOOLS)[0]
    widened = json.loads(json.dumps(TOOLS))
    widened[0]["inputSchema"]["properties"]["limit"] = {"type": "number"}
    hinted = json.loads(json.dumps(TOOLS))
    hinted[0]["annotations"]["readOnlyHint"] = False
    assert normalize_tools(widened)[0]["digest"] != base["digest"]
    assert normalize_tools(hinted)[0]["digest"] != base["digest"]
    # Key order and the display title are not the tool.
    reordered = {**TOOLS[0], "annotations": {"openWorldHint": True, "readOnlyHint": True, "title": "x"}}
    assert tool_digest(normalize_tools([reordered])[0]) == base["digest"]


def test_a_malformed_tool_is_named_not_dropped():
    tools = normalize_tools([{"description": "no name"}, {"name": "ok", "inputSchema": []}, TOOLS[0]])
    assert [tool.get("refused") for tool in tools[:2]] == ["MCP_TOOL_MALFORMED", "MCP_TOOL_MALFORMED"]
    assert tools[2]["name"] == "ratings.read"


# -- calls -------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["json", "sse"])
async def test_a_tool_call_returns_its_content(server, mode):
    FakeMcp.mode = mode
    answer = await client(server).call_tool("ratings.read", {"company": "c-1"})
    assert answer == {"ok": True, "data": {
        "content": [{"type": "text", "text": "rating B"}],
        "structured_content": {"company": "c-1", "rating": "B"}}}
    assert FakeMcp.seen[-1]["params"] == {"name": "ratings.read", "arguments": {"company": "c-1"}}


async def test_is_error_is_a_typed_failure_never_an_empty_success(server):
    answer = await client(server).call_tool("ticket.delete", {"id": "t-1"})
    assert answer["ok"] is False and answer["error_code"] == "MCP_TOOL_ERROR"
    assert "ticket is locked" in answer["error"]
    assert answer["final"] is True


@pytest.mark.parametrize("behaviour, code", [
    ("unauthorized", "PROVIDER_UNAUTHORIZED"),
    ("server_error", "PROVIDER_ERROR"),
    ("redirect", "PROVIDER_REDIRECT_REFUSED"),
    ("rpc_error", "MCP_INVALID_PARAMS"),
    ("not_json", "PROVIDER_INVALID_RESPONSE"),
])
async def test_every_failure_is_typed(server, behaviour, code):
    FakeMcp.behaviour = behaviour
    answer = await client(server).call_tool("ratings.read", {"company": "c-1"})
    assert answer["ok"] is False
    assert answer["error_code"] == code
    assert code in MCP_FAILURES or code.startswith("PROVIDER_")


async def test_a_timeout_is_typed(server):
    FakeMcp.behaviour = "slow"
    answer = await client(server, timeout_ms=300).call_tool("ratings.read", {"company": "c-1"})
    assert answer["ok"] is False and answer["error_code"] == "PROVIDER_TIMEOUT"


async def test_an_unreachable_server_is_typed(monkeypatch):
    monkeypatch.setenv("FLYTO_ALLOWED_HOSTS", "127.0.0.1")
    monkeypatch.setenv("FLYTO_HTTP_ALLOWED_PORTS", "9")
    answer = await client("http://127.0.0.1:9/mcp", timeout_ms=500).list_tools()
    assert answer["ok"] is False and answer["error_code"] == "PROVIDER_UNREACHABLE"


async def test_a_private_address_is_refused_unless_the_owner_named_it(monkeypatch):
    monkeypatch.delenv("FLYTO_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("FLYTO_HTTP_ALLOWED_PORTS", raising=False)
    answer = await client("http://127.0.0.1:9/mcp", timeout_ms=500).list_tools()
    assert answer["error_code"] == "SSRF_BLOCKED"


async def test_a_refusal_is_final(server):
    FakeMcp.behaviour = "unauthorized"
    answer = await client(server).list_tools()
    assert answer["error_code"] == "PROVIDER_UNAUTHORIZED" and answer["final"] is True
    # One request, no retry: the server's refusal stands.
    assert len(FakeMcp.seen) == 1


async def test_no_credential_is_a_typed_failure_before_any_request(server):
    answer = await McpClient(server, credential=None, credential_required=True).list_tools()
    assert answer["error_code"] == "CREDENTIAL_MISSING"
    assert FakeMcp.seen == []


# -- no token passthrough ----------------------------------------------------------


async def test_only_the_resource_credential_reaches_the_server(server, monkeypatch):
    """Rule 8: a token issued to Flyto2 is never forwarded to a provider.

    The process holds an inbound token in every place one lives (the
    environment a host reads its own Cloud token from, and the bearer an MCP
    client presented). The server must see the resource's own credential and
    nothing else, on every request.
    """
    for name in ("FLYTO_API_TOKEN", "FLYTO_OFFLINE_MCP_TOKEN", "FLYTO_DEVICE_TOKEN", "AUTHORIZATION"):
        monkeypatch.setenv(name, INBOUND_TOKEN)
    await client(server).call_tool("ratings.read", {"company": "c-1"})
    assert FakeMcp.seen
    for request in FakeMcp.seen:
        assert request["auth"] == f"Bearer {RESOURCE_TOKEN}"
        assert all(INBOUND_TOKEN not in str(value) for value in request["headers"].values())


def test_the_client_takes_no_caller_headers():
    with pytest.raises(TypeError):
        McpClient("https://mcp.example/mcp", credential=RESOURCE_TOKEN, headers={"Authorization": "Bearer x"})


async def test_an_echoed_credential_never_reaches_the_failure_text(server):
    FakeMcp.behaviour = "rpc_error"
    answer = await client(server).call_tool(RESOURCE_TOKEN, {})
    assert RESOURCE_TOKEN not in json.dumps(answer)


def test_failure_vocabulary_is_closed():
    assert set(MCP_FAILURES) >= {"MCP_TOOL_ERROR", "MCP_RPC_ERROR", "MCP_INVALID_PARAMS", "MCP_TOOL_MALFORMED"}
    assert asyncio.iscoroutinefunction(McpClient.call_tool)
