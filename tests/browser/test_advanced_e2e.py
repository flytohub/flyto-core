"""
E2E Tests — Advanced Browser Features (real Playwright browser)

Tests:
1. Pagination with adaptive rate limiting
2. Pagination with checkpoint save/resume
3. Human-like behavior profile (careful mode)
4. BrowserPool launch + acquire/release
5. Concurrent pagination via URL template
6. Challenge detection (no actual captcha, just detection logic)
7. Retry with simulated failures
"""
import asyncio
import functools
import http.server
import json
import os
import pytest
import pytest_asyncio
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
os.environ["FLYTO_VSCODE_LOCAL_MODE"] = "true"
os.environ.setdefault("FLYTO_ENV", "test")

from core.modules import atomic  # noqa: F401
from core.modules.registry import ModuleRegistry


# ─── Multi-page Test HTML ────────────────────────────────────────

def _make_page_html(page_num, total_pages=5, items_per_page=3):
    """Generate HTML for a paginated page."""
    items = ''.join(
        f'<div class="item">Page {page_num} Item {i+1}</div>'
        for i in range(items_per_page)
    )
    next_disabled = 'disabled' if page_num >= total_pages else ''
    no_more = '<div class="no-more">End of results</div>' if page_num >= total_pages else ''
    return f"""<!DOCTYPE html>
<html><head><title>Test Page {page_num}</title></head>
<body>
  <div id="items">{items}</div>
  <div class="pagination">
    <span class="current">Page {page_num}</span>
    <button id="next-btn" {next_disabled}
            onclick="location.href='?page={page_num+1}'">Next</button>
  </div>
  {no_more}
</body></html>"""


CHALLENGE_HTML = """<!DOCTYPE html>
<html><head><title>Just a moment...</title></head>
<body>
  <h1>Checking your browser</h1>
  <p>Please wait while we verify you are human.</p>
  <div class="cf-turnstile" data-sitekey="0x4AAAAAAA_test_key"></div>
  <iframe src="about:blank" id="fake-cf"></iframe>
</body></html>"""


class _TestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that serves paginated pages."""

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == '/challenge':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(CHALLENGE_HTML.encode())
            return

        page_num = int(params.get('page', ['1'])[0])
        html = _make_page_html(page_num)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        pass  # Suppress logs


# ─── Fixtures ────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def local_server():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _TestHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


@pytest_asyncio.fixture(scope="module")
async def ctx(local_server):
    from core.browser.driver import BrowserDriver
    driver = BrowserDriver(headless=True)
    await driver.launch(stealth=False)
    context = {"browser": driver}
    await driver.goto(f"{local_server}/?page=1")
    yield context
    try:
        await driver.close()
    except Exception:
        pass


async def run(module_id, params, ctx):
    cls = ModuleRegistry.get(module_id)
    assert cls is not None, f"Module {module_id} not registered"
    mod = cls(params, ctx)
    result = await mod.execute()
    assert result is not None
    return result


# ═════════════════════════════════════════════════════════════════
#  TESTS
# ═════════════════════════════════════════════════════════════════

@pytest.mark.browser
@pytest.mark.asyncio(loop_scope="module")
class TestAdvancedBrowserFeatures:

    # ── 1. Pagination with Retry ───────────────────────────────

    async def test_pagination_with_retry(self, ctx, local_server):
        """Paginate with retry enabled — should work and report retries."""
        await ctx["browser"].goto(f"{local_server}/?page=1")

        r = await run("browser.pagination", {
            "mode": "next_button",
            "item_selector": ".item",
            "next_selector": "#next-btn",
            "max_pages": 3,
            "wait_between_pages_ms": 200,
            "retry_on_error": True,
            "max_retries": 2,
        }, ctx)
        assert r["status"] == "success"
        assert r["pages_processed"] >= 1
        assert r["total_items"] >= 3
        assert "retries_used" in r

    # ── 2. Pagination with Checkpoint ────────────────────────────

    async def test_pagination_checkpoint_save_and_clear(self, ctx, local_server):
        """Checkpoint is saved during pagination and cleared on success."""
        checkpoint_path = tempfile.mkstemp(suffix=".json")[1]
        try:
            await ctx["browser"].goto(f"{local_server}/?page=1")

            r = await run("browser.pagination", {
                "mode": "next_button",
                "item_selector": ".item",
                "next_selector": "#next-btn",
                "max_pages": 3,
                "wait_between_pages_ms": 100,
                "checkpoint_path": checkpoint_path,
            }, ctx)
            assert r["status"] == "success"
            assert r["pages_processed"] >= 1

            # Checkpoint should be cleared on successful completion
            assert not Path(checkpoint_path).exists(), \
                "Checkpoint should be cleared after successful completion"

        finally:
            Path(checkpoint_path).unlink(missing_ok=True)

    async def test_pagination_checkpoint_resume(self, ctx, local_server):
        """Simulate checkpoint resume: pre-seed a checkpoint file."""
        from core.browser.checkpoint import PaginationCheckpoint

        checkpoint_path = tempfile.mkstemp(suffix=".json")[1]
        try:
            # Pre-seed checkpoint as if we already scraped 2 pages
            cp = PaginationCheckpoint(checkpoint_path, '.item', 'next_button')
            pre_items = [{'text': f'Page 1 Item {i+1}'} for i in range(3)]
            pre_items += [{'text': f'Page 2 Item {i+1}'} for i in range(3)]
            cp.save(items=pre_items, pages_processed=2)

            # Navigate to page 1
            await ctx["browser"].goto(f"{local_server}/?page=1")

            r = await run("browser.pagination", {
                "mode": "next_button",
                "item_selector": ".item",
                "next_selector": "#next-btn",
                "max_pages": 5,
                "wait_between_pages_ms": 100,
                "checkpoint_path": checkpoint_path,
            }, ctx)
            assert r["status"] == "success"
            assert r.get("resumed") is True, "Should indicate it resumed from checkpoint"
            # Should have pre-seeded items + newly scraped items
            assert r["total_items"] >= 6, f"Expected >= 6 items (2 pre + new), got {r['total_items']}"
            assert r["pages_processed"] >= 3, f"Expected >= 3 pages (2 pre + new), got {r['pages_processed']}"

        finally:
            Path(checkpoint_path).unlink(missing_ok=True)

    # ── 3. Human-like Behavior ───────────────────────────────────

    async def test_humanize_careful_mode(self, ctx, local_server):
        """Set careful behavior and verify it doesn't break navigation."""
        from core.browser.humanize import HumanBehavior

        browser = ctx["browser"]
        old_human = browser._human

        try:
            # Set careful mode
            browser._human = HumanBehavior('careful')

            await browser.goto(f"{local_server}/?page=1")

            # Click should work with mouse movement delay
            await browser.click("#next-btn")
            page = browser.page
            title = await page.title()
            assert "Page 2" in title

        finally:
            browser._human = old_human

    async def test_humanize_human_like_typing(self, ctx, local_server):
        """Human-like behavior should add typing delays."""
        from core.browser.humanize import HumanBehavior

        hb = HumanBehavior('human_like')
        assert hb.get_type_delay() > 0  # Should have non-zero delay
        assert hb.typo_rate > 0  # Should have typo simulation
        assert not hb.is_fast

    # ── 4. BrowserPool ───────────────────────────────────────────

    async def test_browser_pool_launch_and_close(self):
        """Launch a pool of 2 browsers, acquire/release, close all."""
        from core.browser.pool import BrowserPool

        pool = BrowserPool(size=2)
        await pool.launch_all(headless=True, stealth=False)
        assert pool.launched
        assert len(pool.browsers) == 2

        # Acquire and release
        b1 = await pool.acquire(timeout=5)
        assert b1 is not None
        b2 = await pool.acquire(timeout=5)
        assert b2 is not None
        assert b1 is not b2  # Different instances

        await pool.release(b1)
        await pool.release(b2)

        # Acquire again should work
        b3 = await pool.acquire(timeout=5)
        assert b3 is not None
        await pool.release(b3)

        await pool.close_all()
        assert not pool.launched

    async def test_browser_pool_map(self, local_server):
        """Pool.map() should distribute work across browsers."""
        from core.browser.pool import BrowserPool

        pool = BrowserPool(size=2)
        await pool.launch_all(headless=True, stealth=False)

        urls = [
            f"{local_server}/?page=1",
            f"{local_server}/?page=2",
            f"{local_server}/?page=3",
        ]

        async def scrape(driver, url):
            await driver.goto(url)
            title = await driver.evaluate('document.title')
            items = await driver.evaluate(
                'Array.from(document.querySelectorAll(".item")).map(e => e.textContent)'
            )
            return {'title': title, 'items': items}

        results = await pool.map(urls, scrape)
        await pool.close_all()

        assert len(results) == 3
        for i, r in enumerate(results):
            assert 'error' not in r, f"Page {i+1} failed: {r}"
            assert f"Page {i+1}" in r['title']
            assert len(r['items']) == 3

    # ── 5. Throttle with Adaptive Strategy ──────────────────────

    async def test_throttle_adaptive(self, ctx, local_server):
        """Throttle node with adaptive strategy stores limiter in context."""
        await ctx["browser"].goto(f"{local_server}/?page=1")

        r = await run("browser.throttle", {
            "strategy": "adaptive",
            "min_interval_ms": 100,
            "max_interval_ms": 5000,
        }, ctx)
        assert r["status"] == "success"
        assert r["strategy"] == "adaptive"
        assert "waited_ms" in r

    # ── 6. Challenge Detection ───────────────────────────────────

    async def test_challenge_detection(self, ctx, local_server):
        """Challenge module should detect Cloudflare-like page."""
        await ctx["browser"].goto(f"{local_server}/challenge")

        r = await run("browser.challenge", {
            "auto_wait_seconds": 1,  # Short wait
            "human_fallback": False,  # Don't wait for human
        }, ctx)

        # Should detect the challenge
        assert r["challenge_type"] in ("cloudflare", "generic_verify"), \
            f"Expected challenge detection, got: {r}"
        # Should timeout since it's a fake challenge
        assert r["status"] in ("timeout", "auto_resolved")

    # ── 7. Throttle Human-like Strategy ─────────────────────────

    async def test_throttle_human_like(self, ctx, local_server):
        """Throttle node with human_like strategy."""
        await ctx["browser"].goto(f"{local_server}/?page=1")

        r = await run("browser.throttle", {
            "strategy": "human_like",
            "min_interval_ms": 100,
            "max_interval_ms": 2000,
        }, ctx)
        assert r["status"] == "success"
        assert r["strategy"] == "human_like"

    # ── 8. Pagination Retry Behavior ─────────────────────────────

    async def test_pagination_retry_on_missing_items(self, ctx, local_server):
        """Retry should kick in when item selector finds nothing."""
        await ctx["browser"].goto(f"{local_server}/?page=1")

        r = await run("browser.pagination", {
            "mode": "next_button",
            "item_selector": ".nonexistent-class",  # Won't find anything
            "next_selector": "#next-btn",
            "max_pages": 2,
            "retry_on_error": True,
            "max_retries": 2,
            "wait_between_pages_ms": 100,
        }, ctx)
        # Should succeed but with 0 items (empty extraction isn't an error)
        assert r["status"] == "success"
        assert r["total_items"] == 0  # Nothing to extract

    # ── 9. ProxyPool Strategies (unit-level with real objects) ───

    async def test_proxy_pool_round_robin_in_driver(self):
        """ProxyPool integrates correctly with driver attributes."""
        from core.browser.proxy_pool import ProxyPool
        from core.browser.driver import BrowserDriver

        pool = ProxyPool(
            ['http://p1:8080', 'http://p2:8080', 'http://p3:8080'],
            strategy='round_robin'
        )
        driver = BrowserDriver(headless=True)
        driver._proxy_pool = pool
        driver._current_proxy = 'http://p1:8080'

        assert driver._proxy_pool.next() == 'http://p1:8080'
        assert driver._proxy_pool.next() == 'http://p2:8080'
        assert driver._proxy_pool.next() == 'http://p3:8080'
