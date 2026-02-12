"""
Tests for MCP server browser session persistence.

Verifies that _browser_sessions store works correctly:
- Sessions are created on browser.launch
- Sessions are auto-resolved when only one exists
- Sessions are cleaned up on browser.close
- Multiple sessions require explicit session_id
- Non-browser modules bypass session logic entirely
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

# Import the module under test
from core.mcp_server import execute_module, _browser_sessions


@pytest.fixture(autouse=True)
def clear_sessions():
    """Ensure clean session state for each test."""
    _browser_sessions.clear()
    yield
    _browser_sessions.clear()


def _make_mock_module(ok=True, data=None):
    """Create a mock module class whose run() returns a result dict."""
    result = {"ok": ok}
    if data is not None:
        result["data"] = data

    mock_instance = MagicMock()
    mock_instance.run = AsyncMock(return_value=result)

    mock_class = MagicMock(return_value=mock_instance)
    return mock_class, mock_instance


class TestBrowserLaunchStoresSession:
    """browser.launch should store the driver and return a session_id."""

    async def test_launch_stores_session(self):
        mock_class, mock_instance = _make_mock_module(ok=True, data={"status": "launched"})

        # Simulate browser.launch putting a driver into ctx
        fake_driver = MagicMock()

        def capture_ctx(params, ctx):
            ctx["browser"] = fake_driver
            return mock_instance

        mock_class.side_effect = capture_ctx

        with patch("core.modules.registry.ModuleRegistry.get", return_value=mock_class):
            result = await execute_module("browser.launch", {"headless": True})

        assert result["ok"] is True
        assert len(_browser_sessions) == 1
        session_id = list(_browser_sessions.keys())[0]
        assert len(session_id) == 8  # uuid4()[:8]
        assert _browser_sessions[session_id] is fake_driver
        assert result["data"]["browser_session"] == session_id


class TestBrowserSessionAutoResolve:
    """When only 1 session exists, browser.* modules should auto-resolve."""

    async def test_auto_resolve_single_session(self):
        # Pre-populate a session
        fake_driver = MagicMock()
        _browser_sessions["abc12345"] = fake_driver

        mock_class, mock_instance = _make_mock_module(ok=True, data={"url": "https://example.com"})
        captured_ctx = {}

        def capture_ctx(params, ctx):
            captured_ctx.update(ctx)
            return mock_instance

        mock_class.side_effect = capture_ctx

        with patch("core.modules.registry.ModuleRegistry.get", return_value=mock_class):
            result = await execute_module("browser.goto", {"url": "https://example.com"})

        assert result["ok"] is True
        assert captured_ctx["browser"] is fake_driver


class TestBrowserSessionExplicitId:
    """Explicit browser_session in context should select the right session."""

    async def test_explicit_session_id(self):
        driver_a = MagicMock(name="driver_a")
        driver_b = MagicMock(name="driver_b")
        _browser_sessions["sess-aaa"] = driver_a
        _browser_sessions["sess-bbb"] = driver_b

        mock_class, mock_instance = _make_mock_module(ok=True, data={})
        captured_ctx = {}

        def capture_ctx(params, ctx):
            captured_ctx.update(ctx)
            return mock_instance

        mock_class.side_effect = capture_ctx

        with patch("core.modules.registry.ModuleRegistry.get", return_value=mock_class):
            result = await execute_module(
                "browser.extract",
                {"selector": "h1"},
                context={"browser_session": "sess-bbb"},
            )

        assert result["ok"] is True
        assert captured_ctx["browser"] is driver_b


class TestBrowserSessionErrors:
    """Error cases for session resolution."""

    async def test_no_session_returns_error(self):
        mock_class, _ = _make_mock_module()
        with patch("core.modules.registry.ModuleRegistry.get", return_value=mock_class):
            result = await execute_module("browser.goto", {"url": "https://x.com"})

        assert result["ok"] is False
        assert "Call browser.launch first" in result["error"]

    async def test_multiple_sessions_no_id_returns_error(self):
        _browser_sessions["s1"] = MagicMock()
        _browser_sessions["s2"] = MagicMock()

        mock_class, _ = _make_mock_module()
        with patch("core.modules.registry.ModuleRegistry.get", return_value=mock_class):
            result = await execute_module("browser.goto", {"url": "https://x.com"})

        assert result["ok"] is False
        assert "Multiple browser sessions" in result["error"]

    async def test_invalid_session_id_returns_error(self):
        _browser_sessions["real"] = MagicMock()

        mock_class, _ = _make_mock_module()
        with patch("core.modules.registry.ModuleRegistry.get", return_value=mock_class):
            result = await execute_module(
                "browser.goto",
                {"url": "https://x.com"},
                context={"browser_session": "nonexistent"},
            )

        assert result["ok"] is False
        assert "not found" in result["error"]


class TestBrowserCloseRemovesSession:
    """browser.close should clean up the session store."""

    async def test_close_removes_single_session(self):
        fake_driver = MagicMock()
        _browser_sessions["sess-x"] = fake_driver

        mock_class, mock_instance = _make_mock_module(ok=True, data={})
        mock_class.side_effect = lambda params, ctx: mock_instance

        with patch("core.modules.registry.ModuleRegistry.get", return_value=mock_class):
            result = await execute_module("browser.close", {})

        assert result["ok"] is True
        assert len(_browser_sessions) == 0

    async def test_close_with_explicit_id(self):
        _browser_sessions["keep"] = MagicMock()
        _browser_sessions["remove"] = MagicMock()

        mock_class, mock_instance = _make_mock_module(ok=True, data={})

        def capture_ctx(params, ctx):
            return mock_instance

        mock_class.side_effect = capture_ctx

        with patch("core.modules.registry.ModuleRegistry.get", return_value=mock_class):
            result = await execute_module(
                "browser.close", {}, context={"browser_session": "remove"}
            )

        assert result["ok"] is True
        assert "keep" in _browser_sessions
        assert "remove" not in _browser_sessions


class TestNonBrowserModulesUnaffected:
    """Non-browser modules should bypass session logic entirely."""

    async def test_string_module_no_session_logic(self):
        mock_class, mock_instance = _make_mock_module(ok=True, data={"result": "HELLO"})
        mock_class.side_effect = lambda params, ctx: mock_instance

        with patch("core.modules.registry.ModuleRegistry.get", return_value=mock_class):
            result = await execute_module("string.uppercase", {"text": "hello"})

        assert result["ok"] is True
        assert len(_browser_sessions) == 0
