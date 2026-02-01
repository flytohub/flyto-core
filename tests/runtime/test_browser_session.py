"""
Tests for browser session management.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.runtime.browser_session import (
    BrowserSession,
    BrowserSessionManager,
    get_browser_manager,
    reset_browser_manager,
)


class TestBrowserSession:
    """Tests for BrowserSession dataclass."""

    def test_create_session(self):
        """Test creating a browser session."""
        session = BrowserSession(
            session_id="test-123",
            ws_endpoint="ws://localhost:9222/devtools/browser/abc",
            headless=True,
        )
        assert session.session_id == "test-123"
        assert session.ws_endpoint == "ws://localhost:9222/devtools/browser/abc"
        assert session.headless is True
        assert session.context_count == 0

    def test_to_dict(self):
        """Test serialization to dict."""
        session = BrowserSession(
            session_id="test-123",
            ws_endpoint="ws://localhost:9222/devtools/browser/abc",
        )
        data = session.to_dict()

        assert data["session_id"] == "test-123"
        assert data["ws_endpoint"] == "ws://localhost:9222/devtools/browser/abc"
        assert "created_at" in data
        assert "last_accessed" in data

    def test_touch_updates_time(self):
        """Test touch() updates last_accessed."""
        session = BrowserSession(
            session_id="test",
            ws_endpoint="ws://localhost:9222/devtools/browser/abc",
        )
        original_time = session.last_accessed
        import time
        time.sleep(0.01)
        session.touch()
        assert session.last_accessed > original_time


class TestBrowserSessionManager:
    """Tests for BrowserSessionManager."""

    @pytest.fixture
    def manager(self):
        """Create a fresh manager for each test."""
        return BrowserSessionManager(
            idle_timeout_seconds=60,
            max_sessions=5,
        )

    def test_init(self, manager):
        """Test manager initialization."""
        assert manager._idle_timeout == 60
        assert manager._max_sessions == 5
        assert len(manager._sessions) == 0

    def test_list_sessions_empty(self, manager):
        """Test listing sessions when empty."""
        sessions = manager.list_sessions()
        assert sessions == {}

    @pytest.mark.asyncio
    async def test_create_session_requires_playwright(self, manager):
        """Test create_session raises ImportError without playwright."""
        with patch.dict("sys.modules", {"playwright": None, "playwright.async_api": None}):
            # Force reimport to trigger ImportError
            manager._playwright = None
            with pytest.raises(ImportError) as exc_info:
                await manager.create_session("test")
            assert "playwright" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_close_nonexistent_session(self, manager):
        """Test closing a session that doesn't exist."""
        result = await manager.close_session("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, manager):
        """Test getting a session that doesn't exist."""
        session = await manager.get_session("nonexistent")
        assert session is None

    @pytest.mark.asyncio
    async def test_shutdown_empty(self, manager):
        """Test shutdown with no sessions."""
        await manager.shutdown()
        assert len(manager._sessions) == 0


class TestBrowserSessionManagerWithMock:
    """Tests using mocked playwright."""

    @pytest.fixture
    def mock_playwright(self):
        """Create mock playwright."""
        mock_browser = MagicMock()
        mock_browser.contexts = []
        mock_browser.close = AsyncMock()

        # Mock the _impl_obj._ws_endpoint for getting the endpoint
        mock_browser._impl_obj = MagicMock()
        mock_browser._impl_obj._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/test-id"

        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)
        mock_chromium.connect = AsyncMock(return_value=mock_browser)

        mock_pw = MagicMock()
        mock_pw.chromium = mock_chromium
        mock_pw.stop = AsyncMock()

        return mock_pw, mock_browser

    @pytest.mark.asyncio
    async def test_create_session_success(self, mock_playwright):
        """Test successful session creation."""
        mock_pw, mock_browser = mock_playwright

        manager = BrowserSessionManager()

        # Mock async_playwright
        async def mock_start():
            return mock_pw

        with patch("core.runtime.browser_session.BrowserSessionManager._ensure_playwright") as mock_ensure:
            async def set_playwright():
                manager._playwright = mock_pw
            mock_ensure.side_effect = set_playwright

            result = await manager.create_session("test-session", headless=True)

            # Security: create_session now returns dict with ws_endpoint, session_id, and session_token
            assert isinstance(result, dict)
            assert result["ws_endpoint"] == "ws://127.0.0.1:9222/devtools/browser/test-id"
            assert result["session_id"] == "test-session"
            assert "session_token" in result
            assert len(result["session_token"]) >= 32  # Token should be sufficiently long
            assert "test-session" in manager._sessions
            mock_pw.chromium.launch.assert_called_once()

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_get_or_create_existing(self, mock_playwright):
        """Test get_or_create returns existing session."""
        mock_pw, mock_browser = mock_playwright

        manager = BrowserSessionManager()

        # Manually add a session
        session = BrowserSession(
            session_id="existing",
            ws_endpoint="ws://existing",
            _browser=mock_browser,
        )
        manager._sessions["existing"] = session

        result = await manager.get_or_create_session("existing")

        # Security: get_or_create_session now returns dict with ws_endpoint, session_id, and session_token
        assert isinstance(result, dict)
        assert result["ws_endpoint"] == "ws://existing"
        assert result["session_id"] == "existing"
        assert "session_token" in result
        # Should not have created a new browser
        mock_pw.chromium.launch.assert_not_called()

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_max_sessions_limit(self, mock_playwright):
        """Test max sessions limit."""
        mock_pw, mock_browser = mock_playwright

        manager = BrowserSessionManager(max_sessions=2)

        # Add two sessions manually
        for i in range(2):
            session = BrowserSession(
                session_id=f"session-{i}",
                ws_endpoint=f"ws://session-{i}",
                _browser=mock_browser,
            )
            manager._sessions[f"session-{i}"] = session

        with patch("core.runtime.browser_session.BrowserSessionManager._ensure_playwright"):
            manager._playwright = mock_pw
            with pytest.raises(RuntimeError) as exc_info:
                await manager.create_session("session-3")
            assert "Maximum" in str(exc_info.value)

        await manager.shutdown()


class TestGlobalManager:
    """Tests for global manager functions."""

    @pytest.mark.asyncio
    async def test_get_browser_manager_singleton(self):
        """Test get_browser_manager returns singleton."""
        await reset_browser_manager()

        manager1 = get_browser_manager()
        manager2 = get_browser_manager()

        assert manager1 is manager2

        await reset_browser_manager()

    @pytest.mark.asyncio
    async def test_reset_browser_manager(self):
        """Test reset_browser_manager clears singleton."""
        manager1 = get_browser_manager()
        await reset_browser_manager()
        manager2 = get_browser_manager()

        assert manager1 is not manager2

        await reset_browser_manager()
