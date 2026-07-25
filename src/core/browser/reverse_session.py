# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
ReverseSession - CDP Debugger wrapper for interactive JS debugging.

Thin Playwright/CDP wrapper, sibling of BrowserDriver. Owns a single CDP
session against a page's Debugger domain: script inventory, breakpoints,
and pause/resume/step state. Has no BaseModule knowledge — the reverse.*
modules translate params <-> these methods.

CDP freeze caveat: while paused at a breakpoint, the browser freezes the
page's JS/renderer. Other browser.* steps issued before resume() will block
until their own timeout. See DECISIONS.md.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Bound how many matches search_scripts collects per script so a broad query
# against a large bundle can't blow up the response.
_MAX_SEARCH_MATCHES_PER_SCRIPT = 200


class ReverseSession:
    """CDP Debugger session for one page: scripts, breakpoints, pause/resume/step."""

    def __init__(self, driver: Any):
        """
        Args:
            driver: BrowserDriver instance. Uses driver.real_page (not driver.page)
                    so a prior browser.frame step pointing _page at a Frame doesn't
                    break CDP session creation, which requires a real Page.
        """
        self._driver = driver
        self._cdp = None
        self._page = None
        self._scripts: Dict[str, dict] = {}
        self._breakpoints: Dict[str, dict] = {}
        self._paused_event = asyncio.Event()
        self._last_pause: Optional[dict] = None
        self._enabled = False

    @property
    def is_paused(self) -> bool:
        return self._paused_event.is_set()

    async def enable(self) -> Dict[str, Any]:
        """Attach a CDP session to the driver's real page and enable the Debugger domain."""
        page = self._driver.real_page
        if page is None:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        self._page = page
        self._cdp = await page.context.new_cdp_session(page)

        # Listeners MUST be registered before Debugger.enable is sent — Chrome
        # backfills Debugger.scriptParsed for every already-parsed script as
        # part of enabling the domain, and those events can arrive before the
        # enable command's own response if the listener isn't already wired.
        self._cdp.on('Debugger.scriptParsed', self._on_script_parsed)
        self._cdp.on('Debugger.paused', self._on_paused)
        self._cdp.on('Debugger.resumed', self._on_resumed)

        await self._cdp.send('Debugger.enable')

        self._enabled = True
        logger.info("Reverse debugger attached (url=%s)", page.url)

        return {
            'status': 'success',
            'url': page.url,
        }

    async def detach(self) -> Dict[str, Any]:
        """Detach the CDP session. Best-effort — always safe to call, even mid-pause."""
        if not self._enabled:
            return {'status': 'success', 'note': 'not attached'}

        try:
            if self._cdp:
                try:
                    self._cdp.remove_listener('Debugger.scriptParsed', self._on_script_parsed)
                    self._cdp.remove_listener('Debugger.paused', self._on_paused)
                    self._cdp.remove_listener('Debugger.resumed', self._on_resumed)
                except Exception:
                    pass
                try:
                    await self._cdp.detach()
                except Exception:
                    logger.debug("CDP detach failed (session may already be gone)", exc_info=True)
        finally:
            self._enabled = False
            self._cdp = None
            self._paused_event.clear()
            self._last_pause = None

        return {'status': 'success'}

    # -------------------------------------------------------------------
    # CDP event handlers
    # -------------------------------------------------------------------

    async def _on_script_parsed(self, params: dict) -> None:
        script_id = params.get('scriptId')
        if not script_id:
            return
        self._scripts[script_id] = {
            'scriptId': script_id,
            'url': params.get('url', ''),
            'startLine': params.get('startLine'),
            'startColumn': params.get('startColumn'),
            'endLine': params.get('endLine'),
            'endColumn': params.get('endColumn'),
            'hash': params.get('hash'),
            'isModule': params.get('isModule', False),
            'sourceMapURL': params.get('sourceMapURL'),
        }

    async def _on_paused(self, params: dict) -> None:
        self._last_pause = self._enrich_pause(params)
        self._paused_event.set()

    async def _on_resumed(self, params: dict) -> None:
        self._paused_event.clear()

    def _enrich_pause(self, params: dict) -> dict:
        """Attach resolved script URLs to each call frame's location."""
        frames = []
        for frame in params.get('callFrames', []):
            location = frame.get('location', {})
            script_id = location.get('scriptId')
            script = self._scripts.get(script_id, {})
            frames.append({
                'callFrameId': frame.get('callFrameId'),
                'functionName': frame.get('functionName', ''),
                'url': script.get('url', ''),
                'scriptId': script_id,
                'lineNumber': location.get('lineNumber'),
                'columnNumber': location.get('columnNumber'),
                'scopeChain': frame.get('scopeChain', []),
                'this': frame.get('this'),
            })
        return {
            'reason': params.get('reason', ''),
            'hitBreakpoints': params.get('hitBreakpoints', []),
            'callFrames': frames,
        }

    # -------------------------------------------------------------------
    # Scripts
    # -------------------------------------------------------------------

    def list_scripts(self) -> List[dict]:
        return sorted(self._scripts.values(), key=lambda s: s.get('url', ''))

    async def get_script_source(self, script_id: str) -> str:
        result = await self._cdp.send('Debugger.getScriptSource', {'scriptId': script_id})
        return result.get('scriptSource', '')

    async def search_scripts(
        self,
        query: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        script_id: Optional[str] = None,
    ) -> List[dict]:
        """Search loaded script sources for `query` via CDP's own search (no hand-rolled grep)."""
        targets = [script_id] if script_id else list(self._scripts.keys())
        results = []
        for sid in targets:
            script = self._scripts.get(sid, {})
            try:
                found = await self._cdp.send('Debugger.searchInContent', {
                    'scriptId': sid,
                    'query': query,
                    'caseSensitive': case_sensitive,
                    'isRegex': is_regex,
                })
            except Exception:
                continue
            matches = found.get('result', [])[:_MAX_SEARCH_MATCHES_PER_SCRIPT]
            if matches:
                results.append({
                    'scriptId': sid,
                    'url': script.get('url', ''),
                    'matches': [
                        {'lineNumber': m.get('lineNumber'), 'lineContent': m.get('lineContent', '')}
                        for m in matches
                    ],
                })
        return results

    # -------------------------------------------------------------------
    # Breakpoints
    # -------------------------------------------------------------------

    async def set_breakpoint(
        self,
        url: Optional[str] = None,
        url_regex: Optional[str] = None,
        line_number: int = 0,
        column_number: int = 0,
        condition: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {'lineNumber': line_number, 'columnNumber': column_number}
        if url_regex:
            params['urlRegex'] = url_regex
        elif url:
            params['url'] = url
        else:
            raise ValueError("set_breakpoint requires either url or url_regex")
        if condition:
            params['condition'] = condition

        result = await self._cdp.send('Debugger.setBreakpointByUrl', params)
        breakpoint_id = result.get('breakpointId')
        entry = {
            'breakpointId': breakpoint_id,
            'url': url,
            'urlRegex': url_regex,
            'lineNumber': line_number,
            'columnNumber': column_number,
            'condition': condition,
            'locations': result.get('locations', []),
        }
        self._breakpoints[breakpoint_id] = entry
        return entry

    async def remove_breakpoint(self, breakpoint_id: str) -> Dict[str, Any]:
        await self._cdp.send('Debugger.removeBreakpoint', {'breakpointId': breakpoint_id})
        self._breakpoints.pop(breakpoint_id, None)
        return {'status': 'success', 'breakpointId': breakpoint_id}

    def list_breakpoints(self) -> List[dict]:
        return list(self._breakpoints.values())

    # -------------------------------------------------------------------
    # Pause / resume / step
    # -------------------------------------------------------------------

    async def wait_paused(self, timeout_s: float) -> Optional[dict]:
        """Block until the page hits a breakpoint (or is already paused). None on timeout."""
        try:
            await asyncio.wait_for(self._paused_event.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return None
        return self._last_pause

    async def resume(self) -> Dict[str, Any]:
        if not self.is_paused:
            return {'status': 'success', 'note': 'not paused'}
        await self._cdp.send('Debugger.resume')
        return {'status': 'success'}

    async def _step(self, cdp_method: str, timeout_s: float) -> Optional[dict]:
        if not self.is_paused:
            raise RuntimeError("Cannot step: debugger is not paused")
        self._paused_event.clear()
        await self._cdp.send(cdp_method)
        try:
            await asyncio.wait_for(self._paused_event.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return None
        return self._last_pause

    async def step_over(self, timeout_s: float) -> Optional[dict]:
        return await self._step('Debugger.stepOver', timeout_s)

    async def step_into(self, timeout_s: float) -> Optional[dict]:
        return await self._step('Debugger.stepInto', timeout_s)

    async def step_out(self, timeout_s: float) -> Optional[dict]:
        return await self._step('Debugger.stepOut', timeout_s)

    # -------------------------------------------------------------------
    # Inspection
    # -------------------------------------------------------------------

    def get_call_frames(self) -> List[dict]:
        if not self._last_pause:
            return []
        return self._last_pause.get('callFrames', [])

    async def evaluate_on_call_frame(self, call_frame_id: str, expression: str) -> Dict[str, Any]:
        result = await self._cdp.send('Debugger.evaluateOnCallFrame', {
            'callFrameId': call_frame_id,
            'expression': expression,
            'returnByValue': True,
        })
        if result.get('exceptionDetails'):
            exc = result['exceptionDetails']
            return {
                'status': 'error',
                'error': exc.get('text', 'Evaluation threw'),
                'exceptionDetails': exc,
            }
        return {
            'status': 'success',
            'result': result.get('result', {}),
        }
