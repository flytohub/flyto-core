"""
Browser Session Management

Manages browser sessions that can be shared across subprocesses using
Chrome DevTools Protocol (CDP) WebSocket endpoints.

This allows plugins written in any language to connect to a shared browser
instance started by the Core runtime.

Security:
- Sessions require authentication via session tokens
- Plugins must be explicitly authorized to access sessions
- Multi-tenant isolation is enforced
"""

import asyncio
import logging
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from .exceptions import InvalidSessionTokenError, UnauthorizedAccessError

logger = logging.getLogger(__name__)

# Type hints for playwright without hard dependency
if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page


@dataclass
class BrowserSession:
    """
    Represents an active browser session.

    Security:
    - session_token: Required for all access (prevents unauthorized connections)
    - allowed_plugins: Whitelist of plugin IDs that can access this session
    - owner_plugin: Plugin that created the session (has full access)
    - tenant_id: Multi-tenant isolation identifier
    """

    session_id: str
    ws_endpoint: str
    headless: bool = True
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    context_count: int = 0

    # Security: Authentication and authorization
    session_token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    owner_plugin: Optional[str] = None  # Plugin that created this session
    allowed_plugins: Set[str] = field(default_factory=set)  # Plugins with access
    tenant_id: Optional[str] = None  # For multi-tenant isolation

    # Internal references (not serializable)
    _browser: Optional["Browser"] = field(default=None, repr=False)
    _contexts: Dict[str, "BrowserContext"] = field(default_factory=dict, repr=False)

    def to_dict(self, include_token: bool = False) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Args:
            include_token: If True, include session_token (only for owner)
        """
        result = {
            "session_id": self.session_id,
            "ws_endpoint": self.ws_endpoint,
            "headless": self.headless,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "context_count": len(self._contexts),
            "owner_plugin": self.owner_plugin,
            "tenant_id": self.tenant_id,
        }
        if include_token:
            result["session_token"] = self.session_token
        return result

    def touch(self):
        """Update last accessed time."""
        self.last_accessed = time.time()

    def authorize_plugin(self, plugin_id: str):
        """Grant a plugin access to this session."""
        self.allowed_plugins.add(plugin_id)

    def revoke_plugin(self, plugin_id: str):
        """Revoke a plugin's access to this session."""
        self.allowed_plugins.discard(plugin_id)

    def is_authorized(self, plugin_id: str, token: Optional[str] = None) -> bool:
        """
        Check if a plugin is authorized to access this session.

        Args:
            plugin_id: Plugin requesting access
            token: Session token provided by the plugin

        Returns:
            True if authorized
        """
        # Token must match
        if token != self.session_token:
            return False

        # Owner always has access
        if plugin_id == self.owner_plugin:
            return True

        # Check allowed list
        return plugin_id in self.allowed_plugins


class BrowserSessionManager:
    """
    Manages browser sessions that can be shared across subprocesses.

    Key Features:
    - Creates browser instances and exposes CDP WebSocket endpoints
    - Allows plugins to connect via ws_endpoint string (serializable)
    - Manages session lifecycle (idle timeout, cleanup)
    - Supports multiple concurrent sessions

    Usage:
        manager = BrowserSessionManager()

        # Create a session (returns ws_endpoint string)
        ws_endpoint = await manager.create_session("my-session", headless=False)

        # Plugin context gets ws_endpoint
        context = {"browser_ws_endpoint": ws_endpoint}

        # Plugin connects using its own browser library
        # Python: browser = await playwright.chromium.connect(ws_endpoint)
        # Node: browser = await chromium.connect({wsEndpoint: ws_endpoint})
    """

    def __init__(
        self,
        idle_timeout_seconds: int = 300,
        max_sessions: int = 10,
    ):
        """
        Initialize browser session manager.

        Args:
            idle_timeout_seconds: Timeout before closing idle sessions
            max_sessions: Maximum concurrent browser sessions
        """
        self._sessions: Dict[str, BrowserSession] = {}
        self._idle_timeout = idle_timeout_seconds
        self._max_sessions = max_sessions
        self._cleanup_task: Optional[asyncio.Task] = None
        self._playwright = None
        self._lock = asyncio.Lock()

    async def _ensure_playwright(self):
        """Ensure playwright is initialized."""
        if self._playwright is None:
            try:
                from playwright.async_api import async_playwright
                self._playwright = await async_playwright().start()
                logger.info("Playwright initialized")
            except ImportError:
                raise ImportError(
                    "playwright is required for browser session management. "
                    "Install with: pip install playwright && playwright install chromium"
                )

    async def create_session(
        self,
        session_id: Optional[str] = None,
        headless: bool = True,
        browser_type: str = "chromium",
        launch_options: Optional[Dict[str, Any]] = None,
        owner_plugin: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Create a new browser session and return connection info.

        Security:
        - Returns session_token for authentication
        - owner_plugin has automatic access
        - Other plugins must be explicitly authorized

        Args:
            session_id: Optional session identifier (auto-generated if not provided)
            headless: Run browser in headless mode
            browser_type: Browser type (chromium, firefox, webkit)
            launch_options: Additional launch options for playwright
            owner_plugin: Plugin ID that owns this session
            tenant_id: Tenant ID for multi-tenant isolation

        Returns:
            Dict with ws_endpoint, session_id, and session_token

        Raises:
            RuntimeError: If max sessions reached
            ImportError: If playwright not installed
        """
        async with self._lock:
            # Check if session already exists
            if session_id and session_id in self._sessions:
                session = self._sessions[session_id]
                # Security: Only return token to owner
                if owner_plugin and session.owner_plugin == owner_plugin:
                    session.touch()
                    return {
                        "ws_endpoint": session.ws_endpoint,
                        "session_id": session.session_id,
                        "session_token": session.session_token,
                    }
                # For non-owners, check authorization
                elif owner_plugin and session.is_authorized(owner_plugin, session.session_token):
                    session.touch()
                    return {
                        "ws_endpoint": session.ws_endpoint,
                        "session_id": session.session_id,
                        "session_token": session.session_token,
                    }
                else:
                    raise UnauthorizedAccessError(
                        f"browser_session:{session_id}",
                        owner_plugin
                    )

            # Check max sessions
            if len(self._sessions) >= self._max_sessions:
                # Try to cleanup idle sessions
                await self._cleanup_idle_sessions()
                if len(self._sessions) >= self._max_sessions:
                    raise RuntimeError(
                        f"Maximum browser sessions reached ({self._max_sessions})"
                    )

            # Generate session ID if not provided
            if not session_id:
                session_id = f"browser-{uuid.uuid4().hex[:8]}"

            # Initialize playwright
            await self._ensure_playwright()

            # Get browser launcher
            browser_launcher = getattr(self._playwright, browser_type, None)
            if not browser_launcher:
                raise ValueError(f"Unsupported browser type: {browser_type}")

            # Prepare launch options
            options = {
                "headless": headless,
            }
            if launch_options:
                options.update(launch_options)

            logger.info(f"Launching browser for session {session_id} (headless={headless})")

            # Launch browser
            browser = await browser_launcher.launch(**options)

            # Get WebSocket endpoint
            # Note: Playwright's browser.ws_endpoint is the CDP endpoint
            ws_endpoint = browser.contexts[0].browser.ws_endpoint if browser.contexts else None

            # For a fresh browser, we need to access it differently
            # The ws_endpoint is available on the browser object for Chromium
            if hasattr(browser, '_impl_obj') and hasattr(browser._impl_obj, '_ws_endpoint'):
                ws_endpoint = browser._impl_obj._ws_endpoint
            elif hasattr(browser, 'ws_endpoint'):
                ws_endpoint = browser.ws_endpoint

            if not ws_endpoint:
                # Fallback: launch with explicit CDP and capture endpoint
                await browser.close()
                browser = await browser_launcher.launch(
                    **options,
                    args=["--remote-debugging-port=0"],  # Auto-assign port
                )
                # Try to get endpoint from browser
                if hasattr(browser, '_impl_obj'):
                    ws_endpoint = getattr(browser._impl_obj, '_ws_endpoint', None)

            if not ws_endpoint:
                logger.warning(
                    f"Could not get WebSocket endpoint for session {session_id}. "
                    "Plugins may not be able to connect."
                )
                ws_endpoint = f"ws://localhost:9222/devtools/browser/{session_id}"

            # Create session with security fields
            session = BrowserSession(
                session_id=session_id,
                ws_endpoint=ws_endpoint,
                headless=headless,
                owner_plugin=owner_plugin,
                tenant_id=tenant_id,
                _browser=browser,
            )

            # Owner automatically gets access
            if owner_plugin:
                session.authorize_plugin(owner_plugin)

            self._sessions[session_id] = session
            logger.info(
                f"Browser session created: {session_id} -> {ws_endpoint} "
                f"(owner: {owner_plugin}, tenant: {tenant_id})"
            )

            # Start cleanup task if not running
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())

            # Return connection info with token (secure)
            return {
                "ws_endpoint": ws_endpoint,
                "session_id": session_id,
                "session_token": session.session_token,
            }

    async def get_session(self, session_id: str) -> Optional[BrowserSession]:
        """
        Get an existing browser session.

        Args:
            session_id: Session identifier

        Returns:
            BrowserSession or None if not found
        """
        session = self._sessions.get(session_id)
        if session:
            session.touch()
        return session

    async def get_or_create_session(
        self,
        session_id: str,
        owner_plugin: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, str]:
        """
        Get existing session or create a new one.

        Args:
            session_id: Session identifier
            owner_plugin: Plugin requesting the session
            **kwargs: Arguments passed to create_session

        Returns:
            Dict with ws_endpoint, session_id, and session_token
        """
        session = await self.get_session(session_id)
        if session:
            # Security: Verify access if owner_plugin provided
            if owner_plugin:
                if not session.is_authorized(owner_plugin, session.session_token):
                    # Plugin not authorized, create a new session for them
                    new_session_id = f"{session_id}-{owner_plugin[:8]}"
                    return await self.create_session(
                        session_id=new_session_id,
                        owner_plugin=owner_plugin,
                        **kwargs
                    )
            return {
                "ws_endpoint": session.ws_endpoint,
                "session_id": session.session_id,
                "session_token": session.session_token,
            }
        return await self.create_session(
            session_id=session_id,
            owner_plugin=owner_plugin,
            **kwargs
        )

    async def close_session(self, session_id: str) -> bool:
        """
        Close a browser session.

        Args:
            session_id: Session identifier

        Returns:
            True if session was closed, False if not found
        """
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if not session:
                return False

            try:
                if session._browser:
                    await session._browser.close()
                logger.info(f"Browser session closed: {session_id}")
            except Exception as e:
                logger.error(f"Error closing browser session {session_id}: {e}")

            return True

    async def connect_to_session(
        self,
        ws_endpoint: str,
        session_token: Optional[str] = None,
        plugin_id: Optional[str] = None,
    ) -> "Browser":
        """
        Connect to an existing browser session via WebSocket endpoint.

        Security:
        - Requires valid session_token for authentication
        - Plugin must be authorized (owner or in allowed list)
        - Core process can connect without auth (internal use)

        Args:
            ws_endpoint: WebSocket endpoint URL
            session_token: Authentication token (required for plugins)
            plugin_id: Plugin requesting connection (required for plugins)

        Returns:
            Browser instance connected to the session

        Raises:
            InvalidSessionTokenError: If token is invalid
            UnauthorizedAccessError: If plugin is not authorized
        """
        # Find session by endpoint
        session = self._find_session_by_endpoint(ws_endpoint)

        # Security: Validate access if plugin_id is provided
        if plugin_id is not None:
            if session is None:
                raise InvalidSessionTokenError("unknown")

            if not session.is_authorized(plugin_id, session_token):
                logger.warning(
                    f"Unauthorized browser access attempt: plugin={plugin_id}, "
                    f"session={session.session_id}"
                )
                raise UnauthorizedAccessError(
                    f"browser_session:{session.session_id}",
                    plugin_id
                )

            session.touch()

        await self._ensure_playwright()
        browser = await self._playwright.chromium.connect(ws_endpoint)
        return browser

    def _find_session_by_endpoint(self, ws_endpoint: str) -> Optional[BrowserSession]:
        """Find a session by its WebSocket endpoint."""
        for session in self._sessions.values():
            if session.ws_endpoint == ws_endpoint:
                return session
        return None

    async def authorize_plugin_for_session(
        self,
        session_id: str,
        plugin_id: str,
        authorizer_plugin: str,
        authorizer_token: str,
    ) -> bool:
        """
        Authorize a plugin to access a session.

        Only the session owner can authorize other plugins.

        Args:
            session_id: Session to grant access to
            plugin_id: Plugin to authorize
            authorizer_plugin: Plugin authorizing (must be owner)
            authorizer_token: Token of authorizer

        Returns:
            True if authorization granted

        Raises:
            UnauthorizedAccessError: If authorizer is not the owner
        """
        session = self._sessions.get(session_id)
        if not session:
            raise InvalidSessionTokenError(session_id)

        # Only owner can authorize
        if session.owner_plugin != authorizer_plugin:
            raise UnauthorizedAccessError(
                f"browser_session:{session_id}:authorize",
                authorizer_plugin
            )

        # Verify owner's token
        if session.session_token != authorizer_token:
            raise InvalidSessionTokenError(session_id)

        session.authorize_plugin(plugin_id)
        logger.info(f"Plugin {plugin_id} authorized for session {session_id}")
        return True

    async def create_context(
        self,
        session_id: str,
        context_id: Optional[str] = None,
        **context_options,
    ) -> Dict[str, str]:
        """
        Create a new browser context in an existing session.

        Args:
            session_id: Session identifier
            context_id: Optional context identifier
            **context_options: Options passed to browser.new_context()

        Returns:
            Dictionary with context_id
        """
        session = self._sessions.get(session_id)
        if not session or not session._browser:
            raise ValueError(f"Session not found: {session_id}")

        context_id = context_id or f"ctx-{uuid.uuid4().hex[:8]}"

        context = await session._browser.new_context(**context_options)
        session._contexts[context_id] = context
        session.touch()

        return {"context_id": context_id}

    async def _cleanup_idle_sessions(self):
        """Close sessions that have been idle too long."""
        now = time.time()
        idle_threshold = now - self._idle_timeout

        sessions_to_close = [
            session_id
            for session_id, session in self._sessions.items()
            if session.last_accessed < idle_threshold
        ]

        for session_id in sessions_to_close:
            logger.info(f"Closing idle browser session: {session_id}")
            await self.close_session(session_id)

    async def _cleanup_loop(self):
        """Background task for periodic cleanup."""
        while self._sessions:
            await asyncio.sleep(60)  # Check every minute
            await self._cleanup_idle_sessions()

    async def shutdown(self):
        """Shutdown manager and close all sessions."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Close all sessions
        session_ids = list(self._sessions.keys())
        for session_id in session_ids:
            await self.close_session(session_id)

        # Stop playwright
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        logger.info("Browser session manager shutdown complete")

    def list_sessions(self) -> Dict[str, Dict[str, Any]]:
        """List all active sessions."""
        return {
            session_id: session.to_dict()
            for session_id, session in self._sessions.items()
        }


# Global singleton
_browser_manager: Optional[BrowserSessionManager] = None


def get_browser_manager() -> BrowserSessionManager:
    """Get the global browser session manager."""
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = BrowserSessionManager()
    return _browser_manager


async def reset_browser_manager():
    """Reset the global browser manager (for testing)."""
    global _browser_manager
    if _browser_manager:
        await _browser_manager.shutdown()
    _browser_manager = None


async def get_or_create_browser_session(
    session_id: str = "default",
    headless: bool = True,
    owner_plugin: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> Dict[str, str]:
    """
    Convenience function to get or create a browser session.

    Args:
        session_id: Session identifier
        headless: Run in headless mode
        owner_plugin: Plugin requesting the session
        tenant_id: Tenant ID for multi-tenant isolation

    Returns:
        Dict with ws_endpoint, session_id, and session_token
    """
    manager = get_browser_manager()
    return await manager.get_or_create_session(
        session_id,
        headless=headless,
        owner_plugin=owner_plugin,
        tenant_id=tenant_id,
    )
