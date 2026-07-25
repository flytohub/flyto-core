# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
ReverseSession - CDP Debugger wrapper for interactive JS debugging.

Thin Playwright/CDP wrapper, sibling of BrowserDriver. Owns a single CDP
session against a page's Debugger, Page, and Network domains: script
inventory, breakpoints, pause/resume/step state, installed function hooks,
and request/WebSocket capture. Has no BaseModule knowledge — the reverse.*
modules translate params <-> these methods.

CDP freeze caveat: while paused at a breakpoint, the browser freezes the
page's JS/renderer. Other browser.* steps issued before resume() will block
until their own timeout. See DECISIONS.md.

Hooking uses an Object.defineProperty(get/set) trap rather than a one-time
direct reassignment, so it also wraps a function the page assigns *after*
our init script runs (not just one that already exists at install time),
and survives the page reassigning the same property afterward — both
re-wrap transparently. The one remaining scope boundary: the property's
*immediate parent* must already exist at document-start (true for
`window.X` and built-in namespaces like `Math`/`JSON`, not for a path whose
parent object is itself lazily created later). A handful of non-configurable
built-ins fall back to a one-time direct wrap (hooks the current value, does
not survive reassignment for that specific property). See DECISIONS.md.
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Bound how many matches search_scripts collects per script so a broad query
# against a large bundle can't blow up the response.
_MAX_SEARCH_MATCHES_PER_SCRIPT = 200

# Bound how many requests/websocket connections and frames-per-connection are
# retained so a chatty page can't grow the session's memory unbounded.
_MAX_NETWORK_REQUESTS = 500
_MAX_WEBSOCKET_FRAMES_PER_CONNECTION = 200

# Placeholder-based template (not an f-string) so the many literal JS braces
# below don't need escaping. Values are substituted via .replace() after
# json.dumps()-encoding any string coming from module params, so a
# function_path containing quotes/backticks can't break out of the snippet.
_HOOK_SCRIPT_TEMPLATE = """
(function() {
  var path = __FUNCTION_PATH__;
  var hookId = __HOOK_ID__;
  var captureArgs = __CAPTURE_ARGS__;
  var captureResult = __CAPTURE_RESULT__;
  var maxRecords = __MAX_RECORDS__;

  window.__flytoHooks = window.__flytoHooks || {};
  window.__flytoHookRestore = window.__flytoHookRestore || {};
  if (window.__flytoHookRestore[hookId]) return;

  var parts = path.split('.');
  var parent = window;
  for (var i = 0; i < parts.length - 1; i++) {
    if (parent == null) { parent = null; break; }
    parent = parent[parts[i]];
  }
  var key = parts[parts.length - 1];
  if (!parent) return;

  window.__flytoHooks[hookId] = [];

  function safeSerialize(v) {
    try { return JSON.parse(JSON.stringify(v)); }
    catch (e) { try { return String(v); } catch (e2) { return null; } }
  }

  function pushRecord(rec) {
    var arr = window.__flytoHooks[hookId];
    arr.push(rec);
    if (arr.length > maxRecords) arr.shift();
  }

  function wrap(fn) {
    if (typeof fn !== 'function') return fn;
    return function() {
      var args = Array.prototype.slice.call(arguments);
      var record = { timestamp: Date.now() };
      if (captureArgs) record.args = args.map(safeSerialize);
      var result;
      try {
        result = fn.apply(this, args);
      } catch (e) {
        record.threw = safeSerialize(e && e.message ? e.message : String(e));
        pushRecord(record);
        throw e;
      }
      pushRecord(record);
      if (captureResult) {
        if (result && typeof result.then === 'function') {
          result.then(function(v) { record.result = safeSerialize(v); })
                .catch(function(e) { record.resultError = safeSerialize(e && e.message ? e.message : String(e)); });
        } else {
          record.result = safeSerialize(result);
        }
      }
      return result;
    };
  }

  // currentRaw/currentWrapped are captured in this closure so the get/set
  // trap below re-wraps every future assignment, not just the value
  // present when the hook was installed — this is what makes the hook
  // survive both "not-yet-defined" and "reassigned later" cases.
  var currentRaw = parent[key];
  var currentWrapped = wrap(currentRaw);

  try {
    Object.defineProperty(parent, key, {
      configurable: true,
      enumerable: true,
      get: function() { return currentWrapped; },
      set: function(fn) {
        currentRaw = fn;
        currentWrapped = wrap(fn);
      },
    });
  } catch (e) {
    // Non-configurable property (some built-ins) — fall back to a one-time
    // direct wrap. Hooks the current value; won't survive reassignment.
    if (typeof parent[key] === 'function') {
      var original = parent[key];
      parent[key] = wrap(original);
      window.__flytoHookRestore[hookId] = function() {
        parent[key] = original;
        delete window.__flytoHookRestore[hookId];
      };
    }
    return;
  }

  window.__flytoHookRestore[hookId] = function() {
    try { delete parent[key]; } catch (e) {}
    parent[key] = currentRaw;
    delete window.__flytoHookRestore[hookId];
  };
})();
"""


class ReverseSession:
    """CDP session for one page: scripts, script-line and request-level
    breakpoints, pause/resume/step, installed function hooks, and
    request/WebSocket capture."""

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

        # Page domain (function hooking via addScriptToEvaluateOnNewDocument)
        self._page_domain_enabled = False
        self._hooks: Dict[str, dict] = {}

        # Network domain (request-initiator tracing + WebSocket capture)
        self._network_enabled = False
        self._requests: Dict[str, dict] = {}
        self._websockets: Dict[str, dict] = {}

        # DOMDebugger request-level breakpoints (XHR/fetch), keyed by the URL
        # substring CDP itself uses as the breakpoint's identity.
        self._request_breakpoints: Dict[str, dict] = {}

    @property
    def is_paused(self) -> bool:
        return self._paused_event.is_set()

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def page(self) -> Any:
        return self._page

    def snapshot(self) -> Dict[str, Any]:
        """Current session state, for a caller deciding whether to reuse this
        session instead of detaching and re-attaching from scratch."""
        return {
            'url': self._page.url if self._page else None,
            'scriptCount': len(self._scripts),
            'breakpointCount': len(self._breakpoints),
            'requestBreakpointCount': len(self._request_breakpoints),
            'hookCount': len(self._hooks),
            'isPaused': self.is_paused,
            'networkEnabled': self._network_enabled,
        }

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
                # Best-effort: stop any installed hooks from re-applying on
                # future navigations. Does not attempt to restore the current
                # page's live bindings — the session (and page, usually) is
                # going away anyway.
                for hook_id, hook in list(self._hooks.items()):
                    try:
                        await self._cdp.send(
                            'Page.removeScriptToEvaluateOnNewDocument',
                            {'identifier': hook['cdpScriptId']},
                        )
                    except Exception:
                        logger.debug("Failed to remove hook %s on detach", hook_id, exc_info=True)

                try:
                    self._cdp.remove_listener('Debugger.scriptParsed', self._on_script_parsed)
                    self._cdp.remove_listener('Debugger.paused', self._on_paused)
                    self._cdp.remove_listener('Debugger.resumed', self._on_resumed)
                    if self._network_enabled:
                        self._cdp.remove_listener('Network.requestWillBeSent', self._on_request_will_be_sent)
                        self._cdp.remove_listener('Network.webSocketCreated', self._on_websocket_created)
                        self._cdp.remove_listener('Network.webSocketFrameSent', self._on_websocket_frame_sent)
                        self._cdp.remove_listener('Network.webSocketFrameReceived', self._on_websocket_frame_received)
                        self._cdp.remove_listener('Network.webSocketClosed', self._on_websocket_closed)
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
            self._page_domain_enabled = False
            self._hooks.clear()
            self._network_enabled = False
            self._requests.clear()
            self._websockets.clear()
            self._request_breakpoints.clear()

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
            # Present for non-script-line pause reasons (e.g. 'XHR' for a
            # request-level breakpoint) — carries reason-specific detail such
            # as the matched URL. Passed through as-is; CDP's shape varies by
            # reason and we don't want to guess at wrong field names.
            'data': params.get('data'),
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
    # Request-level breakpoints (DOMDebugger: pause on XHR/fetch send)
    # -------------------------------------------------------------------

    async def set_request_breakpoint(self, url: str) -> Dict[str, Any]:
        """Pause execution when an XHR/fetch request URL contains `url`
        (empty string matches every request). Unlike script breakpoints,
        CDP has no separate breakpoint-id concept here — the URL substring
        itself is the breakpoint's identity, so setting the same url twice
        is idempotent."""
        await self._cdp.send('DOMDebugger.setXHRBreakpoint', {'url': url})
        entry = {'url': url}
        self._request_breakpoints[url] = entry
        return entry

    async def remove_request_breakpoint(self, url: str) -> Dict[str, Any]:
        await self._cdp.send('DOMDebugger.removeXHRBreakpoint', {'url': url})
        self._request_breakpoints.pop(url, None)
        return {'status': 'success', 'url': url}

    def list_request_breakpoints(self) -> List[dict]:
        return list(self._request_breakpoints.values())

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

    # -------------------------------------------------------------------
    # Function hooking (Page domain: addScriptToEvaluateOnNewDocument)
    # -------------------------------------------------------------------

    async def install_hook(
        self,
        function_path: str,
        capture_args: bool = True,
        capture_result: bool = True,
        max_records: int = 500,
    ) -> Dict[str, Any]:
        """Wrap a JS function so every call/return/throw is recorded.

        Applies both to future navigations (via
        Page.addScriptToEvaluateOnNewDocument, which runs before the page's
        own scripts) and immediately to the current page (via page.evaluate)
        so a function already present on an already-loaded page gets hooked
        too. Only wraps a function that already exists at the time the
        wrapping code runs — see module docstring for the not-yet-defined
        limitation.
        """
        if not self._page_domain_enabled:
            await self._cdp.send('Page.enable')
            self._page_domain_enabled = True

        hook_id = f"hook_{uuid.uuid4().hex[:8]}"
        hook_js = self._build_hook_script(
            function_path, hook_id, capture_args, capture_result, max_records,
        )

        result = await self._cdp.send('Page.addScriptToEvaluateOnNewDocument', {'source': hook_js})

        entry = {
            'hookId': hook_id,
            'functionPath': function_path,
            'cdpScriptId': result.get('identifier'),
            'installedAt': time.time(),
        }
        self._hooks[hook_id] = entry

        try:
            await self._page.evaluate(hook_js)
        except Exception:
            logger.debug(
                "Immediate hook application failed for %s (target may not exist yet)",
                function_path, exc_info=True,
            )

        return entry

    async def remove_hook(self, hook_id: str) -> Dict[str, Any]:
        entry = self._hooks.get(hook_id)
        if not entry:
            return {'status': 'success', 'note': 'hook not found', 'hookId': hook_id}

        try:
            await self._cdp.send(
                'Page.removeScriptToEvaluateOnNewDocument',
                {'identifier': entry['cdpScriptId']},
            )
        except Exception:
            logger.debug("Failed to remove init script for hook %s", hook_id, exc_info=True)

        hook_id_js = json.dumps(hook_id)
        restore_script = (
            "() => {"
            "  if (window.__flytoHookRestore && window.__flytoHookRestore[" + hook_id_js + "]) {"
            "    window.__flytoHookRestore[" + hook_id_js + "]();"
            "  }"
            "}"
        )
        try:
            await self._page.evaluate(restore_script)
        except Exception:
            logger.debug("Failed to restore original function for hook %s", hook_id, exc_info=True)

        self._hooks.pop(hook_id, None)
        return {'status': 'success', 'hookId': hook_id}

    def list_hooks(self) -> List[dict]:
        return list(self._hooks.values())

    async def get_hook_records(self, hook_id: str, clear: bool = False) -> List[dict]:
        hook_id_js = json.dumps(hook_id)
        clear_js = 'true' if clear else 'false'
        script = (
            "() => {"
            "  var arr = (window.__flytoHooks && window.__flytoHooks[" + hook_id_js + "]) || [];"
            "  var copy = arr.slice();"
            "  if (" + clear_js + " && window.__flytoHooks) { window.__flytoHooks[" + hook_id_js + "] = []; }"
            "  return copy;"
            "}"
        )
        return await self._page.evaluate(script)

    def _build_hook_script(
        self,
        function_path: str,
        hook_id: str,
        capture_args: bool,
        capture_result: bool,
        max_records: int,
    ) -> str:
        script = _HOOK_SCRIPT_TEMPLATE
        script = script.replace('__FUNCTION_PATH__', json.dumps(function_path))
        script = script.replace('__HOOK_ID__', json.dumps(hook_id))
        script = script.replace('__CAPTURE_ARGS__', 'true' if capture_args else 'false')
        script = script.replace('__CAPTURE_RESULT__', 'true' if capture_result else 'false')
        script = script.replace('__MAX_RECORDS__', str(int(max_records)))
        return script

    # -------------------------------------------------------------------
    # Network (request-initiator tracing + WebSocket capture)
    # -------------------------------------------------------------------

    async def enable_network(self) -> None:
        """Enable the Network domain. Idempotent — safe to call from both
        reverse.network and reverse.websocket."""
        if self._network_enabled:
            return

        # Listeners before Network.enable, same reasoning as Debugger.enable
        # in enable() — consistent practice even though Network domain has no
        # equivalent scriptParsed-style backfill for already-sent requests.
        self._cdp.on('Network.requestWillBeSent', self._on_request_will_be_sent)
        self._cdp.on('Network.webSocketCreated', self._on_websocket_created)
        self._cdp.on('Network.webSocketFrameSent', self._on_websocket_frame_sent)
        self._cdp.on('Network.webSocketFrameReceived', self._on_websocket_frame_received)
        self._cdp.on('Network.webSocketClosed', self._on_websocket_closed)

        await self._cdp.send('Network.enable')
        self._network_enabled = True

    async def disable_network(self) -> None:
        if not self._network_enabled:
            return
        try:
            self._cdp.remove_listener('Network.requestWillBeSent', self._on_request_will_be_sent)
            self._cdp.remove_listener('Network.webSocketCreated', self._on_websocket_created)
            self._cdp.remove_listener('Network.webSocketFrameSent', self._on_websocket_frame_sent)
            self._cdp.remove_listener('Network.webSocketFrameReceived', self._on_websocket_frame_received)
            self._cdp.remove_listener('Network.webSocketClosed', self._on_websocket_closed)
        except Exception:
            pass
        try:
            await self._cdp.send('Network.disable')
        except Exception:
            logger.debug("Network.disable failed", exc_info=True)
        self._network_enabled = False

    async def _on_request_will_be_sent(self, params: dict) -> None:
        request_id = params.get('requestId')
        if not request_id:
            return
        request = params.get('request', {})
        self._requests[request_id] = {
            'requestId': request_id,
            'url': request.get('url', ''),
            'method': request.get('method', ''),
            'resourceType': params.get('type', ''),
            'timestamp': params.get('timestamp'),
            'initiator': params.get('initiator', {}),
        }
        if len(self._requests) > _MAX_NETWORK_REQUESTS:
            oldest_id = next(iter(self._requests))
            del self._requests[oldest_id]

    def list_requests(self) -> List[dict]:
        return [
            {
                'requestId': r['requestId'],
                'url': r['url'],
                'method': r['method'],
                'resourceType': r['resourceType'],
                'timestamp': r['timestamp'],
            }
            for r in self._requests.values()
        ]

    def get_request_initiator(self, request_id: str) -> Dict[str, Any]:
        entry = self._requests.get(request_id)
        if not entry:
            raise ValueError(f"Unknown request_id: {request_id}")

        initiator = entry.get('initiator', {})
        frames: List[dict] = []

        def _walk(stack: Optional[dict]) -> None:
            if not stack:
                return
            for frame in stack.get('callFrames', []):
                frames.append({
                    'functionName': frame.get('functionName', ''),
                    'url': frame.get('url', ''),
                    'lineNumber': frame.get('lineNumber'),
                    'columnNumber': frame.get('columnNumber'),
                })
            _walk(stack.get('parent'))

        _walk(initiator.get('stack'))

        return {
            'requestId': request_id,
            'type': initiator.get('type', ''),
            'url': initiator.get('url'),
            'stack': frames,
        }

    async def _on_websocket_created(self, params: dict) -> None:
        request_id = params.get('requestId')
        if not request_id:
            return
        self._websockets[request_id] = {
            'requestId': request_id,
            'url': params.get('url', ''),
            'createdAt': time.time(),
            'closedAt': None,
            'frames': [],
        }

    async def _on_websocket_frame_sent(self, params: dict) -> None:
        self._append_websocket_frame(params, direction='sent')

    async def _on_websocket_frame_received(self, params: dict) -> None:
        self._append_websocket_frame(params, direction='received')

    def _append_websocket_frame(self, params: dict, direction: str) -> None:
        conn = self._websockets.get(params.get('requestId'))
        if conn is None:
            return
        payload = params.get('response', {})
        conn['frames'].append({
            'direction': direction,
            'opcode': payload.get('opcode'),
            'payloadData': payload.get('payloadData', ''),
            'timestamp': params.get('timestamp'),
        })
        if len(conn['frames']) > _MAX_WEBSOCKET_FRAMES_PER_CONNECTION:
            conn['frames'].pop(0)

    async def _on_websocket_closed(self, params: dict) -> None:
        conn = self._websockets.get(params.get('requestId'))
        if conn:
            conn['closedAt'] = time.time()

    def list_websockets(self) -> List[dict]:
        return [
            {
                'requestId': ws['requestId'],
                'url': ws['url'],
                'createdAt': ws['createdAt'],
                'closedAt': ws['closedAt'],
                'frameCount': len(ws['frames']),
            }
            for ws in self._websockets.values()
        ]

    def get_websocket_frames(
        self,
        request_id: str,
        direction: str = 'both',
        limit: Optional[int] = None,
    ) -> List[dict]:
        conn = self._websockets.get(request_id)
        if not conn:
            raise ValueError(f"Unknown websocket request_id: {request_id}")

        frames = conn['frames']
        if direction != 'both':
            frames = [f for f in frames if f['direction'] == direction]
        if limit:
            frames = frames[-limit:]
        return frames
