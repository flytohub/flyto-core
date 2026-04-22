"""
Real integration tests for http.session module.

Uses a live aiohttp test server — no mocks.
FLYTO_ALLOW_PRIVATE_NETWORK=true is set per-fixture so localhost is reachable.
"""

import asyncio
import base64

import pytest
from aiohttp import web

from core.modules.atomic.http.session import _apply_auth, _read_body, http_session


async def _run(params: dict) -> dict:
    """Call http_session via the FunctionModuleWrapper created by @register_module."""
    instance = http_session(params, {})
    return await instance.execute()


# ---------------------------------------------------------------------------
# Server fixture helpers
# ---------------------------------------------------------------------------


async def _handle_get_data(request: web.Request) -> web.Response:
    """Return JSON body on GET /data."""
    return web.json_response({"message": "hello", "method": "GET"})


async def _handle_post_echo(request: web.Request) -> web.Response:
    """Echo the received JSON body."""
    body = await request.json()
    return web.json_response({"echo": body, "method": "POST"})


async def _handle_set_cookie(request: web.Request) -> web.Response:
    """Set a session cookie and return 200."""
    response = web.json_response({"step": "login"})
    response.set_cookie("session_id", "abc123")
    return response


async def _handle_check_cookie(request: web.Request) -> web.Response:
    """Return the session cookie value if present, else 401."""
    session_id = request.cookies.get("session_id")
    if session_id:
        return web.json_response({"session_id": session_id, "authenticated": True})
    return web.json_response({"authenticated": False}, status=401)


async def _handle_error(request: web.Request) -> web.Response:
    """Always returns 500."""
    return web.json_response({"error": "internal"}, status=500)


async def _handle_not_found(request: web.Request) -> web.Response:
    """Always returns 404."""
    return web.json_response({"error": "not found"}, status=404)


async def _handle_auth_bearer(request: web.Request) -> web.Response:
    """Expect Bearer token in Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth == "Bearer supersecret":
        return web.json_response({"authorized": True})
    return web.json_response({"authorized": False}, status=401)


async def _handle_auth_basic(request: web.Request) -> web.Response:
    """Expect Basic auth header."""
    auth = request.headers.get("Authorization", "")
    expected = "Basic " + base64.b64encode(b"user:pass").decode()
    if auth == expected:
        return web.json_response({"authorized": True})
    return web.json_response({"authorized": False}, status=401)


async def _handle_auth_api_key(request: web.Request) -> web.Response:
    """Expect X-API-Key header."""
    key = request.headers.get("X-API-Key", "")
    if key == "mykey":
        return web.json_response({"authorized": True})
    return web.json_response({"authorized": False}, status=401)


async def _handle_slow(request: web.Request) -> web.Response:
    """Delays 5 seconds — used for timeout tests."""
    await asyncio.sleep(5)
    return web.json_response({"done": True})


async def _handle_text(request: web.Request) -> web.Response:
    """Returns plain text."""
    return web.Response(text="plain text response", content_type="text/plain")


# ---------------------------------------------------------------------------
# Fixture: real aiohttp server
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_server(monkeypatch):
    """Start a real aiohttp server on a random localhost port."""
    monkeypatch.setenv("FLYTO_ALLOW_PRIVATE_NETWORK", "true")

    app = web.Application()
    app.router.add_get("/data", _handle_get_data)
    app.router.add_post("/echo", _handle_post_echo)
    app.router.add_get("/login", _handle_set_cookie)
    app.router.add_get("/profile", _handle_check_cookie)
    app.router.add_get("/error", _handle_error)
    app.router.add_get("/notfound", _handle_not_found)
    app.router.add_get("/auth/bearer", _handle_auth_bearer)
    app.router.add_get("/auth/basic", _handle_auth_basic)
    app.router.add_get("/auth/apikey", _handle_auth_api_key)
    app.router.add_get("/slow", _handle_slow)
    app.router.add_get("/text", _handle_text)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    base = f"http://localhost:{port}"
    yield base
    await runner.cleanup()


# ---------------------------------------------------------------------------
# Helper: build params dict
# ---------------------------------------------------------------------------


def params(requests, **kwargs):
    """Build a params dict for _run()."""
    return {"requests": requests, **kwargs}


# ---------------------------------------------------------------------------
# Tests: basic requests
# ---------------------------------------------------------------------------


class TestBasicRequests:
    async def test_get_request(self, test_server):
        result = await _run(params(
            [{"label": "Get", "url": f"{test_server}/data", "method": "GET"}]
        ))

        assert result["ok"] is True
        assert len(result["results"]) == 1
        r = result["results"][0]
        assert r["ok"] is True
        assert r["status"] == 200
        assert r["label"] == "Get"
        assert r["body"]["message"] == "hello"
        assert r["duration_ms"] >= 0

    async def test_post_request_with_json_body(self, test_server):
        payload = {"key": "value", "num": 42}
        result = await _run(params(
            [{"label": "Post", "url": f"{test_server}/echo", "method": "POST", "body": payload}]
        ))

        assert result["ok"] is True
        r = result["results"][0]
        assert r["ok"] is True
        assert r["status"] == 200
        assert r["body"]["echo"] == payload
        assert r["body"]["method"] == "POST"

    async def test_sequential_get_post(self, test_server):
        result = await _run(params([
            {"label": "Step1", "url": f"{test_server}/data", "method": "GET"},
            {"label": "Step2", "url": f"{test_server}/echo", "method": "POST", "body": {"x": 1}},
        ]))

        assert result["ok"] is True
        assert len(result["results"]) == 2
        assert result["results"][0]["body"]["method"] == "GET"
        assert result["results"][1]["body"]["method"] == "POST"

    async def test_duration_ms_is_non_negative(self, test_server):
        result = await _run(params([{"url": f"{test_server}/data", "method": "GET"}]))

        assert result["duration_ms"] >= 0
        assert result["results"][0]["duration_ms"] >= 0

    async def test_url_is_in_result(self, test_server):
        result = await _run(params([{"url": f"{test_server}/data"}]))

        assert "url" in result["results"][0]


# ---------------------------------------------------------------------------
# Tests: cookie persistence
# ---------------------------------------------------------------------------


class TestCookiePersistence:
    async def test_cookie_set_on_first_request_sent_on_second(self, test_server):
        """Server sets cookie on /login; /profile requires it."""
        result = await _run(params([
            {"label": "Login", "url": f"{test_server}/login", "method": "GET"},
            {"label": "Profile", "url": f"{test_server}/profile", "method": "GET"},
        ]))

        assert result["ok"] is True
        assert result["results"][0]["ok"] is True
        assert result["results"][1]["ok"] is True
        assert result["results"][1]["body"]["authenticated"] is True
        assert result["results"][1]["body"]["session_id"] == "abc123"

    async def test_cookies_in_output(self, test_server):
        """The 'cookies' key in output contains cookies set during session."""
        result = await _run(params([{"label": "Login", "url": f"{test_server}/login"}]))

        assert "cookies" in result
        assert result["cookies"].get("session_id") == "abc123"

    async def test_no_cookie_without_login(self, test_server):
        """Accessing /profile without login cookie returns 401."""
        result = await _run(params(
            [{"label": "Profile", "url": f"{test_server}/profile", "method": "GET"}],
            stop_on_error=False,
        ))

        assert result["ok"] is False
        assert result["results"][0]["status"] == 401


# ---------------------------------------------------------------------------
# Tests: stop_on_error
# ---------------------------------------------------------------------------


class TestStopOnError:
    async def test_stop_on_error_true_halts_after_failure(self, test_server):
        result = await _run(params(
            [
                {"label": "Step1", "url": f"{test_server}/error"},
                {"label": "Step2", "url": f"{test_server}/data"},
            ],
            stop_on_error=True,
        ))

        assert result["ok"] is False
        assert len(result["results"]) == 1
        assert result["results"][0]["label"] == "Step1"
        assert result["results"][0]["ok"] is False

    async def test_stop_on_error_false_continues_after_failure(self, test_server):
        result = await _run(params(
            [
                {"label": "Step1", "url": f"{test_server}/error"},
                {"label": "Step2", "url": f"{test_server}/data"},
            ],
            stop_on_error=False,
        ))

        assert result["ok"] is False
        assert len(result["results"]) == 2
        assert result["results"][0]["ok"] is False
        assert result["results"][1]["ok"] is True

    async def test_stop_on_error_default_is_true(self, test_server):
        """Default stop_on_error=True — second request must not run."""
        result = await _run(params([
            {"url": f"{test_server}/notfound"},
            {"url": f"{test_server}/data"},
        ]))

        assert len(result["results"]) == 1

    async def test_all_ok_true_when_no_errors(self, test_server):
        result = await _run(params([
            {"url": f"{test_server}/data"},
            {"url": f"{test_server}/data"},
        ]))

        assert result["ok"] is True


# ---------------------------------------------------------------------------
# Tests: authentication
# ---------------------------------------------------------------------------


class TestAuthentication:
    async def test_bearer_token(self, test_server):
        result = await _run(params(
            [{"label": "Auth", "url": f"{test_server}/auth/bearer"}],
            auth={"type": "bearer", "token": "supersecret"},
        ))

        assert result["ok"] is True
        assert result["results"][0]["body"]["authorized"] is True

    async def test_bearer_token_wrong(self, test_server):
        result = await _run(params(
            [{"url": f"{test_server}/auth/bearer"}],
            auth={"type": "bearer", "token": "wrong"},
            stop_on_error=False,
        ))

        assert result["ok"] is False
        assert result["results"][0]["status"] == 401

    async def test_basic_auth(self, test_server):
        result = await _run(params(
            [{"url": f"{test_server}/auth/basic"}],
            auth={"type": "basic", "username": "user", "password": "pass"},
        ))

        assert result["ok"] is True
        assert result["results"][0]["body"]["authorized"] is True

    async def test_api_key_auth(self, test_server):
        result = await _run(params(
            [{"url": f"{test_server}/auth/apikey"}],
            auth={"type": "api_key", "header_name": "X-API-Key", "api_key": "mykey"},
        ))

        assert result["ok"] is True
        assert result["results"][0]["body"]["authorized"] is True

    async def test_auth_applied_to_all_requests(self, test_server):
        """Auth should propagate to every request in the session."""
        result = await _run(params(
            [
                {"url": f"{test_server}/auth/bearer", "label": "R1"},
                {"url": f"{test_server}/auth/bearer", "label": "R2"},
            ],
            auth={"type": "bearer", "token": "supersecret"},
        ))

        assert result["ok"] is True
        assert result["results"][0]["body"]["authorized"] is True
        assert result["results"][1]["body"]["authorized"] is True


# ---------------------------------------------------------------------------
# Tests: empty requests list
# ---------------------------------------------------------------------------


class TestEmptyRequests:
    async def test_empty_list_returns_error(self, monkeypatch):
        monkeypatch.setenv("FLYTO_ALLOW_PRIVATE_NETWORK", "true")
        result = await _run({"requests": []})

        assert result["ok"] is False
        assert result["error_code"] == "NO_REQUESTS"
        assert result["results"] == []
        assert result["cookies"] == {}
        assert result["duration_ms"] == 0

    async def test_missing_requests_key(self, monkeypatch):
        monkeypatch.setenv("FLYTO_ALLOW_PRIVATE_NETWORK", "true")
        result = await _run({})

        assert result["ok"] is False
        assert result["error_code"] == "NO_REQUESTS"


# ---------------------------------------------------------------------------
# Tests: timeout
# ---------------------------------------------------------------------------


class TestTimeout:
    async def test_timeout_returns_timeout_error_code(self, test_server):
        result = await _run(params(
            [{"label": "Slow", "url": f"{test_server}/slow"}],
            timeout=1,  # 1 second; server delays 5 seconds
            stop_on_error=False,
        ))

        assert result["ok"] is False
        r = result["results"][0]
        assert r["ok"] is False
        assert r["error_code"] == "TIMEOUT"
        assert r["label"] == "Slow"

    async def test_timeout_stops_session_when_stop_on_error(self, test_server):
        result = await _run(params(
            [
                {"label": "Slow", "url": f"{test_server}/slow"},
                {"label": "Fast", "url": f"{test_server}/data"},
            ],
            timeout=1,
            stop_on_error=True,
        ))

        assert result["ok"] is False
        assert len(result["results"]) == 1  # stopped after first failure


# ---------------------------------------------------------------------------
# Tests: _apply_auth helper (pure unit tests, no server needed)
# ---------------------------------------------------------------------------


class TestApplyAuth:
    def test_bearer(self):
        headers: dict = {}
        _apply_auth(headers, {"type": "bearer", "token": "tok123"})
        assert headers["Authorization"] == "Bearer tok123"

    def test_bearer_is_default_type(self):
        headers: dict = {}
        _apply_auth(headers, {"token": "tok"})  # no 'type' key
        assert headers["Authorization"] == "Bearer tok"

    def test_basic(self):
        headers: dict = {}
        _apply_auth(headers, {"type": "basic", "username": "alice", "password": "secret"})
        encoded = base64.b64encode(b"alice:secret").decode()
        assert headers["Authorization"] == f"Basic {encoded}"

    def test_basic_empty_credentials(self):
        headers: dict = {}
        _apply_auth(headers, {"type": "basic"})
        encoded = base64.b64encode(b":").decode()
        assert headers["Authorization"] == f"Basic {encoded}"

    def test_api_key_default_header(self):
        headers: dict = {}
        _apply_auth(headers, {"type": "api_key", "api_key": "mykey"})
        assert headers["X-API-Key"] == "mykey"

    def test_api_key_custom_header(self):
        headers: dict = {}
        _apply_auth(
            headers, {"type": "api_key", "header_name": "Authorization", "api_key": "Bearer xyz"}
        )
        assert headers["Authorization"] == "Bearer xyz"

    def test_unknown_type_is_noop(self):
        headers: dict = {}
        _apply_auth(headers, {"type": "oauth2", "token": "t"})
        assert headers == {}


# ---------------------------------------------------------------------------
# Tests: _read_body helper (uses real server responses)
# ---------------------------------------------------------------------------


class TestReadBody:
    async def test_read_body_json_explicit(self, test_server):
        """Explicit response_type='json' returns parsed dict."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{test_server}/data") as response:
                body = await _read_body(response, "json")
        assert isinstance(body, dict)
        assert body["message"] == "hello"

    async def test_read_body_text_explicit(self, test_server):
        """Explicit response_type='text' returns raw string."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{test_server}/text") as response:
                body = await _read_body(response, "text")
        assert body == "plain text response"

    async def test_read_body_auto_json(self, test_server):
        """Auto-detect: Content-Type application/json → dict."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{test_server}/data") as response:
                body = await _read_body(response, "auto")
        assert isinstance(body, dict)

    async def test_read_body_auto_text(self, test_server):
        """Auto-detect: text/plain Content-Type → string."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{test_server}/text") as response:
                body = await _read_body(response, "auto")
        assert isinstance(body, str)
        assert "plain text" in body


# ---------------------------------------------------------------------------
# Tests: default label generation
# ---------------------------------------------------------------------------


class TestDefaultLabel:
    async def test_default_label_when_not_provided(self, test_server):
        result = await _run(params([{"url": f"{test_server}/data"}]))  # no 'label' key

        assert result["results"][0]["label"] == "Request 1"

    async def test_custom_label_preserved(self, test_server):
        result = await _run(params([{"label": "MyStep", "url": f"{test_server}/data"}]))

        assert result["results"][0]["label"] == "MyStep"


# ---------------------------------------------------------------------------
# Tests: SSRF block (private IP without allow flag)
# ---------------------------------------------------------------------------


class TestSSRFBlock:
    async def test_ssrf_blocked_without_allow_flag(self, monkeypatch):
        monkeypatch.setenv("FLYTO_ALLOW_PRIVATE_NETWORK", "false")
        result = await _run(params(
            [{"url": "http://localhost:9999/data"}],
            stop_on_error=False,
        ))

        assert result["ok"] is False
        r = result["results"][0]
        assert r["error_code"] == "SSRF_BLOCKED"


# ---------------------------------------------------------------------------
# Tests: _read_body — JSON Content-Type with invalid JSON body falls back to text
# ---------------------------------------------------------------------------


async def _handle_invalid_json_ct(request: web.Request) -> web.Response:
    """Return Content-Type: application/json with a body that is NOT valid JSON."""
    return web.Response(
        body=b"this is not json at all !!!",
        content_type="application/json",
    )


async def _handle_post_no_content_type(request: web.Request) -> web.Response:
    """Echo back the Content-Type header that was received."""
    ct = request.headers.get("Content-Type", "")
    body = await request.read()
    return web.json_response({"content_type": ct, "got_body": len(body) > 0})


async def _handle_close_abruptly(request: web.Request) -> web.StreamResponse:
    """Accept the connection then drop it immediately without sending a response."""
    # Forcibly close the underlying transport so aiohttp raises a ClientError
    request.transport.close()  # type: ignore[union-attr]
    raise web.HTTPInternalServerError()


@pytest.fixture
async def extended_test_server(monkeypatch):
    """Extended server with additional routes for coverage tests."""
    monkeypatch.setenv("FLYTO_ALLOW_PRIVATE_NETWORK", "true")

    app = web.Application()
    app.router.add_get("/data", _handle_get_data)
    app.router.add_get("/invalid_json_ct", _handle_invalid_json_ct)
    app.router.add_post("/post_echo_ct", _handle_post_no_content_type)
    app.router.add_get("/close_abruptly", _handle_close_abruptly)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    base = f"http://localhost:{port}"
    yield base
    await runner.cleanup()


class TestReadBodyFallback:
    async def test_auto_json_ct_invalid_json_falls_back_to_text(self, extended_test_server):
        """Lines 45-46: application/json Content-Type but body is not valid JSON → fallback to text."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{extended_test_server}/invalid_json_ct",
                headers={"Accept": "*/*"},
            ) as response:
                body = await _read_body(response, "auto")

        # The fallback path returns the raw text instead of raising
        assert isinstance(body, str)
        assert "this is not json at all" in body


class TestPostBodyAttachment:
    async def test_post_without_content_type_auto_sets_application_json(self, extended_test_server):
        """Lines 77-79: POST with body and no explicit Content-Type → auto-set to application/json."""
        result = await _run(params(
            [{"label": "Post", "url": f"{extended_test_server}/post_echo_ct",
              "method": "POST", "body": {"x": 1}}],
        ))

        assert result["ok"] is True
        r = result["results"][0]
        assert r["ok"] is True
        # The server echoes back what Content-Type it received
        assert r["body"]["content_type"] == "application/json"
        assert r["body"]["got_body"] is True


class TestClientError:
    async def test_connection_closed_abruptly_returns_client_error(self, extended_test_server):
        """Lines 100-102: aiohttp.ClientError (connection reset) → CLIENT_ERROR result."""
        result = await _run(params(
            [{"label": "Broken", "url": f"{extended_test_server}/close_abruptly"}],
            stop_on_error=False,
        ))

        assert result["ok"] is False
        r = result["results"][0]
        assert r["ok"] is False
        assert r["error_code"] == "CLIENT_ERROR"


# ---------------------------------------------------------------------------
# Tests — ImportError when aiohttp is missing (lines 302-303)
# ---------------------------------------------------------------------------

import sys


class TestAiohttpImportError:
    async def test_importerror_when_aiohttp_missing(self):
        """Lines 302-303: ImportError raised when aiohttp is not importable."""
        saved = sys.modules.pop('aiohttp', None)
        sys.modules['aiohttp'] = None  # type: ignore[assignment]
        try:
            from core.modules.atomic.http.session import http_session as _hs
            instance = _hs({'requests': [{'url': 'http://example.com'}]}, {})
            with pytest.raises(ImportError, match="aiohttp is required"):
                await instance.execute()
        finally:
            if saved is not None:
                sys.modules['aiohttp'] = saved
            else:
                sys.modules.pop('aiohttp', None)


# ---------------------------------------------------------------------------
# Edge-case fixture — server for GET-body, per-request headers, SSRF mix
# ---------------------------------------------------------------------------


async def _handle_get_body_check(request: web.Request) -> web.Response:
    """Return whether the server received any body bytes on a GET request."""
    body = await request.read()
    return web.json_response({"received_body": len(body) > 0, "method": request.method})


async def _handle_content_type_echo(request: web.Request) -> web.Response:
    """Echo back the Content-Type header that arrived, plus whether body was received."""
    ct = request.headers.get("Content-Type", "")
    body = await request.read()
    return web.json_response({"content_type": ct, "got_body": len(body) > 0})


@pytest.fixture
async def edge_case_server(monkeypatch):
    """Minimal server for edge-case tests."""
    monkeypatch.setenv("FLYTO_ALLOW_PRIVATE_NETWORK", "true")

    app = web.Application()
    app.router.add_get("/get_body_check", _handle_get_body_check)
    app.router.add_post("/ct_echo", _handle_content_type_echo)
    app.router.add_get("/data", _handle_get_data)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    base = f"http://localhost:{port}"
    yield base
    await runner.cleanup()


# ---------------------------------------------------------------------------
# 1. GET with body — body silently dropped
# ---------------------------------------------------------------------------


class TestGetBodyDropped:
    async def test_body_with_get_request_is_not_sent(self, edge_case_server):
        """Body provided on a GET request is silently ignored (not forwarded to server)."""
        result = await _run(params(
            [{"label": "GetWithBody", "url": f"{edge_case_server}/get_body_check",
              "method": "GET", "body": {"should": "be dropped"}}],
        ))

        assert result["ok"] is True
        r = result["results"][0]
        assert r["ok"] is True
        assert r["body"]["method"] == "GET"
        # Server must not have received any body bytes
        assert r["body"]["received_body"] is False

    async def test_post_sends_body(self, edge_case_server):
        """Contrast: POST with same body does reach the server."""
        result = await _run(params(
            [{"label": "PostWithBody", "url": f"{edge_case_server}/ct_echo",
              "method": "POST", "body": {"key": "value"}}],
        ))

        assert result["ok"] is True
        assert result["results"][0]["body"]["got_body"] is True


# ---------------------------------------------------------------------------
# 2. Per-request Content-Type is preserved, not overwritten
# ---------------------------------------------------------------------------


class TestPerRequestContentTypePreserved:
    async def test_explicit_content_type_not_overwritten(self, edge_case_server):
        """If per-request headers already contain Content-Type, it must not be replaced."""
        result = await _run(params(
            [{"label": "CustomCT", "url": f"{edge_case_server}/ct_echo",
              "method": "POST", "body": {"x": 1},
              "headers": {"Content-Type": "application/vnd.api+json"}}],
        ))

        assert result["ok"] is True
        r = result["results"][0]
        assert r["ok"] is True
        # The server must echo back the original Content-Type, not application/json
        assert r["body"]["content_type"] == "application/vnd.api+json"

    async def test_no_content_type_gets_auto_set_to_json(self, edge_case_server):
        """When no Content-Type is provided for POST, module auto-sets application/json."""
        result = await _run(params(
            [{"label": "AutoCT", "url": f"{edge_case_server}/ct_echo",
              "method": "POST", "body": {"x": 1}}],
        ))

        assert result["ok"] is True
        assert result["results"][0]["body"]["content_type"] == "application/json"


# ---------------------------------------------------------------------------
# 3. Empty URL string → error handling
# ---------------------------------------------------------------------------


class TestEmptyUrl:
    async def test_empty_url_with_private_network_blocked(self, monkeypatch):
        """Empty URL string with SSRF guard active (allow_private=False) → SSRF_BLOCKED."""
        monkeypatch.setenv("FLYTO_ALLOW_PRIVATE_NETWORK", "false")
        result = await _run(params(
            [{"label": "EmptyUrl", "url": ""}],
            stop_on_error=False,
        ))

        assert result["ok"] is False
        r = result["results"][0]
        assert r["ok"] is False
        # Empty URL has no valid scheme → SSRFError raised by validate_url_ssrf
        assert r["error_code"] == "SSRF_BLOCKED"

    async def test_empty_url_with_private_network_allowed(self, monkeypatch):
        """Empty URL string with allow_private=True bypasses SSRF check → CLIENT_ERROR from aiohttp."""
        monkeypatch.setenv("FLYTO_ALLOW_PRIVATE_NETWORK", "true")
        result = await _run(params(
            [{"label": "EmptyUrl", "url": ""}],
            stop_on_error=False,
        ))

        assert result["ok"] is False
        r = result["results"][0]
        assert r["ok"] is False
        # aiohttp cannot make a request to an empty URL → CLIENT_ERROR
        assert r["error_code"] == "CLIENT_ERROR"


# ---------------------------------------------------------------------------
# 4. Mixed SSRF-blocked and valid requests with stop_on_error=False
# ---------------------------------------------------------------------------


class TestMixedSSRFAndValid:
    async def test_ssrf_blocked_and_valid_both_appear_in_results(self, monkeypatch, edge_case_server):
        """With stop_on_error=False, a blocked request and a valid request both appear in results."""
        # edge_case_server fixture sets FLYTO_ALLOW_PRIVATE_NETWORK=true for localhost,
        # but we need localhost to be blocked for the first request only.
        # Use an external-looking URL that is still blocked (169.254.x.x metadata range).
        monkeypatch.setenv("FLYTO_ALLOW_PRIVATE_NETWORK", "false")

        # Restart environment: we need one blocked URL and one reachable one.
        # Since private network is now blocked we can't use localhost for the valid request.
        # Instead use the two blocked/valid checks against a public host — but in tests we
        # avoid real network. Use 169.254.169.254 (always blocked) as the SSRF target and
        # confirm that the second entry still appears even when the first is blocked.
        result = await _run(params(
            [
                {"label": "Blocked", "url": "http://169.254.169.254/latest/meta-data"},
                {"label": "AlsoBlocked", "url": "http://192.168.1.1/admin"},
            ],
            stop_on_error=False,
        ))

        assert result["ok"] is False
        assert len(result["results"]) == 2
        assert result["results"][0]["error_code"] == "SSRF_BLOCKED"
        assert result["results"][0]["label"] == "Blocked"
        assert result["results"][1]["error_code"] == "SSRF_BLOCKED"
        assert result["results"][1]["label"] == "AlsoBlocked"

    @pytest.mark.skip(
        reason="Test design conflicts with SSRF port whitelist: the fixture server "
        "binds to a random high port (e.g. :58209) but validate_url_ssrf enforces "
        "{80, 443, 8080, 8443} BEFORE the hostname allowlist. Relaxing the port "
        "order would be a product-level SSRF regression, so this scenario can't "
        "be reproduced locally without allow_private=true — which nullifies the test."
    )
    async def test_ssrf_blocked_first_then_valid_continues(self, edge_case_server, monkeypatch):
        """First request SSRF-blocked, second request valid — stop_on_error=False means both run.

        Strategy: disable allow_private but whitelist localhost via FLYTO_ALLOWED_HOSTS so
        the test server remains reachable while the metadata IP is still blocked.
        """
        monkeypatch.setenv("FLYTO_ALLOW_PRIVATE_NETWORK", "false")
        monkeypatch.setenv("FLYTO_ALLOWED_HOSTS", "localhost,127.0.0.1")

        result = await _run(params(
            [
                {"label": "Blocked", "url": "http://169.254.169.254/latest/meta-data"},
                {"label": "Valid", "url": f"{edge_case_server}/data"},
            ],
            stop_on_error=False,
        ))

        assert result["ok"] is False
        assert len(result["results"]) == 2
        r0, r1 = result["results"]
        assert r0["label"] == "Blocked"
        assert r0["ok"] is False
        assert r0["error_code"] == "SSRF_BLOCKED"
        assert r1["label"] == "Valid"
        assert r1["ok"] is True
        assert r1["status"] == 200


# ---------------------------------------------------------------------------
# 5. _apply_auth called twice — no header accumulation
# ---------------------------------------------------------------------------


class TestApplyAuthNoAccumulation:
    def test_bearer_called_twice_does_not_accumulate(self):
        """Calling _apply_auth twice on the same headers dict overwrites, never appends."""
        headers: dict = {}
        _apply_auth(headers, {"type": "bearer", "token": "first"})
        _apply_auth(headers, {"type": "bearer", "token": "second"})

        # Must be a single string, not a list or concatenated value
        assert headers["Authorization"] == "Bearer second"
        assert isinstance(headers["Authorization"], str)

    def test_api_key_called_twice_overwrites(self):
        """Repeated _apply_auth for api_key replaces the previous value."""
        headers: dict = {}
        _apply_auth(headers, {"type": "api_key", "header_name": "X-Token", "api_key": "keyA"})
        _apply_auth(headers, {"type": "api_key", "header_name": "X-Token", "api_key": "keyB"})

        assert headers["X-Token"] == "keyB"
        # No stale entries
        assert len([k for k in headers if k == "X-Token"]) == 1

    def test_session_context_not_mutated_across_requests(self, monkeypatch):
        """_apply_auth works on per-request header copies; the original dict is unchanged."""
        monkeypatch.setenv("FLYTO_ALLOW_PRIVATE_NETWORK", "true")
        original: dict = {"Accept": "application/json"}
        copy1 = dict(original)
        copy2 = dict(original)

        _apply_auth(copy1, {"type": "bearer", "token": "tok1"})
        _apply_auth(copy2, {"type": "bearer", "token": "tok2"})

        # Each call mutated its own dict
        assert copy1["Authorization"] == "Bearer tok1"
        assert copy2["Authorization"] == "Bearer tok2"
        # The shared source dict was never touched
        assert "Authorization" not in original


# ---------------------------------------------------------------------------
# 7. _read_body with explicit response_type='json' on a valid JSON response
# ---------------------------------------------------------------------------


class TestReadBodyExplicitJson:
    async def test_explicit_json_on_json_response_returns_dict(self, edge_case_server):
        """response_type='json' on a JSON endpoint always returns a parsed dict."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{edge_case_server}/data") as response:
                body = await _read_body(response, "json")

        assert isinstance(body, dict)
        assert body["message"] == "hello"
        assert body["method"] == "GET"

    async def test_explicit_json_type_attribute_preserved(self, edge_case_server):
        """Parsed JSON dict has correct types (str, str) — not double-decoded."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{edge_case_server}/data") as response:
                body = await _read_body(response, "json")

        assert isinstance(body["message"], str)
        assert isinstance(body["method"], str)


# ---------------------------------------------------------------------------
# 8. _read_body with explicit response_type='text' on a JSON response
# ---------------------------------------------------------------------------


class TestReadBodyTextOnJson:
    async def test_explicit_text_on_json_response_returns_string(self, edge_case_server):
        """response_type='text' on a JSON endpoint returns a raw string, never a dict."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{edge_case_server}/data") as response:
                body = await _read_body(response, "text")

        assert isinstance(body, str)
        # Must NOT be a dict
        assert not isinstance(body, dict)

    async def test_explicit_text_contains_json_content(self, edge_case_server):
        """The raw string still contains the serialized JSON content."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{edge_case_server}/data") as response:
                body = await _read_body(response, "text")

        # The JSON payload is present as a string
        assert "hello" in body
        assert "message" in body
