"""
E2E tests for the reverse.* CDP debugger modules (Phase 1 + Phase 2).

Real BrowserDriver + real CDP session against a locally served HTML page.
Covers sub-phase A (attach/scripts/detach) and sub-phase B (breakpoint,
pause/resume) from Phase 1, plus sub-phases C/D/E (function hooking,
network-initiator tracing, WebSocket capture) from Phase 2.
"""
import asyncio
import base64
import functools
import hashlib
import http.server
import json
import os
import socket
import struct
import sys
import tempfile
import threading
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
os.environ.setdefault("FLYTO_ENV", "test")

from core.modules import atomic  # noqa: F401 — triggers registration
from core.modules.registry import ModuleRegistry
from tests.conftest import allow_local_http_port_for_test


def get_module(mid):
    cls = ModuleRegistry.get(mid)
    assert cls is not None, f"{mid} not registered"
    return cls


async def run(module_id: str, params: dict, ctx: dict) -> dict:
    """Instantiate module (auto-validates), execute, return result."""
    cls = get_module(module_id)
    mod = cls(params, ctx)  # BaseModule.__init__ calls validate_params()
    result = await mod.execute()
    assert result is not None, f"{module_id} returned None"
    return result


# ─── Registration Tests ──────────────────────────────────────────────────

class TestRegistration:
    @pytest.mark.parametrize("mid", [
        "reverse.attach", "reverse.detach", "reverse.scripts",
        "reverse.breakpoint", "reverse.request_breakpoint",
        "reverse.wait_paused", "reverse.resume",
        "reverse.step", "reverse.get_call_frames", "reverse.evaluate_on_call_frame",
        "reverse.hook", "reverse.network", "reverse.websocket",
    ])
    def test_registered(self, mid):
        meta = ModuleRegistry.get_metadata(mid)
        assert meta is not None
        assert meta["required_permissions"] == ["browser.debug"]
        assert meta["category"] == "reverse"


# ─── Test HTML: a named function with a breakpoint-able line ─────────────

PAGE_HTML = """<!DOCTYPE html>
<html>
<head><title>Reverse Test Page</title></head>
<body>
<div id="result">not-run</div>
<script>
function computeSecret(x) {
  var localVar = x * 2;
  window.__secret = localVar;
  document.getElementById('result').innerText = 'done:' + localVar;
  return localVar;
}
window.__computeSecretMarker = 'reverse-modules-test-marker';

function triggerFetch() {
  return fetch('/ping.json').then(function(r) { return r.json(); });
}
</script>
</body>
</html>
"""

# Zero-based line number CDP expects — computed, not hardcoded, so
# reformatting the HTML above can't silently desync the breakpoint.
BREAKPOINT_LINE = PAGE_HTML.split("\n").index("  var localVar = x * 2;")


@pytest.fixture(scope="module")
def event_loop():
    """Single event loop for all tests — browser/CDP session persists."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def local_server():
    """Serve PAGE_HTML (plus a companion JSON endpoint for network tracing) on a random local port."""
    tmpdir = tempfile.mkdtemp()
    (Path(tmpdir) / "reverse_test.html").write_text(PAGE_HTML, encoding="utf-8")
    (Path(tmpdir) / "ping.json").write_text('{"ok": true}', encoding="utf-8")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=tmpdir)
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    with allow_local_http_port_for_test(port):
        yield f"http://127.0.0.1:{port}/reverse_test.html"
    srv.shutdown()


# ─── Minimal stdlib-only WebSocket echo server (RFC 6455) ────────────────
# No new pip dependency — `websockets` is present in some dev sandboxes only
# as a transitive dep of unrelated tools and must not be relied on in CI.

_WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _ws_accept_key(key: str) -> str:
    digest = hashlib.sha1((key + _WS_MAGIC).encode("utf-8")).digest()
    return base64.b64encode(digest).decode("utf-8")


def _recv_ws_frame(conn):
    header = conn.recv(2)
    if len(header) < 2:
        return None, None
    b1, b2 = header[0], header[1]
    opcode = b1 & 0x0F
    masked = (b2 & 0x80) != 0
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack(">H", conn.recv(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", conn.recv(8))[0]
    mask_key = conn.recv(4) if masked else None
    data = b""
    while len(data) < length:
        chunk = conn.recv(length - len(data))
        if not chunk:
            break
        data += chunk
    if masked:
        data = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))
    return opcode, data


def _send_ws_frame(conn, opcode: int, payload: bytes):
    b1 = 0x80 | opcode  # FIN + opcode
    length = len(payload)
    if length < 126:
        header = bytes([b1, length])
    elif length < 65536:
        header = bytes([b1, 126]) + struct.pack(">H", length)
    else:
        header = bytes([b1, 127]) + struct.pack(">Q", length)
    conn.sendall(header + payload)


def _ws_serve_one(sock):
    """Accept exactly one connection, handshake, and echo text frames until close."""
    conn, _ = sock.accept()
    try:
        request = b""
        while b"\r\n\r\n" not in request:
            chunk = conn.recv(4096)
            if not chunk:
                return
            request += chunk
        key = None
        for line in request.decode("utf-8", errors="replace").split("\r\n"):
            if line.lower().startswith("sec-websocket-key:"):
                key = line.split(":", 1)[1].strip()
        if not key:
            return
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {_ws_accept_key(key)}\r\n\r\n"
        )
        conn.sendall(response.encode("utf-8"))
        while True:
            opcode, data = _recv_ws_frame(conn)
            if opcode is None:
                break
            if opcode == 0x8:  # close
                _send_ws_frame(conn, 0x8, b"")
                break
            if opcode == 0x1:  # text frame — echo back
                _send_ws_frame(conn, 0x1, data)
    finally:
        conn.close()


@pytest.fixture(scope="module")
def ws_server():
    """Minimal local WebSocket echo server for capture tests."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]

    def _serve_forever():
        while True:
            try:
                _ws_serve_one(sock)
            except OSError:
                break

    t = threading.Thread(target=_serve_forever, daemon=True)
    t.start()
    with allow_local_http_port_for_test(port):
        yield f"ws://127.0.0.1:{port}/"
    try:
        sock.close()
    except Exception:
        pass


@pytest_asyncio.fixture(scope="module")
async def ctx(local_server):
    """Launch a real browser, navigate to the test page, yield shared context."""
    from core.browser.driver import BrowserDriver

    driver = BrowserDriver(headless=True)
    await driver.launch(stealth=False)
    context = {"browser": driver}

    await run("browser.goto", {"url": local_server}, context)

    yield context

    session = context.get("reverse_session")
    if session:
        try:
            await session.detach()
        except Exception:
            pass
    try:
        await driver.close()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
#  Sub-phase A — plumbing + read-only inspection
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.browser
@pytest.mark.asyncio(loop_scope="module")
class TestReverseSubPhaseA:

    async def test_01_attach(self, ctx, local_server):
        result = await run("reverse.attach", {}, ctx)
        assert result["status"] == "success"
        assert result["url"] == local_server
        assert ctx.get("reverse_session") is not None

        # Give scriptParsed events (fired on Debugger.enable backfill) a tick
        # to arrive — they're separate CDP notifications from the enable ack.
        await asyncio.sleep(0.3)

    async def test_02_list_scripts_shows_inline_script(self, ctx, local_server):
        result = await run("reverse.scripts", {"action": "list"}, ctx)
        assert result["status"] == "success"
        matching = [s for s in result["scripts"] if s["url"] == local_server]
        assert matching, f"Expected a script with url={local_server}, got {result['scripts']}"
        ctx["_script_id"] = matching[0]["scriptId"]

    async def test_03_get_source_roundtrips_exact_text(self, ctx):
        script_id = ctx["_script_id"]
        result = await run("reverse.scripts", {"action": "get_source", "script_id": script_id}, ctx)
        assert result["status"] == "success"
        assert "function computeSecret(x)" in result["source"]
        assert "reverse-modules-test-marker" in result["source"]

    async def test_04_search_finds_known_string(self, ctx):
        result = await run("reverse.scripts", {
            "action": "search",
            "query": "computeSecret",
        }, ctx)
        assert result["status"] == "success"
        assert result["count"] >= 1
        assert any("computeSecret" in m["lineContent"] for entry in result["matches"] for m in entry["matches"])

    async def test_05_detach_leaves_page_functional(self, ctx):
        result = await run("reverse.detach", {}, ctx)
        assert result["status"] == "success"
        assert ctx.get("reverse_session") is None

        # Page must still be usable after detach.
        eval_result = await run("browser.evaluate", {"script": "() => 1 + 1"}, ctx)
        assert eval_result["result"] == 2


# ═══════════════════════════════════════════════════════════════════════════
#  Sub-phase B — breakpoints + pause/resume
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.browser
@pytest.mark.asyncio(loop_scope="module")
class TestReverseSubPhaseB:

    async def test_01_reattach(self, ctx):
        result = await run("reverse.attach", {}, ctx)
        assert result["status"] == "success"
        await asyncio.sleep(0.3)

    async def test_02_set_breakpoint(self, ctx, local_server):
        result = await run("reverse.breakpoint", {
            "action": "set",
            "url": local_server,
            "line_number": BREAKPOINT_LINE,
        }, ctx)
        assert result["status"] == "success"
        assert result["breakpointId"]
        ctx["_breakpoint_id"] = result["breakpointId"]

    async def test_03_trigger_and_wait_paused(self, ctx):
        driver = ctx["browser"]

        # Fire-and-forget: the CDP pause freezes the page's JS, so this
        # evaluate() call will not resolve until reverse.resume runs. Awaiting
        # it directly here would deadlock the test.
        eval_task = asyncio.ensure_future(driver.evaluate("computeSecret(21)"))
        ctx["_eval_task"] = eval_task

        result = await run("reverse.wait_paused", {"timeout_ms": 10000}, ctx)
        assert result["status"] == "success"
        assert result["paused"] is True
        frames = result["callFrames"]
        assert frames, "Expected at least one call frame at the pause point"
        assert frames[0]["functionName"] == "computeSecret"
        assert frames[0]["lineNumber"] == BREAKPOINT_LINE
        ctx["_call_frame_id"] = frames[0]["callFrameId"]

    async def test_04_get_call_frames_matches_pause(self, ctx):
        result = await run("reverse.get_call_frames", {}, ctx)
        assert result["status"] == "success"
        assert result["callFrames"]
        assert result["callFrames"][0]["functionName"] == "computeSecret"

    async def test_05_evaluate_on_call_frame_reads_param(self, ctx):
        result = await run("reverse.evaluate_on_call_frame", {
            "call_frame_id": ctx["_call_frame_id"],
            "expression": "x",
        }, ctx)
        assert result["status"] == "success"
        assert result["result"]["value"] == 21

    async def test_06_resume_lets_execution_continue(self, ctx):
        result = await run("reverse.resume", {}, ctx)
        assert result["status"] == "success"

        # The evaluate() call fired in test_03 can now complete.
        secret_value = await asyncio.wait_for(ctx["_eval_task"], timeout=5)
        assert secret_value == 42

        # Confirm via a subsequent DOM check that the function actually ran.
        dom_result = await run("browser.evaluate", {
            "script": "() => document.getElementById('result').innerText",
        }, ctx)
        assert dom_result["result"] == "done:42"

    async def test_07_remove_breakpoint(self, ctx):
        result = await run("reverse.breakpoint", {
            "action": "remove",
            "breakpoint_id": ctx["_breakpoint_id"],
        }, ctx)
        assert result["status"] == "success"

    async def test_08_detach(self, ctx):
        result = await run("reverse.detach", {}, ctx)
        assert result["status"] == "success"


# ═══════════════════════════════════════════════════════════════════════════
#  Sub-phase C — function hooking
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.browser
@pytest.mark.asyncio(loop_scope="module")
class TestReverseSubPhaseC:

    async def test_01_reattach(self, ctx):
        result = await run("reverse.attach", {}, ctx)
        assert result["status"] == "success"

    async def test_02_install_hook(self, ctx):
        result = await run("reverse.hook", {
            "action": "install",
            "function_path": "window.Math.max",
        }, ctx)
        assert result["status"] == "success"
        assert result["hookId"]
        ctx["_hook_id"] = result["hookId"]

    async def test_03_call_and_get_records(self, ctx):
        driver = ctx["browser"]
        value = await driver.evaluate("Math.max(1, 2, 3)")
        assert value == 3

        result = await run("reverse.hook", {
            "action": "get_records",
            "hook_id": ctx["_hook_id"],
        }, ctx)
        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["records"][0]["args"] == [1, 2, 3]
        assert result["records"][0]["result"] == 3

    async def test_04_hook_survives_reload(self, ctx):
        await ctx["browser"].real_page.reload(wait_until="load")

        value = await ctx["browser"].evaluate("Math.max(10, 20)")
        assert value == 20

        result = await run("reverse.hook", {
            "action": "get_records",
            "hook_id": ctx["_hook_id"],
        }, ctx)
        assert result["status"] == "success"
        # Fresh document after reload — only the post-reload call is present.
        assert result["count"] == 1
        assert result["records"][0]["args"] == [10, 20]
        assert result["records"][0]["result"] == 20

    async def test_05_list_hooks(self, ctx):
        result = await run("reverse.hook", {"action": "list"}, ctx)
        assert result["status"] == "success"
        assert any(h["hookId"] == ctx["_hook_id"] for h in result["hooks"])

    async def test_06_remove_hook(self, ctx):
        result = await run("reverse.hook", {
            "action": "remove",
            "hook_id": ctx["_hook_id"],
        }, ctx)
        assert result["status"] == "success"

    async def test_07_removed_hook_does_not_reapply_after_reload(self, ctx):
        await ctx["browser"].real_page.reload(wait_until="load")

        value = await ctx["browser"].evaluate("Math.max(100, 200)")
        assert value == 200  # original Math.max, unaffected

        result = await run("reverse.hook", {
            "action": "get_records",
            "hook_id": ctx["_hook_id"],
        }, ctx)
        assert result["status"] == "success"
        assert result["count"] == 0

    async def test_08_hook_survives_lazy_definition(self, ctx):
        # Install a hook on a property that doesn't exist yet — unlike a
        # direct property wrap, the Object.defineProperty trap installs
        # regardless, and only starts recording once the page assigns it.
        result = await run("reverse.hook", {
            "action": "install",
            "function_path": "window.lazyAppFn",
        }, ctx)
        assert result["status"] == "success"
        hook_id = result["hookId"]

        driver = ctx["browser"]
        value = await driver.evaluate("() => { window.lazyAppFn = function(a, b) { return a + b; }; return window.lazyAppFn(2, 3); }")
        assert value == 5

        records = await run("reverse.hook", {"action": "get_records", "hook_id": hook_id}, ctx)
        assert records["status"] == "success"
        assert records["count"] == 1
        assert records["records"][0]["args"] == [2, 3]
        assert records["records"][0]["result"] == 5

        ctx["_lazy_hook_id"] = hook_id

    async def test_09_hook_survives_reassignment(self, ctx):
        # The page overwrites the same property a second time — the hook
        # must re-wrap the new function and keep recording, not silently
        # stop after the first reassignment.
        driver = ctx["browser"]
        value = await driver.evaluate("() => { window.lazyAppFn = function(a, b) { return a * b; }; return window.lazyAppFn(4, 5); }")
        assert value == 20

        records = await run("reverse.hook", {
            "action": "get_records",
            "hook_id": ctx["_lazy_hook_id"],
        }, ctx)
        assert records["status"] == "success"
        assert records["count"] == 2
        assert records["records"][1]["args"] == [4, 5]
        assert records["records"][1]["result"] == 20

        await run("reverse.hook", {"action": "remove", "hook_id": ctx["_lazy_hook_id"]}, ctx)

    async def test_10_detach(self, ctx):
        result = await run("reverse.detach", {}, ctx)
        assert result["status"] == "success"


# ═══════════════════════════════════════════════════════════════════════════
#  Sub-phase D — network-initiator tracing
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.browser
@pytest.mark.asyncio(loop_scope="module")
class TestReverseSubPhaseD:

    async def test_01_reattach(self, ctx, local_server):
        # A fresh reload put the page back at its original URL/state after
        # sub-phase C's hook-removal reload.
        await ctx["browser"].real_page.goto(local_server, wait_until="load")
        result = await run("reverse.attach", {}, ctx)
        assert result["status"] == "success"

    async def test_02_start_tracing(self, ctx):
        result = await run("reverse.network", {"action": "start"}, ctx)
        assert result["status"] == "success"

    async def test_03_trigger_fetch_and_list(self, ctx):
        driver = ctx["browser"]
        fetch_result = await driver.evaluate("triggerFetch()")
        assert fetch_result == {"ok": True}

        result = await run("reverse.network", {"action": "list"}, ctx)
        assert result["status"] == "success"
        matching = [r for r in result["requests"] if "ping.json" in r["url"]]
        assert matching, f"Expected a ping.json request, got {result['requests']}"
        ctx["_request_id"] = matching[0]["requestId"]

    async def test_04_get_initiator_names_triggering_function(self, ctx):
        result = await run("reverse.network", {
            "action": "get_initiator",
            "request_id": ctx["_request_id"],
        }, ctx)
        assert result["status"] == "success"
        assert result["type"] == "script"
        function_names = [f["functionName"] for f in result["stack"]]
        assert "triggerFetch" in function_names, function_names

    async def test_05_stop_tracing(self, ctx):
        result = await run("reverse.network", {"action": "stop"}, ctx)
        assert result["status"] == "success"

    async def test_06_detach(self, ctx):
        result = await run("reverse.detach", {}, ctx)
        assert result["status"] == "success"


# ═══════════════════════════════════════════════════════════════════════════
#  Sub-phase E — WebSocket capture
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.browser
@pytest.mark.asyncio(loop_scope="module")
class TestReverseSubPhaseE:

    async def test_01_reattach(self, ctx):
        result = await run("reverse.attach", {}, ctx)
        assert result["status"] == "success"

    async def test_02_start_capture(self, ctx):
        result = await run("reverse.websocket", {"action": "start"}, ctx)
        assert result["status"] == "success"

    async def test_03_connect_send_and_receive(self, ctx, ws_server):
        driver = ctx["browser"]
        script = (
            "() => new Promise((resolve, reject) => {"
            f"const ws = new WebSocket({json.dumps(ws_server)});"
            "ws.onopen = () => { ws.send('hello-from-test'); };"
            "ws.onmessage = (evt) => { resolve(evt.data); };"
            "ws.onerror = () => reject(new Error('ws error'));"
            "setTimeout(() => reject(new Error('timeout')), 5000);"
            "})"
        )
        result = await driver.evaluate(script)
        assert result == "hello-from-test"

    async def test_04_list_and_get_frames(self, ctx):
        result = await run("reverse.websocket", {"action": "list"}, ctx)
        assert result["status"] == "success"
        assert result["connections"], "Expected at least one captured websocket connection"
        ctx["_ws_request_id"] = result["connections"][0]["requestId"]

        frames_result = await run("reverse.websocket", {
            "action": "get_frames",
            "request_id": ctx["_ws_request_id"],
        }, ctx)
        assert frames_result["status"] == "success"
        sent = [f for f in frames_result["frames"] if f["direction"] == "sent"]
        received = [f for f in frames_result["frames"] if f["direction"] == "received"]
        assert any("hello-from-test" in f["payloadData"] for f in sent)
        assert any("hello-from-test" in f["payloadData"] for f in received)

    async def test_05_get_frames_filtered_by_direction(self, ctx):
        result = await run("reverse.websocket", {
            "action": "get_frames",
            "request_id": ctx["_ws_request_id"],
            "direction": "received",
        }, ctx)
        assert result["status"] == "success"
        assert all(f["direction"] == "received" for f in result["frames"])

    async def test_06_stop_capture(self, ctx):
        result = await run("reverse.websocket", {"action": "stop"}, ctx)
        assert result["status"] == "success"

    async def test_07_detach(self, ctx):
        result = await run("reverse.detach", {}, ctx)
        assert result["status"] == "success"


# ═══════════════════════════════════════════════════════════════════════════
#  Sub-phase F — request-level breakpoints (DOMDebugger XHR/fetch)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.browser
@pytest.mark.asyncio(loop_scope="module")
class TestReverseSubPhaseF:

    async def test_01_reattach(self, ctx, local_server):
        await ctx["browser"].real_page.goto(local_server, wait_until="load")
        result = await run("reverse.attach", {}, ctx)
        assert result["status"] == "success"

    async def test_02_set_request_breakpoint(self, ctx):
        result = await run("reverse.request_breakpoint", {
            "action": "set",
            "url": "ping.json",
        }, ctx)
        assert result["status"] == "success"
        assert result["url"] == "ping.json"

    async def test_03_list_shows_breakpoint(self, ctx):
        result = await run("reverse.request_breakpoint", {"action": "list"}, ctx)
        assert result["status"] == "success"
        assert any(bp["url"] == "ping.json" for bp in result["breakpoints"])

    async def test_04_trigger_and_wait_paused(self, ctx):
        driver = ctx["browser"]

        # Fire-and-forget, same reasoning as sub-phase B's script breakpoint:
        # the CDP pause freezes the page's JS, so awaiting this directly
        # would deadlock the test.
        eval_task = asyncio.ensure_future(driver.evaluate("triggerFetch()"))
        ctx["_fetch_eval_task"] = eval_task

        result = await run("reverse.wait_paused", {"timeout_ms": 10000}, ctx)
        assert result["status"] == "success"
        assert result["paused"] is True
        assert result["reason"] == "XHR"

    async def test_05_resume_lets_fetch_continue(self, ctx):
        result = await run("reverse.resume", {}, ctx)
        assert result["status"] == "success"

        fetch_result = await asyncio.wait_for(ctx["_fetch_eval_task"], timeout=5)
        assert fetch_result == {"ok": True}

    async def test_06_remove_request_breakpoint(self, ctx):
        result = await run("reverse.request_breakpoint", {
            "action": "remove",
            "url": "ping.json",
        }, ctx)
        assert result["status"] == "success"

        result = await run("reverse.request_breakpoint", {"action": "list"}, ctx)
        assert result["breakpoints"] == []

    async def test_07_detach(self, ctx):
        result = await run("reverse.detach", {}, ctx)
        assert result["status"] == "success"


# ═══════════════════════════════════════════════════════════════════════════
#  Sub-phase G — reverse.attach session-snapshot reuse
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.browser
@pytest.mark.asyncio(loop_scope="module")
class TestReverseSessionReuse:

    async def test_01_attach(self, ctx, local_server):
        await ctx["browser"].real_page.goto(local_server, wait_until="load")
        result = await run("reverse.attach", {}, ctx)
        assert result["status"] == "success"
        assert result["reused"] is False
        await asyncio.sleep(0.3)

    async def test_02_reattach_without_detach_reuses_session(self, ctx, local_server):
        session_before = ctx["reverse_session"]

        bp = await run("reverse.breakpoint", {
            "action": "set",
            "url": local_server,
            "line_number": BREAKPOINT_LINE,
        }, ctx)
        assert bp["status"] == "success"
        ctx["_reuse_breakpoint_id"] = bp["breakpointId"]

        result = await run("reverse.attach", {}, ctx)
        assert result["status"] == "success"
        assert result["reused"] is True
        assert result["breakpointCount"] == 1
        assert ctx["reverse_session"] is session_before

        # The breakpoint set before the redundant reattach must still exist —
        # reuse must not have wiped session state.
        assert any(
            b["breakpointId"] == ctx["_reuse_breakpoint_id"]
            for b in session_before.list_breakpoints()
        )

    async def test_03_force_new_discards_the_reused_session(self, ctx):
        session_before = ctx["reverse_session"]

        result = await run("reverse.attach", {"force_new": True}, ctx)
        assert result["status"] == "success"
        assert result["reused"] is False
        assert ctx["reverse_session"] is not session_before
        # A brand-new session has no breakpoints carried over.
        assert ctx["reverse_session"].list_breakpoints() == []

    async def test_04_detach(self, ctx):
        result = await run("reverse.detach", {}, ctx)
        assert result["status"] == "success"
