"""
E2E tests for the reverse.* CDP debugger modules (Phase 1).

Real BrowserDriver + real CDP session against a locally served HTML page.
Covers sub-phase A (attach/scripts/detach) and sub-phase B (breakpoint,
pause/resume) from the build sequencing in the reverse.* debugger plan.
"""
import asyncio
import functools
import http.server
import os
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
        "reverse.breakpoint", "reverse.wait_paused", "reverse.resume",
        "reverse.step", "reverse.get_call_frames", "reverse.evaluate_on_call_frame",
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
    """Serve PAGE_HTML on a random local port."""
    tmpdir = tempfile.mkdtemp()
    (Path(tmpdir) / "reverse_test.html").write_text(PAGE_HTML, encoding="utf-8")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=tmpdir)
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    with allow_local_http_port_for_test(port):
        yield f"http://127.0.0.1:{port}/reverse_test.html"
    srv.shutdown()


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
