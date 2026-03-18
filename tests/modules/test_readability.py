"""
Tests for browser.readability module

Tests module registration, param validation, and extraction JS logic.
Browser tests require Playwright and are marked with @pytest.mark.browser.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestReadabilityRegistration:
    """Tests that the module is properly registered."""

    MODULE_ID = "browser.readability"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic  # noqa: F401 — triggers registration
        return ModuleRegistry.get(self.MODULE_ID)

    def test_module_registered(self, module_class):
        """Module should be discoverable in the registry."""
        assert module_class is not None

    def test_module_metadata(self, module_class):
        """Check module is registered with correct metadata."""
        from core.modules.registry import ModuleRegistry
        meta = ModuleRegistry.get_metadata(self.MODULE_ID)
        assert meta is not None
        assert meta.get("module_id") == self.MODULE_ID or meta.get("id") == self.MODULE_ID

    def test_module_has_execute(self, module_class):
        """Module should have an async execute method."""
        import inspect
        assert hasattr(module_class, 'execute')
        assert inspect.iscoroutinefunction(module_class.execute)


class TestReadabilityValidation:
    """Tests param validation without running a browser."""

    MODULE_ID = "browser.readability"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic  # noqa: F401
        return ModuleRegistry.get(self.MODULE_ID)

    def test_default_params(self, module_class):
        """Should accept empty params (all optional)."""
        instance = module_class({}, {})
        instance.validate_params()
        assert instance.selector == ''
        assert instance.include_images is True
        assert instance.min_content_length == 80

    def test_custom_selector(self, module_class):
        instance = module_class({"selector": ".my-content"}, {})
        instance.validate_params()
        assert instance.selector == ".my-content"

    def test_custom_clean_selectors(self, module_class):
        instance = module_class({"clean_selectors": [".ad", ".popup"]}, {})
        instance.validate_params()
        assert instance.clean_selectors == [".ad", ".popup"]

    def test_wait_ms(self, module_class):
        instance = module_class({"wait_ms": 2000}, {})
        instance.validate_params()
        assert instance.wait_ms == 2000

    @pytest.mark.asyncio
    async def test_no_browser_raises(self, module_class):
        """Should raise when no browser in context."""
        instance = module_class({}, {})
        instance.validate_params()
        with pytest.raises(RuntimeError, match="Browser not launched"):
            await instance.execute()


class TestExtractionJS:
    """Test the extraction JavaScript logic standalone."""

    def test_js_string_is_valid(self):
        """The extraction JS should be a valid string constant."""
        from core.modules.atomic.browser.readability import _EXTRACT_JS
        assert isinstance(_EXTRACT_JS, str)
        assert len(_EXTRACT_JS) > 100
        # Should be a JS function expression
        assert _EXTRACT_JS.strip().startswith("(")

    def test_js_contains_strategies(self):
        """JS should contain metadata extraction + unified scoring."""
        from core.modules.atomic.browser.readability import _EXTRACT_JS
        # Strategy 1: metadata
        assert "og:title" in _EXTRACT_JS
        assert "application/ld+json" in _EXTRACT_JS
        # Strategy 2: unified scoring (not hardcoded selectors)
        assert "scoreElement" in _EXTRACT_JS
        assert "linkDensity" in _EXTRACT_JS
        assert "articleBody" in _EXTRACT_JS  # schema.org bonus in scoring
        # Scoring signals
        assert "blockCount" in _EXTRACT_JS
        assert "isNoise" in _EXTRACT_JS

    def test_js_contains_noise_selectors(self):
        """JS should remove common noise elements."""
        from core.modules.atomic.browser.readability import _EXTRACT_JS
        assert "sidebar" in _EXTRACT_JS
        assert "comment" in _EXTRACT_JS
        assert "advert" in _EXTRACT_JS
        assert "newsletter" in _EXTRACT_JS
        assert "cookie" in _EXTRACT_JS

    def test_js_supports_custom_options(self):
        """JS should accept options for customization."""
        from core.modules.atomic.browser.readability import _EXTRACT_JS
        assert "customSelector" in _EXTRACT_JS
        assert "customTitleSelector" in _EXTRACT_JS
        assert "extraCleanSelectors" in _EXTRACT_JS
        assert "minLen" in _EXTRACT_JS


@pytest.mark.browser
class TestReadabilityE2E:
    """End-to-end tests with real browser. Run with: pytest -m browser"""

    MODULE_ID = "browser.readability"

    @pytest.fixture
    async def browser_context(self):
        """Create a real browser context for testing."""
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
    async def test_extract_from_html(self, browser_context):
        """Test extraction from a controlled HTML page."""
        page = browser_context

        html = """
        <html lang="en">
        <head>
            <title>Test Article</title>
            <meta property="og:title" content="My Test Article">
            <meta name="author" content="John Doe">
            <meta property="article:published_time" content="2026-01-15T10:00:00Z">
        </head>
        <body>
            <nav>Navigation menu here</nav>
            <article>
                <h1>My Test Article</h1>
                <p>This is the first paragraph of the article content.</p>
                <p>This is the second paragraph with more interesting details about the topic.</p>
                <p>And a third paragraph to ensure we have enough content for extraction.</p>
            </article>
            <footer>Footer content here</footer>
        </body>
        </html>
        """
        await page.set_content(html)

        from core.modules.atomic.browser.readability import _EXTRACT_JS
        result = await page.evaluate(_EXTRACT_JS, {})

        assert result["title"] == "My Test Article"
        assert result["author"] == "John Doe"
        assert result["date"] == "2026-01-15T10:00:00Z"
        assert "first paragraph" in result["content"]
        assert "second paragraph" in result["content"]
        assert "Navigation menu" not in result["content"]
        assert "Footer content" not in result["content"]
        assert result["content_found"] is True
        assert result["word_count"] > 10

    @pytest.mark.asyncio
    async def test_extract_with_custom_selector(self, browser_context):
        """Test extraction with user-specified selector."""
        page = browser_context

        html = """
        <html>
        <body>
            <div class="noise">This should be ignored</div>
            <div id="weird-content">
                <p>This is the real content in a weird container.</p>
                <p>More content here that we want to extract properly.</p>
            </div>
            <div class="noise">Also ignored</div>
        </body>
        </html>
        """
        await page.set_content(html)

        from core.modules.atomic.browser.readability import _EXTRACT_JS
        result = await page.evaluate(_EXTRACT_JS, {"selector": "#weird-content"})

        assert "real content" in result["content"]
        assert "should be ignored" not in result["content"]

    @pytest.mark.asyncio
    async def test_extract_with_clean_selectors(self, browser_context):
        """Test removing site-specific noise."""
        page = browser_context

        html = """
        <html>
        <body>
            <nav>Home | About | Contact</nav>
            <article>
                <p>Good content here that matters and should be extracted properly from the page.</p>
                <div class="promo-box">Buy our stuff! Special offer! Limited time only!</div>
                <p>More good content after the promo that continues the article narrative.</p>
                <p>A third paragraph to ensure sufficient content length for the readability algorithm.</p>
            </article>
            <footer>Copyright 2026</footer>
        </body>
        </html>
        """
        await page.set_content(html)

        from core.modules.atomic.browser.readability import _EXTRACT_JS
        result = await page.evaluate(_EXTRACT_JS, {"clean_selectors": [".promo-box"]})

        assert "Good content" in result["content"]
        assert "Buy our stuff" not in result["content"]

    @pytest.mark.asyncio
    async def test_json_ld_extraction(self, browser_context):
        """Test JSON-LD schema.org metadata extraction."""
        page = browser_context

        html = """
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@type": "NewsArticle",
                "headline": "Breaking News Title",
                "author": {"name": "Jane Reporter"},
                "datePublished": "2026-03-18T08:00:00Z",
                "description": "A short summary of the news."
            }
            </script>
        </head>
        <body>
            <article>
                <p>The full news article content goes here with details.</p>
                <p>Multiple paragraphs of reporting and analysis follow.</p>
            </article>
        </body>
        </html>
        """
        await page.set_content(html)

        from core.modules.atomic.browser.readability import _EXTRACT_JS
        result = await page.evaluate(_EXTRACT_JS, {})

        assert result["title"] == "Breaking News Title"
        assert result["author"] == "Jane Reporter"
        assert result["date"] == "2026-03-18T08:00:00Z"

    @pytest.mark.asyncio
    async def test_text_density_fallback(self, browser_context):
        """Test fallback to text density when no semantic selectors match."""
        page = browser_context

        html = """
        <html>
        <body>
            <div class="x-nav"><a href="/">Home</a> <a href="/about">About</a> <a href="/contact">Contact</a></div>
            <div class="x-main">
                <p>This is a blog post without any standard article markup or class names.</p>
                <p>It has multiple paragraphs with substantial content that should be detected.</p>
                <p>The text density algorithm should find this as the main content block.</p>
                <p>Because it has the most text and lowest link density on the page.</p>
            </div>
            <div class="x-sidebar"><a href="/1">Link 1</a><a href="/2">Link 2</a><a href="/3">Link 3</a></div>
        </body>
        </html>
        """
        await page.set_content(html)

        from core.modules.atomic.browser.readability import _EXTRACT_JS
        result = await page.evaluate(_EXTRACT_JS, {})

        assert "blog post" in result["content"]
        assert "text density algorithm" in result["content"]
        assert result["content_found"] is True
