# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Surface tests for the capability manifest: MCP tool, REST read, REST refresh.

`tests/core/test_capability_manifest.py` pins the *document* — determinism,
ordering, hashing, isolation. This file pins the three ways a client reaches
it, and in particular the auth split that makes the pair safe to expose: the
read is open, the rebuild is not.
"""

import json

import pytest
from fastapi.testclient import TestClient

from core.api import security as sec
from core.api.server import create_app
from core.capability_manifest import MANIFEST_SCHEMA, compute_manifest_hash
from core.mcp_handler import TOOLS, _handle_tool_call


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def anon(app):
    """Client that sends NO Authorization header."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def authed(app):
    """Client carrying the token `init_auth` minted during `create_app`."""
    with TestClient(
        app, headers={"Authorization": f"Bearer {sec._active_token}"}
    ) as c:
        yield c


def _assert_is_manifest(body):
    """Shape assertions shared by every surface — one document, one contract."""
    assert body["schema"] == MANIFEST_SCHEMA
    for key in (
        "registry_version",
        "core_version",
        "module_count",
        "modules",
        "capabilities",
        "categories",
        "plugins",
        "hash",
    ):
        assert key in body, f"missing {key}"
    assert body["module_count"] == len(body["modules"])
    assert body["modules"] == sorted(body["modules"])
    # The hash a client receives must verify against the body it arrived with,
    # or comparing hashes across hosts proves nothing.
    assert compute_manifest_hash(body) == body["hash"]


# ---------------------------------------------------------------------------
# MCP tool
# ---------------------------------------------------------------------------


def test_manifest_tool_is_registered_and_read_only():
    """The tool is advertised, takes no arguments, and is annotated read-only."""
    tool = next(t for t in TOOLS if t["name"] == "get_capability_manifest")

    assert tool["inputSchema"]["properties"] == {}
    assert "required" not in tool["inputSchema"]
    assert tool["annotations"]["readOnlyHint"] is True
    assert tool["annotations"]["destructiveHint"] is False
    assert tool["annotations"]["idempotentHint"] is True


async def _call_manifest_tool(request_id=1, arguments=None, modern=False):
    """Dispatch `get_capability_manifest` the way the transport does."""
    return await _handle_tool_call(
        request_id,
        {"name": "get_capability_manifest", "arguments": arguments or {}},
        modern=modern,
        browser_sessions={},
        debugger_sessions={},
        session_activity={},
    )


def _mcp_payload(response):
    """Unwrap the JSON-RPC envelope and return the tool's structured result."""
    assert "error" not in response, response
    body = response["result"]
    # `modern=True` wraps the body further; both eras carry structuredContent.
    if "structuredContent" not in body and "content" not in body:
        body = next(v for v in body.values() if isinstance(v, dict))
    assert body.get("isError") is not True, body
    if "structuredContent" in body:
        return body["structuredContent"]
    return json.loads(body["content"][0]["text"])


async def test_mcp_dispatch_returns_the_manifest():
    """`tools/call` for the manifest reaches the handler and returns the doc."""
    response = await _call_manifest_tool(request_id=1)

    assert response["id"] == 1
    _assert_is_manifest(_mcp_payload(response))


async def test_mcp_dispatch_ignores_stray_arguments():
    """A client passing arguments to a no-arg tool still gets a valid answer."""
    response = await _call_manifest_tool(
        request_id=2, arguments={"unexpected": True}
    )

    _assert_is_manifest(_mcp_payload(response))


async def test_mcp_dispatch_is_not_an_error_result():
    """The tool reports success, so clients do not treat the doc as a failure."""
    response = await _call_manifest_tool(request_id=3)

    assert response["result"].get("isError") is False


async def test_mcp_text_and_structured_content_agree():
    """The JSON text block and structuredContent are the same document."""
    response = await _call_manifest_tool(request_id=4)
    body = response["result"]

    assert json.loads(body["content"][0]["text"]) == body["structuredContent"]


# ---------------------------------------------------------------------------
# GET /v1/capabilities — open, read-only
# ---------------------------------------------------------------------------


def test_rest_get_returns_manifest_without_auth(anon):
    """The read is deliberately open, like /v1/modules and /v1/info.

    A client has to learn which modules exist before it can meaningfully
    authenticate a call to execute one.
    """
    resp = anon.get("/v1/capabilities")

    assert resp.status_code == 200
    _assert_is_manifest(resp.json())


def test_rest_get_is_stable_across_calls(anon):
    """Two reads with no refresh between them are byte-identical."""
    first = anon.get("/v1/capabilities").json()
    second = anon.get("/v1/capabilities").json()

    assert first == second
    assert first["hash"] == second["hash"]


async def test_rest_get_agrees_with_the_mcp_tool(anon):
    """Both surfaces serve the same document — one catalog, two doors."""
    rest = anon.get("/v1/capabilities").json()
    mcp = _mcp_payload(await _call_manifest_tool(request_id=5))

    assert rest["hash"] == mcp["hash"]
    assert rest == mcp


def test_rest_get_response_carries_no_volatile_detail(anon):
    """No timestamps, paths, or host identity cross the wire."""
    blob = anon.get("/v1/capabilities").text

    for forbidden in (
        "loaded_at",
        "created_at",
        "timestamp",
        "entry_point",
        "/Users/",
        "/home/",
        "secret",
        "password",
        "hostname",
    ):
        assert forbidden not in blob, f"response leaked {forbidden!r}"


# ---------------------------------------------------------------------------
# POST /v1/capabilities/refresh — authenticated
# ---------------------------------------------------------------------------


def test_refresh_requires_auth(anon):
    """Unauthenticated refresh is refused.

    The rebuild clears and re-discovers the process-wide registry. Left open it
    is both a state change an anonymous caller should not command and a cheap
    way to churn a server, so it is gated while the read stays open.
    """
    resp = anon.post("/v1/capabilities/refresh")

    assert resp.status_code in (401, 403), resp.text


def test_refresh_rejects_a_wrong_token(app):
    """A bad bearer token is rejected, not merely a missing one."""
    with TestClient(app, headers={"Authorization": "Bearer not-the-token"}) as c:
        resp = c.post("/v1/capabilities/refresh")

    assert resp.status_code in (401, 403), resp.text


def test_unauthorized_refresh_does_not_rebuild(anon, authed):
    """A refused refresh must have no side effect on the served document."""
    before = authed.get("/v1/capabilities").json()

    assert anon.post("/v1/capabilities/refresh").status_code in (401, 403)

    after = authed.get("/v1/capabilities").json()
    assert after == before


def test_authenticated_refresh_returns_a_manifest(authed):
    """The happy path rebuilds and answers with the same document contract."""
    resp = authed.post("/v1/capabilities/refresh")

    assert resp.status_code == 200, resp.text
    _assert_is_manifest(resp.json())


def test_refresh_result_matches_the_next_read(authed):
    """What refresh returns is what subsequent reads serve — no stale cache."""
    refreshed = authed.post("/v1/capabilities/refresh").json()
    read = authed.get("/v1/capabilities").json()

    assert refreshed["hash"] == read["hash"]
    assert refreshed == read


def test_refresh_is_not_exposed_as_a_get(anon):
    """The rebuild is POST-only; a GET must not slip past the auth dependency."""
    resp = anon.get("/v1/capabilities/refresh")

    assert resp.status_code in (404, 405), resp.text
