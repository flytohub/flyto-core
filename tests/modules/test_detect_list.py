"""
Tests for browser.detect_list module
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestDetectListRegistration:
    MODULE_ID = "browser.detect_list"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic  # noqa: F401
        return ModuleRegistry.get(self.MODULE_ID)

    def test_module_registered(self, module_class):
        assert module_class is not None

    def test_default_params(self, module_class):
        instance = module_class({}, {})
        instance.validate_params()
        assert instance.selector == ''
        assert instance.min_items == 3

    @pytest.mark.asyncio
    async def test_no_browser_raises(self, module_class):
        instance = module_class({}, {})
        instance.validate_params()
        with pytest.raises(RuntimeError, match="Browser not launched"):
            await instance.execute()


class TestDetectListJS:
    def test_js_valid(self):
        from core.modules.atomic.browser.detect_list import _DETECT_LIST_JS
        assert isinstance(_DETECT_LIST_JS, str)
        assert _DETECT_LIST_JS.strip().startswith("(")

    def test_js_has_fingerprint(self):
        from core.modules.atomic.browser.detect_list import _DETECT_LIST_JS
        assert "fingerprint" in _DETECT_LIST_JS
        assert "structureSimilarity" in _DETECT_LIST_JS

    def test_js_extracts_fields(self):
        from core.modules.atomic.browser.detect_list import _DETECT_LIST_JS
        assert "item.title" in _DETECT_LIST_JS
        assert "item.url" in _DETECT_LIST_JS
        assert "item.image" in _DETECT_LIST_JS


@pytest.mark.browser
class TestDetectListE2E:

    @pytest.fixture
    async def browser_context(self):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            pytest.skip("Playwright not installed")
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        yield page
        await browser.close()
        await pw.stop()

    @pytest.mark.asyncio
    async def test_detect_article_list(self, browser_context):
        """Detect a list of articles (HN-like structure)."""
        page = browser_context
        html = """
        <html><body>
        <nav>Home | New | Top</nav>
        <div id="items">
            <div class="item"><a href="/article/1">First Article Title Here</a><span class="score">42 points</span></div>
            <div class="item"><a href="/article/2">Second Article Title Here</a><span class="score">38 points</span></div>
            <div class="item"><a href="/article/3">Third Article About Programming</a><span class="score">25 points</span></div>
            <div class="item"><a href="/article/4">Fourth Article On Design</a><span class="score">19 points</span></div>
            <div class="item"><a href="/article/5">Fifth Article On Startups</a><span class="score">12 points</span></div>
        </div>
        <footer>Page 1 of 10</footer>
        </body></html>
        """
        await page.set_content(html)

        from core.modules.atomic.browser.detect_list import _DETECT_LIST_JS
        result = await page.evaluate(_DETECT_LIST_JS, {})

        assert result["content_found"] is True
        assert result["count"] == 5
        assert result["auto_detected"] is True
        assert result["items"][0]["title"] == "First Article Title Here"
        assert result["items"][0]["url"].endswith("/article/1")
        assert result["items"][2]["title"] == "Third Article About Programming"

    @pytest.mark.asyncio
    async def test_detect_product_grid(self, browser_context):
        """Detect a product listing (e-commerce style)."""
        page = browser_context
        html = """
        <html><body>
        <div class="products">
            <div class="product-card"><a href="/p/1"><h3>Widget A</h3></a><img src="a.jpg" alt="Widget A"><span>$19.99</span></div>
            <div class="product-card"><a href="/p/2"><h3>Widget B</h3></a><img src="b.jpg" alt="Widget B"><span>$29.99</span></div>
            <div class="product-card"><a href="/p/3"><h3>Widget C</h3></a><img src="c.jpg" alt="Widget C"><span>$39.99</span></div>
            <div class="product-card"><a href="/p/4"><h3>Widget D</h3></a><img src="d.jpg" alt="Widget D"><span>$49.99</span></div>
        </div>
        </body></html>
        """
        await page.set_content(html)

        from core.modules.atomic.browser.detect_list import _DETECT_LIST_JS
        result = await page.evaluate(_DETECT_LIST_JS, {"min_items": 3})

        assert result["content_found"] is True
        assert result["count"] == 4
        assert "Widget A" in result["items"][0]["title"]
        assert result["items"][0].get("image", "").endswith("a.jpg")

    @pytest.mark.asyncio
    async def test_detect_with_custom_selector(self, browser_context):
        """Use explicit selector instead of auto-detect."""
        page = browser_context
        html = """
        <html><body>
        <ul>
            <li class="result"><a href="/r1">Result One</a></li>
            <li class="result"><a href="/r2">Result Two</a></li>
            <li class="result"><a href="/r3">Result Three</a></li>
        </ul>
        </body></html>
        """
        await page.set_content(html)

        from core.modules.atomic.browser.detect_list import _DETECT_LIST_JS
        result = await page.evaluate(_DETECT_LIST_JS, {"selector": "li.result"})

        assert result["auto_detected"] is False
        assert result["count"] == 3
        assert result["items"][1]["title"] == "Result Two"

    @pytest.mark.asyncio
    async def test_returns_reusable_selector(self, browser_context):
        """Auto-detection should return a CSS selector for reuse."""
        page = browser_context
        html = """
        <html><body>
        <div class="feed">
            <article class="post-item"><a href="/1">Post One is great</a></article>
            <article class="post-item"><a href="/2">Post Two is better</a></article>
            <article class="post-item"><a href="/3">Post Three is best</a></article>
        </div>
        </body></html>
        """
        await page.set_content(html)

        from core.modules.atomic.browser.detect_list import _DETECT_LIST_JS
        result = await page.evaluate(_DETECT_LIST_JS, {})

        assert result["content_found"] is True
        assert result["selector"]  # should return a reusable selector
        # Verify the selector actually works
        items = await page.query_selector_all(result["selector"])
        assert len(items) >= 3

    @pytest.mark.asyncio
    async def test_no_list_returns_empty(self, browser_context):
        """Page with no repeating items should return empty."""
        page = browser_context
        html = """
        <html><body>
        <h1>About Us</h1>
        <p>We are a company that does things.</p>
        <p>Contact us at hello@example.com.</p>
        </body></html>
        """
        await page.set_content(html)

        from core.modules.atomic.browser.detect_list import _DETECT_LIST_JS
        result = await page.evaluate(_DETECT_LIST_JS, {})

        assert result["content_found"] is False
        assert result["count"] == 0
