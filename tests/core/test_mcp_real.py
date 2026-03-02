"""
MCP Real Integration Tests — Zero Mocks

Tests the full MCP stack with real module execution:
  1a. Handler layer → direct execute_module / validate_params
  1b. list_modules / search_modules / get_module_info (catalog)
  1c. HTTP transport → TestClient → POST /mcp → real dispatch
  1d. STDIO subprocess → JSON-RPC over stdin/stdout
"""

import asyncio
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure modules are registered BEFORE any handler/app import
# ---------------------------------------------------------------------------
from core.modules import atomic  # noqa: F401  — triggers 400+ module registration

from core.mcp_handler import (
    execute_module,
    validate_params,
    list_modules,
    search_modules,
    get_module_info,
    get_module_examples,
    handle_jsonrpc_request,
    TOOLS,
)

REPO_ROOT = Path(__file__).parent.parent.parent
EXPECTED_TOOL_COUNT = 8  # list_modules, search_modules, get_module_info, get_module_examples, execute_module, validate_params, list_recipes, run_recipe


# ===================================================================
# 1a. Handler Layer — Direct Real Module Execution
# ===================================================================

class TestHandlerExecuteModule:
    """Direct handler calls — no HTTP, no subprocess, no mock."""

    @pytest.mark.asyncio
    async def test_string_uppercase(self):
        """execute_module('string.uppercase') returns HELLO."""
        result = await execute_module("string.uppercase", {"text": "hello"})
        assert result.get("ok") is True, f"Expected ok=True, got: {result}"
        assert result["data"]["result"] == "HELLO"

    @pytest.mark.asyncio
    async def test_string_lowercase(self):
        """execute_module('string.lowercase') returns hello."""
        result = await execute_module("string.lowercase", {"text": "HELLO"})
        assert result.get("ok") is True
        assert result["data"]["result"] == "hello"

    @pytest.mark.asyncio
    async def test_module_not_found(self):
        """Non-existent module returns ok=False."""
        result = await execute_module("nonexistent.module_xyz", {"x": 1})
        assert result.get("ok") is False
        assert "not found" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_missing_required_param(self):
        """Missing required param returns ok=False."""
        result = await execute_module("string.uppercase", {})
        assert result.get("ok") is False


class TestHandlerValidateParams:
    """validate_params — real module schema validation."""

    def test_valid_params(self):
        result = validate_params("string.uppercase", {"text": "hi"})
        assert result["valid"] is True
        assert result["module_id"] == "string.uppercase"

    def test_invalid_module(self):
        result = validate_params("nonexistent.xyz", {"text": "hi"})
        assert result["valid"] is False
        assert len(result["errors"]) > 0


# ===================================================================
# 1b. Catalog — list / search / info
# ===================================================================

class TestCatalog:
    """Catalog functions using real ModuleRegistry data."""

    def test_list_modules_all(self):
        result = list_modules()
        assert "error" not in result
        assert result["total_categories"] > 30
        cat_names = [c["category"] for c in result["categories"]]
        assert "string" in cat_names
        assert "browser" in cat_names

    def test_list_modules_string_category(self):
        result = list_modules(category="string")
        assert "error" not in result
        module_ids = [m["module_id"] for m in result["modules"]]
        assert "string.uppercase" in module_ids

    def test_list_modules_bad_category(self):
        result = list_modules(category="nonexistent_cat_xyz")
        assert "error" in result

    def test_search_modules_uppercase(self):
        result = search_modules("uppercase")
        assert "error" not in result
        assert result["total"] >= 1
        ids = [r["module_id"] for r in result["results"]]
        assert "string.uppercase" in ids

    def test_get_module_info(self):
        result = get_module_info("string.uppercase")
        assert "error" not in result
        assert "params_schema" in result

    def test_get_module_info_not_found(self):
        result = get_module_info("nonexistent.xyz")
        assert "error" in result

    def test_get_module_examples(self):
        result = get_module_examples("string.uppercase")
        assert "error" not in result
        assert "examples" in result


# ===================================================================
# 1c. HTTP Transport — TestClient → POST /mcp
# ===================================================================

class TestHTTPTransport:
    """Real HTTP requests through FastAPI TestClient, real module execution."""

    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient
        from core.api.server import create_app

        app = create_app()
        return TestClient(app)

    def _mcp_call(self, client, tool_name: str, arguments: dict, req_id: int = 1) -> dict:
        """Send tools/call via POST /mcp and return structuredContent."""
        body = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": req_id,
        }
        resp = client.post("/mcp", json=body)
        assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "error" not in data, f"JSON-RPC error: {data.get('error')}"
        return data["result"]["structuredContent"]

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_initialize(self, client):
        body = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0.1"},
            },
            "id": 1,
        }
        resp = client.post("/mcp", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["serverInfo"]["name"] == "flyto-core"

    def test_tools_list(self, client):
        body = {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1}
        resp = client.post("/mcp", json=body)
        data = resp.json()
        tools = data["result"]["tools"]
        assert len(tools) == EXPECTED_TOOL_COUNT
        names = sorted(t["name"] for t in tools)
        assert "execute_module" in names
        assert "validate_params" in names

    def test_execute_module_via_http(self, client):
        result = self._mcp_call(client, "execute_module", {
            "module_id": "string.uppercase",
            "params": {"text": "hello"},
        })
        assert result["ok"] is True
        assert result["data"]["result"] == "HELLO"

    def test_validate_params_via_http(self, client):
        result = self._mcp_call(client, "validate_params", {
            "module_id": "string.uppercase",
            "params": {"text": "test"},
        })
        assert result["valid"] is True

    def test_list_modules_via_http(self, client):
        result = self._mcp_call(client, "list_modules", {})
        assert result["total_categories"] > 30

    def test_search_modules_via_http(self, client):
        result = self._mcp_call(client, "search_modules", {"query": "uppercase"})
        assert result["total"] >= 1

    def test_unknown_tool_via_http(self, client):
        body = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "nonexistent_tool_xyz", "arguments": {}},
            "id": 1,
        }
        resp = client.post("/mcp", json=body)
        data = resp.json()
        assert data.get("error", {}).get("code") == -32601


# ===================================================================
# 1d. STDIO Subprocess E2E
# ===================================================================

def _send_jsonrpc(proc, method: str, params: dict = None, req_id: int = 1):
    """Write a JSON-RPC request line to the subprocess stdin."""
    msg = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        msg["params"] = params
    line = json.dumps(msg) + "\n"
    proc.stdin.write(line.encode())
    proc.stdin.flush()


def _read_response(proc, timeout: float = 10.0) -> dict:
    """Read one JSON-RPC response line from stdout with a timeout."""
    result = {}
    exc = []

    def _reader():
        try:
            raw = proc.stdout.readline()
            if raw:
                result["data"] = json.loads(raw.decode().strip())
        except Exception as e:
            exc.append(e)

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if t.is_alive():
        raise TimeoutError(f"No response within {timeout}s")
    if exc:
        raise exc[0]
    if "data" not in result:
        stderr_out = ""
        if proc.stderr:
            try:
                stderr_out = proc.stderr.read(4096).decode(errors="replace")
            except Exception:
                pass
        raise RuntimeError(f"Empty response from MCP server. stderr: {stderr_out}")
    return result["data"]


_next_id = 100


def _call(proc, method: str, params: dict = None, timeout: float = 10.0) -> dict:
    """Send a request and return the parsed response."""
    global _next_id
    rid = _next_id
    _next_id += 1
    _send_jsonrpc(proc, method, params, req_id=rid)
    resp = _read_response(proc, timeout=timeout)
    assert resp.get("id") == rid, f"ID mismatch: expected {rid}, got {resp.get('id')}"
    return resp


@pytest.fixture(scope="module")
def mcp_server():
    """Start the real MCP server subprocess once for the module."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")

    proc = subprocess.Popen(
        [sys.executable, "-m", "core.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO_ROOT / "src"),
        env=env,
    )

    # Initialize — wait up to 30s (400+ module imports take time)
    _send_jsonrpc(proc, "initialize", {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "0.1"},
    }, req_id=0)

    try:
        resp = _read_response(proc, timeout=30.0)
        assert resp.get("id") == 0, f"Unexpected init response: {resp}"
    except Exception:
        proc.terminate()
        proc.wait(timeout=5)
        stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        raise RuntimeError(f"MCP server failed to initialize. stderr:\n{stderr}")

    # Send notifications/initialized
    _send_jsonrpc(proc, "notifications/initialized", {}, req_id=None)

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


class TestSTDIOSubprocess:
    """Full E2E through real subprocess — JSON-RPC over stdin/stdout."""

    def test_tools_list_count(self, mcp_server):
        resp = _call(mcp_server, "tools/list")
        tools = resp["result"]["tools"]
        assert len(tools) == EXPECTED_TOOL_COUNT

    def test_execute_module_string_uppercase(self, mcp_server):
        resp = _call(mcp_server, "tools/call", {
            "name": "execute_module",
            "arguments": {
                "module_id": "string.uppercase",
                "params": {"text": "hello"},
            },
        }, timeout=15.0)
        assert "error" not in resp, f"Got error: {resp.get('error')}"
        content = resp["result"]["structuredContent"]
        assert content["ok"] is True
        assert content["data"]["result"] == "HELLO"

    def test_validate_params_via_stdio(self, mcp_server):
        resp = _call(mcp_server, "tools/call", {
            "name": "validate_params",
            "arguments": {
                "module_id": "string.uppercase",
                "params": {"text": "x"},
            },
        })
        content = resp["result"]["structuredContent"]
        assert content["valid"] is True

    def test_list_modules_via_stdio(self, mcp_server):
        resp = _call(mcp_server, "tools/call", {
            "name": "list_modules",
            "arguments": {},
        })
        content = resp["result"]["structuredContent"]
        assert content["total_categories"] > 30

    def test_search_modules_via_stdio(self, mcp_server):
        resp = _call(mcp_server, "tools/call", {
            "name": "search_modules",
            "arguments": {"query": "uppercase"},
        })
        content = resp["result"]["structuredContent"]
        assert content["total"] >= 1

    def test_unknown_tool_returns_error(self, mcp_server):
        resp = _call(mcp_server, "tools/call", {
            "name": "nonexistent_tool_xyz",
            "arguments": {},
        })
        assert resp.get("error", {}).get("code") == -32601

    def test_unknown_method_returns_error(self, mcp_server):
        resp = _call(mcp_server, "evil/method", {"foo": "bar"})
        assert resp.get("error", {}).get("code") == -32601

    def test_ping(self, mcp_server):
        resp = _call(mcp_server, "ping")
        assert resp["result"] == {}
