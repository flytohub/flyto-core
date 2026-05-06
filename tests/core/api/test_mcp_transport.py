"""
Tests for MCP Streamable HTTP Transport.

Tests POST /mcp, GET /mcp, DELETE /mcp endpoints.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from core.api.server import create_app
from core.api.routes.mcp import _mcp_sessions


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clear_sessions():
    _mcp_sessions.clear()
    yield
    _mcp_sessions.clear()


INIT_REQUEST = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"},
    },
}


class TestInitializeHandshake:

    def test_initialize_returns_capabilities(self, client):
        resp = client.post(
            "/mcp",
            json=INIT_REQUEST,
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["jsonrpc"] == "2.0"
        assert body["id"] == 1
        result = body["result"]
        assert "protocolVersion" in result
        assert result["serverInfo"]["name"] == "flyto-core"
        assert "tools" in result["capabilities"]

    def test_initialize_returns_session_header(self, client):
        resp = client.post(
            "/mcp",
            json=INIT_REQUEST,
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        session_id = resp.headers.get("mcp-session-id")
        assert session_id is not None
        assert len(session_id) > 10
        # Session should be stored
        assert session_id in _mcp_sessions


class TestProtocolVersionNegotiation:
    """MCP servers must echo the client's requested protocol version when supported,
    so older clients (e.g. LM Studio) don't see an unrecognized version and disconnect.
    Regression: github.com/flytohub/flyto-core/issues/16
    """

    @pytest.mark.parametrize(
        "client_version",
        ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"],
    )
    def test_supported_version_is_echoed(self, client, client_version):
        resp = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": client_version,
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["protocolVersion"] == client_version

    def test_unsupported_version_falls_back_to_server_preferred(self, client):
        from core.mcp_handler import SUPPORTED_PROTOCOL_VERSIONS

        resp = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "1999-01-01",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["protocolVersion"] == SUPPORTED_PROTOCOL_VERSIONS[0]

    def test_missing_version_falls_back_to_server_preferred(self, client):
        from core.mcp_handler import SUPPORTED_PROTOCOL_VERSIONS

        resp = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
            },
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["protocolVersion"] == SUPPORTED_PROTOCOL_VERSIONS[0]

    def test_negotiate_helper_directly(self):
        from core.mcp_handler import negotiate_protocol_version, SUPPORTED_PROTOCOL_VERSIONS

        assert negotiate_protocol_version("2024-11-05") == "2024-11-05"
        assert negotiate_protocol_version("2025-06-18") == "2025-06-18"
        assert negotiate_protocol_version("2025-11-25") == "2025-11-25"
        assert negotiate_protocol_version("bogus") == SUPPORTED_PROTOCOL_VERSIONS[0]
        assert negotiate_protocol_version(None) == SUPPORTED_PROTOCOL_VERSIONS[0]
        assert negotiate_protocol_version("") == SUPPORTED_PROTOCOL_VERSIONS[0]


class TestToolsList:

    def _init_session(self, client) -> str:
        resp = client.post(
            "/mcp",
            json=INIT_REQUEST,
            headers={"Accept": "application/json"},
        )
        return resp.headers["mcp-session-id"]

    def test_tools_list_returns_tools(self, client):
        session_id = self._init_session(client)
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers={
                "Accept": "application/json",
                "Mcp-Session-Id": session_id,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        tools = body["result"]["tools"]
        assert len(tools) == 8
        tool_names = {t["name"] for t in tools}
        assert "execute_module" in tool_names
        assert "list_modules" in tool_names

    def test_tools_list_without_session_still_works(self, client):
        """Session is optional for non-initialize requests."""
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["result"]["tools"]) == 8


class TestToolsCall:

    def test_tools_call_validate_params(self, client):
        """Test calling validate_params tool via MCP."""
        mock_class = MagicMock()
        mock_instance = MagicMock()
        mock_instance.validate_params.return_value = None
        mock_class.return_value = mock_instance

        with patch("core.modules.registry.ModuleRegistry.get", return_value=mock_class):
            resp = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "validate_params",
                        "arguments": {"module_id": "string.uppercase", "params": {"text": "hi"}},
                    },
                },
                headers={"Accept": "application/json"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 3
        result = body["result"]
        structured = result["structuredContent"]
        assert structured["valid"] is True


class TestNotifications:

    def test_notification_returns_202(self, client):
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 202

    def test_notification_in_batch_with_request(self, client):
        """Batch with notification + request: notification ignored, request returned."""
        resp = client.post(
            "/mcp",
            json=[
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 10, "method": "ping"},
            ],
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Batch response: only the ping response
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["id"] == 10


class TestSessionValidation:

    def test_invalid_session_id_returns_404(self, client):
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={
                "Accept": "application/json",
                "Mcp-Session-Id": "nonexistent-session",
            },
        )
        assert resp.status_code == 404

    def test_invalid_accept_returns_406(self, client):
        resp = client.post(
            "/mcp",
            json=INIT_REQUEST,
            headers={"Accept": "text/html"},
        )
        assert resp.status_code == 406


class TestBatchRequests:

    def test_batch_of_two_requests(self, client):
        resp = client.post(
            "/mcp",
            json=[
                {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            ],
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 2
        ids = {item["id"] for item in body}
        assert ids == {1, 2}


class TestDeleteSession:

    def test_delete_existing_session(self, client):
        # Create session
        resp = client.post(
            "/mcp",
            json=INIT_REQUEST,
            headers={"Accept": "application/json"},
        )
        session_id = resp.headers["mcp-session-id"]

        # Delete it
        resp = client.delete("/mcp", headers={"Mcp-Session-Id": session_id})
        assert resp.status_code == 200
        assert session_id not in _mcp_sessions

    def test_delete_nonexistent_session(self, client):
        resp = client.delete("/mcp", headers={"Mcp-Session-Id": "fake"})
        assert resp.status_code == 404

    def test_delete_no_session_header(self, client):
        resp = client.delete("/mcp")
        assert resp.status_code == 404


class TestGetNotAllowed:

    def test_get_returns_405(self, client):
        resp = client.get("/mcp")
        assert resp.status_code == 405


class TestParseError:

    def test_invalid_json_returns_400(self, client):
        resp = client.post(
            "/mcp",
            content=b"not json",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        assert resp.status_code == 400


class TestMCPHelpers:
    """Direct unit tests for MCP helper functions."""

    def test_is_notification_true(self):
        from core.api.routes.mcp import _is_notification
        assert _is_notification({"jsonrpc": "2.0", "method": "notifications/initialized"}) is True

    def test_is_notification_false(self):
        from core.api.routes.mcp import _is_notification
        assert _is_notification({"jsonrpc": "2.0", "id": 1, "method": "ping"}) is False

    def test_is_initialize_true(self):
        from core.api.routes.mcp import _is_initialize
        assert _is_initialize({"method": "initialize"}) is True

    def test_is_initialize_false(self):
        from core.api.routes.mcp import _is_initialize
        assert _is_initialize({"method": "tools/list"}) is False


class TestMCPEdgeCases:
    """Edge cases for MCP transport."""

    def test_empty_batch_returns_400(self, client):
        resp = client.post(
            "/mcp",
            json=[],
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == -32600

    def test_wildcard_accept_header_passes(self, client):
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"Accept": "*/*"},
        )
        assert resp.status_code == 200

    def test_batch_all_notifications(self, client):
        resp = client.post(
            "/mcp",
            json=[
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "method": "notifications/cancelled"},
            ],
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 202

    def test_tools_call_execute_module(self, client):
        """Test calling execute_module tool which returns a result."""
        resp = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "execute_module",
                    "arguments": {
                        "module_id": "math.abs",
                        "params": {"number": -99},
                    },
                },
            },
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 5
        # Should have result with content
        assert "result" in body

    def test_tools_call_list_modules(self, client):
        resp = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "list_modules",
                    "arguments": {},
                },
            },
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 6
        assert "result" in body
