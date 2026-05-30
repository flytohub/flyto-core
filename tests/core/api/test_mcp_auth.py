"""
Regression tests: fail-closed authz on the MCP Streamable HTTP transport.

Security advisory GHSA-h9f9-h6gm-wc85 — the POST /mcp JSON-RPC surface
(notably `execute_module`) was reachable with no authentication, while every
other Execution-API endpoint required the bearer token minted by `init_auth`.
These tests pin the deny-by-default posture:

  * an unauthenticated / wrongly-authenticated /mcp request is rejected
    (401/403) and the JSON-RPC dispatcher is never invoked — the module does
    NOT execute;
  * a correctly-authenticated request still works (no regression for
    legitimate MCP clients);
  * a non-loopback bind without active auth is refused at startup, not merely
    warned.

These assertions FAIL against the pre-fix code (the route had no auth
dependency and `enforce_bind_policy` did not exist) and PASS after the fix.
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from core.api.server import create_app
from core.api import security as sec
from core.api.routes.mcp import _mcp_sessions


@pytest.fixture(autouse=True)
def clear_sessions():
    _mcp_sessions.clear()
    yield
    _mcp_sessions.clear()


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    """Raw client — sends NO Authorization header by default."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def token():
    return sec._active_token


EXECUTE_MODULE_CALL = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "execute_module",
        # math.abs is harmless; the point is the request must never reach dispatch.
        "arguments": {"module_id": "math.abs", "params": {"number": -1}},
    },
}


class TestMcpTransportRequiresAuth:
    """The /mcp transport must fail closed: no token => no dispatch, no execution."""

    def test_execute_module_without_token_is_denied_and_never_dispatched(self, client):
        with patch(
            "core.api.routes.mcp.handle_jsonrpc_request", new_callable=AsyncMock
        ) as dispatch:
            resp = client.post(
                "/mcp",
                json=EXECUTE_MODULE_CALL,
                headers={"Accept": "application/json"},
            )
        assert resp.status_code in (401, 403), resp.text
        # Complete mediation: the JSON-RPC dispatcher (and execute_module) must
        # never run for an unauthenticated caller.
        dispatch.assert_not_called()

    def test_invalid_token_is_denied_and_never_dispatched(self, client):
        with patch(
            "core.api.routes.mcp.handle_jsonrpc_request", new_callable=AsyncMock
        ) as dispatch:
            resp = client.post(
                "/mcp",
                json=EXECUTE_MODULE_CALL,
                headers={
                    "Accept": "application/json",
                    "Authorization": "Bearer not-the-real-token",
                },
            )
        assert resp.status_code in (401, 403), resp.text
        dispatch.assert_not_called()

    def test_initialize_without_token_is_denied(self, client):
        """Deny-by-default covers the whole transport, including `initialize`."""
        resp = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
            },
            headers={"Accept": "application/json"},
        )
        assert resp.status_code in (401, 403), resp.text

    def test_delete_session_without_token_is_denied(self, client):
        resp = client.delete("/mcp", headers={"Mcp-Session-Id": "anything"})
        assert resp.status_code in (401, 403), resp.text


class TestMcpTransportAllowsAuthenticatedClients:
    """No regression: a request carrying the correct bearer token still works."""

    def test_initialize_with_valid_token_succeeds(self, client, token):
        resp = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
            },
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["result"]["serverInfo"]["name"] == "flyto-core"

    def test_execute_module_with_valid_token_is_dispatched(self, client, token):
        resp = client.post(
            "/mcp",
            json=EXECUTE_MODULE_CALL,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == 1
        assert "result" in body


class TestBindPolicy:
    """A non-loopback bind without active auth must be refused at startup."""

    def setup_method(self):
        self._saved = sec._active_token

    def teardown_method(self):
        sec._active_token = self._saved

    def test_nonloopback_without_auth_is_refused(self):
        from core.api.security import enforce_bind_policy

        sec._active_token = None
        with pytest.raises(RuntimeError):
            enforce_bind_policy("0.0.0.0")

    def test_loopback_without_auth_is_allowed(self):
        from core.api.security import enforce_bind_policy

        sec._active_token = None
        # Loopback binds are the safe default and must not be refused.
        enforce_bind_policy("127.0.0.1")
        enforce_bind_policy("::1")
        enforce_bind_policy("localhost")

    def test_nonloopback_with_active_auth_is_allowed(self):
        from core.api.security import enforce_bind_policy

        sec._active_token = "an-active-token"
        enforce_bind_policy("0.0.0.0")

    # FLYA-32 hardening: an empty/wildcard host means "all interfaces"
    # (INADDR_ANY / in6addr_any), not loopback. Previously "" lived in
    # _LOOPBACK_HOSTS, so enforce_bind_policy("") returned early and skipped
    # the auth check — a fail-open in the bind guard. These pin the fix.
    @pytest.mark.parametrize("host", ["", " ", "0.0.0.0", "::", "*"])
    def test_wildcard_host_without_auth_is_refused(self, host):
        from core.api.security import enforce_bind_policy

        sec._active_token = None
        with pytest.raises(RuntimeError):
            enforce_bind_policy(host)

    @pytest.mark.parametrize("host", ["", "0.0.0.0", "::", "*"])
    def test_wildcard_host_with_active_auth_is_allowed(self, host):
        from core.api.security import enforce_bind_policy

        sec._active_token = "an-active-token"
        # With auth active a wildcard bind is the operator's explicit choice.
        enforce_bind_policy(host)


class TestMcpFailsClosedWhenAuthUninitialized:
    """FLYA-32 hardening: the MCP exec surface must fail closed even when auth
    was never initialized (`_active_token is None`). Previously `require_auth`
    returned early ("pass through") in that state — a latent fail-open on the
    shared dependency that would have left module execution wide open.
    """

    def setup_method(self):
        self._saved = sec._active_token

    def teardown_method(self):
        sec._active_token = self._saved

    def test_execute_module_with_uninitialized_auth_is_denied(self, app):
        # create_app() ran init_auth(); simulate the uninitialized/misconfigured
        # state by clearing the active token after construction.
        sec._active_token = None
        with TestClient(app) as client:
            with patch(
                "core.api.routes.mcp.handle_jsonrpc_request", new_callable=AsyncMock
            ) as dispatch:
                resp = client.post(
                    "/mcp",
                    json=EXECUTE_MODULE_CALL,
                    headers={
                        "Accept": "application/json",
                        # Even a "matching" bearer must not succeed: there is no
                        # active token to match against, so deny outright.
                        "Authorization": "Bearer anything",
                    },
                )
        # Fail closed: refused (not 2xx) and the dispatcher never runs.
        assert resp.status_code >= 400, resp.text
        assert resp.status_code not in (200,), resp.text
        dispatch.assert_not_called()
