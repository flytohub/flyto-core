"""
Tests for crawl infrastructure modules:
  browser.robots, browser.sitemap, browser.throttle,
  browser.proxy_rotate, browser.login
"""
import pytest
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from core.modules import atomic  # noqa: F401
from core.modules.registry import ModuleRegistry


def get_module(mid):
    cls = ModuleRegistry.get(mid)
    assert cls is not None, f"{mid} not registered"
    return cls


# ─── Registration ────────────────────────────────────────────────────────

class TestRegistration:
    @pytest.mark.parametrize("mid", [
        "browser.robots", "browser.sitemap", "browser.throttle",
        "browser.proxy_rotate", "browser.login",
    ])
    def test_registered(self, mid):
        assert ModuleRegistry.get(mid) is not None


# ─── browser.robots ─────────────────────────────────────────────────────

@pytest.mark.browser
class TestRobotsE2E:
    @pytest.fixture
    async def ctx(self):
        from core.browser.driver import BrowserDriver
        driver = BrowserDriver(headless=True)
        await driver.launch(stealth=False)
        yield {"browser": driver}
        await driver.close()

    @pytest.mark.asyncio
    async def test_robots_on_real_site(self, ctx):
        """Check robots.txt on a real site (GitHub)."""
        await ctx["browser"].page.goto("https://github.com", wait_until="domcontentloaded", timeout=15000)

        mod = get_module("browser.robots")({}, ctx)
        mod.validate_params()
        result = await mod.execute()

        print(f"\n[robots] exists={result['exists']}, rules={result['rule_count']}, sitemaps={len(result['sitemaps'])}")

        assert result["exists"] is True
        assert result["rule_count"] > 0

    @pytest.mark.asyncio
    async def test_robots_check_allowed(self, ctx):
        """Check if a specific URL is allowed."""
        await ctx["browser"].page.goto("https://github.com", wait_until="domcontentloaded", timeout=15000)

        mod = get_module("browser.robots")({"check_url": "/trending"}, ctx)
        mod.validate_params()
        result = await mod.execute()

        print(f"\n[robots] /trending allowed={result['allowed']}, rule='{result['matched_rule']}'")
        # /trending should be allowed on GitHub
        assert result["allowed"] is True


# ─── browser.sitemap ────────────────────────────────────────────────────

@pytest.mark.browser
class TestSitemapE2E:
    @pytest.fixture
    async def ctx(self):
        from core.browser.driver import BrowserDriver
        driver = BrowserDriver(headless=True)
        await driver.launch(stealth=False)
        yield {"browser": driver}
        await driver.close()

    @pytest.mark.asyncio
    async def test_sitemap_with_namespace(self, ctx):
        """Parse a sitemap XML with xmlns namespace (the bug we fixed)."""
        page = ctx["browser"].page

        # Serve a mock sitemap via data URL won't work (fetch fails on data:).
        # Instead, test with a real site's sitemap.
        await page.goto("https://dev.to", wait_until="domcontentloaded", timeout=15000)

        from core.modules.atomic.browser.sitemap import _SITEMAP_JS
        result = await page.evaluate(_SITEMAP_JS, {
            'sitemap_url': 'https://dev.to/sitemap.xml',
            'max_urls': 5,
            'follow_index': True,
        })

        print(f"\n[sitemap] count={result['count']}, is_index={result['is_index']}, error={result.get('error','')}")
        if result['count'] > 0:
            print(f"  first URL: {result['urls'][0].get('url', '?')[:60]}")

        # dev.to should have a sitemap (index or direct)
        if result.get('error'):
            pytest.skip(f"Sitemap fetch failed: {result['error']}")
        assert result["count"] >= 1 or result["is_index"] is True


# ─── browser.throttle ───────────────────────────────────────────────────

@pytest.mark.browser
class TestThrottleE2E:
    @pytest.fixture
    async def ctx(self):
        from core.browser.driver import BrowserDriver
        driver = BrowserDriver(headless=True)
        await driver.launch(stealth=False)
        yield {"browser": driver}
        await driver.close()

    @pytest.mark.asyncio
    async def test_throttle_waits(self, ctx):
        """Second request to same domain should wait."""
        await ctx["browser"].page.goto("https://example.com", wait_until="domcontentloaded", timeout=15000)

        Throttle = get_module("browser.throttle")

        # First request — no wait
        mod1 = Throttle({"min_interval_ms": 1000, "randomize": False}, ctx)
        mod1.validate_params()
        r1 = await mod1.execute()
        assert r1["waited_ms"] == 0  # First request, no history

        # Second request immediately — should wait ~1000ms
        mod2 = Throttle({"min_interval_ms": 1000, "randomize": False}, ctx)
        mod2.validate_params()
        t0 = time.monotonic()
        r2 = await mod2.execute()
        elapsed = (time.monotonic() - t0) * 1000

        print(f"\n[throttle] waited_ms={r2['waited_ms']}, actual_elapsed={elapsed:.0f}ms")

        assert r2["waited_ms"] >= 500, f"Should wait ~1000ms, waited {r2['waited_ms']}ms"
        assert r2["domain"] == "example.com"

    @pytest.mark.asyncio
    async def test_different_domains_no_wait(self, ctx):
        """Different domains should NOT throttle each other."""
        # Reset throttle state
        from core.modules.atomic.browser.throttle import _domain_last_request
        _domain_last_request.clear()

        Throttle = get_module("browser.throttle")

        mod1 = Throttle({"min_interval_ms": 5000, "url": "https://a.example.com/page"}, ctx)
        mod1.validate_params()
        await mod1.execute()

        # Different domain — should NOT wait
        mod2 = Throttle({"min_interval_ms": 5000, "url": "https://b.example.com/page"}, ctx)
        mod2.validate_params()
        r2 = await mod2.execute()

        assert r2["waited_ms"] == 0, "Different domain should not wait"


# ─── browser.proxy_rotate ───────────────────────────────────────────────

class TestProxyRotate:
    """Test proxy rotation logic (no real proxies needed for init/status/mark_dead)."""

    @pytest.mark.asyncio
    async def test_init_and_status(self):
        Proxy = get_module("browser.proxy_rotate")
        ctx = {}

        mod = Proxy({
            "action": "init",
            "proxies": ["http://p1:8080", "http://p2:8080", "socks5://p3:1080"],
        }, ctx)
        mod.validate_params()
        result = await mod.execute()

        assert result["pool_size"] == 3
        assert result["alive"] == 3
        assert result["dead"] == 0

    @pytest.mark.asyncio
    async def test_mark_dead(self):
        Proxy = get_module("browser.proxy_rotate")
        ctx = {}

        # Init
        mod = Proxy({"action": "init", "proxies": ["http://p1:8080", "http://p2:8080"]}, ctx)
        mod.validate_params()
        await mod.execute()

        # Mark dead
        mod2 = Proxy({"action": "mark_dead"}, ctx)
        mod2.validate_params()
        result = await mod2.execute()

        assert result["dead"] == 1
        assert result["alive"] == 1

    @pytest.mark.asyncio
    async def test_rotate_without_init_raises(self):
        Proxy = get_module("browser.proxy_rotate")
        # Reset global state
        from core.modules.atomic.browser.proxy_rotate import _proxy_pool
        _proxy_pool.clear()

        ctx = {}
        mod = Proxy({"action": "rotate"}, ctx)
        mod.validate_params()
        with pytest.raises(ValueError, match="not initialized"):
            await mod.execute()


# ─── browser.login ───────────────────────────────────────────────────────

@pytest.mark.browser
class TestLoginE2E:
    @pytest.fixture
    async def ctx(self):
        from core.browser.driver import BrowserDriver
        driver = BrowserDriver(headless=True)
        await driver.launch(stealth=False)
        yield {"browser": driver}
        await driver.close()

    @pytest.mark.asyncio
    async def test_auto_detect_form_fields(self, ctx):
        """Should auto-detect username, password, and submit fields."""
        page = ctx["browser"].page
        await page.set_content("""
        <html><body>
            <form action="/login" method="POST">
                <input type="email" name="email" placeholder="Email">
                <input type="password" name="password" placeholder="Password">
                <button type="submit">Sign In</button>
            </form>
        </body></html>
        """)

        from core.modules.atomic.browser.login import _LOGIN_JS
        result = await page.evaluate(_LOGIN_JS, {})

        assert result["username_found"] is True
        assert result["password_found"] is True
        assert result["submit_found"] is True

    @pytest.mark.asyncio
    async def test_login_fills_form(self, ctx):
        """Should fill and submit a login form."""
        page = ctx["browser"].page

        # Create a mock login page that shows success on submit
        await page.set_content("""
        <html><body>
            <form id="login-form">
                <input type="email" name="email" id="email">
                <input type="password" name="password" id="pass">
                <button type="submit">Login</button>
            </form>
            <script>
                document.getElementById('login-form').addEventListener('submit', (e) => {
                    e.preventDefault();
                    const email = document.getElementById('email').value;
                    const pass = document.getElementById('pass').value;
                    if (email && pass) {
                        document.title = 'Dashboard - Welcome';
                        document.body.innerHTML = '<div class="dashboard">Welcome ' + email + '</div>';
                    }
                });
            </script>
        </body></html>
        """)

        mod = get_module("browser.login")({
            "username": "test@example.com",
            "password": "secret123",
            "success_indicator": ".dashboard",
        }, ctx)
        mod.validate_params()
        result = await mod.execute()

        print(f"\n[login] logged_in={result['logged_in']}, fields={result['fields_found']}")

        assert result["logged_in"] is True
        assert result["fields_found"]["username_found"] is True
        assert result["fields_found"]["password_found"] is True
