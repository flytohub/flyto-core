# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Session idle-timeout reaper — shared by all three transports.

`browser_sessions`/`debugger_sessions` (see mcp_server.py, mcp_handler.py,
api/state.py) are process-local dicts keyed by a minted session id. Until
now they were only ever cleaned up by an explicit browser.close/
reverse.detach call, or (STDIO only) on process EOF. A session abandoned
mid-workflow (crash, disconnect) leaked a live Chromium process and/or CDP
session for the life of the server process.

This module tracks a last-used timestamp per session id and periodically
closes/detaches (and drops) any session idle past a configurable timeout.
Both session types are reaped uniformly — browser_sessions never had a
reaper either, so fixing only debugger_sessions would be a half-measure.

A session with no recorded activity is left alone rather than reaped:
absence of data is not evidence of staleness, and callers that don't yet
call touch_session() for a given session must not have it disappear out
from under them.
"""
import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_IDLE_TIMEOUT_S = 1800.0  # 30 minutes
DEFAULT_SWEEP_INTERVAL_S = 60.0


def idle_timeout_s() -> float:
    """Read the idle timeout from FLYTO_SESSION_IDLE_TIMEOUT_S, or the default."""
    raw = os.environ.get("FLYTO_SESSION_IDLE_TIMEOUT_S")
    if not raw:
        return DEFAULT_IDLE_TIMEOUT_S
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_IDLE_TIMEOUT_S


def touch_session(activity: Dict[str, float], session_id: Optional[str]) -> None:
    """Record that a session was just used. No-op if session_id is falsy."""
    if session_id:
        activity[session_id] = time.time()


def untrack_session(activity: Dict[str, float], session_id: Optional[str]) -> None:
    """Stop tracking a session (it was explicitly closed/detached)."""
    if session_id:
        activity.pop(session_id, None)


async def _close_browser(driver: Any) -> None:
    try:
        await driver.close()
    except Exception:
        logger.debug("Reaper: browser session close failed", exc_info=True)


async def _close_debugger(session: Any) -> None:
    try:
        await session.detach()
    except Exception:
        logger.debug("Reaper: debugger session detach failed", exc_info=True)


async def reap_stale_sessions(
    browser_sessions: Dict[str, Any],
    debugger_sessions: Dict[str, Any],
    activity: Dict[str, float],
    timeout_s: float,
) -> None:
    """One sweep: close/detach and drop any session idle past timeout_s."""
    now = time.time()
    stale_ids = [session_id for session_id, last in list(activity.items()) if now - last > timeout_s]

    for session_id in stale_ids:
        if session_id in debugger_sessions:
            logger.info("Reaper: closing idle debugger session %s", session_id)
            await _close_debugger(debugger_sessions.pop(session_id))
        if session_id in browser_sessions:
            logger.info("Reaper: closing idle browser session %s", session_id)
            await _close_browser(browser_sessions.pop(session_id))
        activity.pop(session_id, None)


async def reaper_loop(
    browser_sessions: Dict[str, Any],
    debugger_sessions: Dict[str, Any],
    activity: Dict[str, float],
    interval_s: float = DEFAULT_SWEEP_INTERVAL_S,
    timeout_s: Optional[float] = None,
) -> None:
    """Run reap_stale_sessions on a fixed interval until cancelled.

    Intended to be wrapped in asyncio.create_task() by each transport's
    entry point and cancelled (with the cancellation awaited) on shutdown.
    """
    timeout = timeout_s if timeout_s is not None else idle_timeout_s()
    try:
        while True:
            await asyncio.sleep(interval_s)
            try:
                await reap_stale_sessions(browser_sessions, debugger_sessions, activity, timeout)
            except Exception:
                logger.exception("Session reaper sweep failed")
    except asyncio.CancelledError:
        pass
