"""
Tests for browser.challenge module

Tests challenge detection, auto-wait, and fallback behavior.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestChallengeRegistration:
    MODULE_ID = "browser.challenge"

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
        assert instance.auto_wait == 15
        assert instance.human_fallback is True
        assert instance.human_timeout == 120

    def test_custom_params(self, module_class):
        instance = module_class({"auto_wait_seconds": 30, "human_fallback": False}, {})
        instance.validate_params()
        assert instance.auto_wait == 30
        assert instance.human_fallback is False

    @pytest.mark.asyncio
    async def test_no_browser_raises(self, module_class):
        instance = module_class({}, {})
        instance.validate_params()
        with pytest.raises(RuntimeError, match="Browser not launched"):
            await instance.execute()


class TestChallengeJS:
    def test_detection_js_valid(self):
        from core.modules.atomic.browser.challenge import _CHALLENGE_PATTERNS_JS
        assert isinstance(_CHALLENGE_PATTERNS_JS, str)
        assert "cloudflare" in _CHALLENGE_PATTERNS_JS
        assert "hcaptcha" in _CHALLENGE_PATTERNS_JS
        assert "recaptcha" in _CHALLENGE_PATTERNS_JS

    def test_resolved_js_valid(self):
        from core.modules.atomic.browser.challenge import _CHECK_RESOLVED_JS
        assert isinstance(_CHECK_RESOLVED_JS, str)
        assert "just a moment" in _CHECK_RESOLVED_JS


@pytest.mark.browser
class TestChallengeE2E:

    @pytest.fixture
    async def page(self):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            pytest.skip("Playwright not installed")
        pw = await async_playwright().start()
        br = await pw.chromium.launch(headless=True)
        p = await br.new_page()
        yield p
        await br.close()
        await pw.stop()

    @pytest.mark.asyncio
    async def test_no_challenge_on_clean_page(self, page):
        """Normal page should report no challenge."""
        html = """
        <html><head><title>My Blog</title></head>
        <body><h1>Welcome</h1><p>This is a normal page with content.</p></body>
        </html>
        """
        await page.set_content(html)

        from core.modules.atomic.browser.challenge import _CHALLENGE_PATTERNS_JS
        result = await page.evaluate(_CHALLENGE_PATTERNS_JS, {})
        assert result["has_challenge"] is False
        assert len(result["challenges"]) == 0

    @pytest.mark.asyncio
    async def test_detect_cloudflare_challenge(self, page):
        """Should detect Cloudflare 'Just a moment' page."""
        html = """
        <html><head><title>Just a moment...</title></head>
        <body>
            <div>Checking your browser before accessing the website.</div>
            <div>This process is automatic. Your browser will redirect shortly.</div>
        </body>
        </html>
        """
        await page.set_content(html)

        from core.modules.atomic.browser.challenge import _CHALLENGE_PATTERNS_JS
        result = await page.evaluate(_CHALLENGE_PATTERNS_JS, {})
        assert result["has_challenge"] is True
        assert result["challenges"][0]["type"] == "cloudflare"

    @pytest.mark.asyncio
    async def test_detect_cloudflare_with_turnstile(self, page):
        """Should detect Cloudflare Turnstile iframe."""
        html = """
        <html><head><title>Just a moment...</title></head>
        <body>
            <div>Verifying you are human.</div>
            <iframe src="https://challenges.cloudflare.com/turnstile/v0/xxx"></iframe>
        </body>
        </html>
        """
        await page.set_content(html)

        from core.modules.atomic.browser.challenge import _CHALLENGE_PATTERNS_JS
        result = await page.evaluate(_CHALLENGE_PATTERNS_JS, {})
        assert result["has_challenge"] is True
        assert result["challenges"][0]["type"] == "cloudflare"
        assert result["challenges"][0]["has_turnstile"] is True

    @pytest.mark.asyncio
    async def test_detect_hcaptcha(self, page):
        """Should detect hCaptcha."""
        html = """
        <html><head><title>Verify</title></head>
        <body>
            <div class="h-captcha" data-sitekey="xxx"></div>
        </body>
        </html>
        """
        await page.set_content(html)

        from core.modules.atomic.browser.challenge import _CHALLENGE_PATTERNS_JS
        result = await page.evaluate(_CHALLENGE_PATTERNS_JS, {})
        assert result["has_challenge"] is True
        assert any(c["type"] == "hcaptcha" for c in result["challenges"])

    @pytest.mark.asyncio
    async def test_detect_recaptcha(self, page):
        """Should detect reCAPTCHA."""
        html = """
        <html><head><title>Login</title></head>
        <body>
            <form>
                <div class="g-recaptcha" data-sitekey="xxx"></div>
            </form>
        </body>
        </html>
        """
        await page.set_content(html)

        from core.modules.atomic.browser.challenge import _CHALLENGE_PATTERNS_JS
        result = await page.evaluate(_CHALLENGE_PATTERNS_JS, {})
        assert result["has_challenge"] is True
        assert any(c["type"] == "recaptcha" for c in result["challenges"])

    @pytest.mark.asyncio
    async def test_auto_resolve_detection(self, page):
        """When challenge page becomes real content, resolution is detected."""
        # Start with challenge
        await page.set_content("<html><head><title>Just a moment...</title></head><body>Checking...</body></html>")

        from core.modules.atomic.browser.challenge import _CHALLENGE_PATTERNS_JS, _CHECK_RESOLVED_JS
        result = await page.evaluate(_CHALLENGE_PATTERNS_JS, {})
        assert result["has_challenge"] is True

        resolved = await page.evaluate(_CHECK_RESOLVED_JS)
        assert resolved is False

        # Simulate challenge resolving (page content changes)
        await page.set_content("""
        <html><head><title>Stack Overflow - Questions</title></head>
        <body><div class="content">
            <div class="question">How to use Python?</div>
            <div class="question">What is JavaScript?</div>
            <p>Lots of real content here that should be detected as resolved.</p>
        </div></body></html>
        """)

        resolved = await page.evaluate(_CHECK_RESOLVED_JS)
        assert resolved is True


@pytest.mark.browser
class TestStealthPatches:
    """Test that stealth patches are correctly applied."""

    @pytest.fixture
    async def stealth_page(self):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            pytest.skip("Playwright not installed")
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
        from core.browser.driver import BrowserDriver
        driver = BrowserDriver(headless=True)
        await driver.launch(stealth=True)
        yield driver.page
        await driver.close()

    @pytest.fixture
    async def no_stealth_page(self):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            pytest.skip("Playwright not installed")
        from core.browser.driver import BrowserDriver
        driver = BrowserDriver(headless=True)
        await driver.launch(stealth=False)
        yield driver.page
        await driver.close()

    @pytest.mark.asyncio
    async def test_webdriver_hidden(self, stealth_page):
        result = await stealth_page.evaluate("() => navigator.webdriver")
        assert result is None  # undefined in JS → None in Python

    @pytest.mark.asyncio
    async def test_chrome_object_complete(self, stealth_page):
        checks = await stealth_page.evaluate("""() => ({
            hasChrome: !!window.chrome,
            hasApp: !!window.chrome?.app,
            hasRuntime: !!window.chrome?.runtime,
            hasCsi: typeof window.chrome?.csi,
            hasLoadTimes: typeof window.chrome?.loadTimes,
            runtimeKeys: Object.keys(window.chrome?.runtime || {}).length,
        })""")
        assert checks["hasChrome"] is True
        assert checks["hasApp"] is True
        assert checks["hasRuntime"] is True
        assert checks["hasCsi"] == "function"
        assert checks["hasLoadTimes"] == "function"
        assert checks["runtimeKeys"] >= 5

    @pytest.mark.asyncio
    async def test_plugins_present(self, stealth_page):
        count = await stealth_page.evaluate("() => navigator.plugins.length")
        assert count >= 3

    @pytest.mark.asyncio
    async def test_languages_set(self, stealth_page):
        langs = await stealth_page.evaluate("() => navigator.languages")
        assert isinstance(langs, list)
        assert len(langs) >= 2
        assert "en" in langs

    @pytest.mark.asyncio
    async def test_hardware_concurrency(self, stealth_page):
        result = await stealth_page.evaluate("() => navigator.hardwareConcurrency")
        assert result in (4, 6, 8, 10, 12, 16)

    @pytest.mark.asyncio
    async def test_webgl_vendor_spoofed(self, stealth_page):
        vendor = await stealth_page.evaluate("""() => {
            try {
                const c = document.createElement('canvas');
                const gl = c.getContext('webgl');
                const ext = gl.getExtension('WEBGL_debug_renderer_info');
                return gl.getParameter(ext.UNMASKED_VENDOR_WEBGL);
            } catch(e) { return 'error: ' + e.message; }
        }""")
        assert "SwiftShader" not in vendor
        assert "Google" in vendor

    @pytest.mark.asyncio
    async def test_webgl_renderer_spoofed(self, stealth_page):
        result = await stealth_page.evaluate("""() => {
            try {
                const c = document.createElement('canvas');
                const gl = c.getContext('webgl');
                const ext = gl.getExtension('WEBGL_debug_renderer_info');
                return {
                    renderer: gl.getParameter(ext.UNMASKED_RENDERER_WEBGL),
                    platform: navigator.platform,
                };
            } catch(e) { return { renderer: 'error: ' + e.message, platform: '' }; }
        }""")
        renderer = result["renderer"]
        platform = result["platform"]
        assert "SwiftShader" not in renderer
        assert "ANGLE" in renderer
        # Renderer should match platform
        if "Mac" in platform:
            assert "Apple" in renderer
        elif "Win" in platform:
            assert "Intel" in renderer or "NVIDIA" in renderer
        else:  # Linux
            assert "NVIDIA" in renderer or "Intel" in renderer

    @pytest.mark.asyncio
    async def test_connection_api_present(self, stealth_page):
        result = await stealth_page.evaluate("() => !!navigator.connection")
        assert result is True

    @pytest.mark.asyncio
    async def test_battery_api_present(self, stealth_page):
        result = await stealth_page.evaluate("() => typeof navigator.getBattery")
        assert result == "function"

    @pytest.mark.asyncio
    async def test_no_stealth_lacks_chrome_app(self, no_stealth_page):
        """Without stealth, chrome.app should NOT be populated."""
        result = await no_stealth_page.evaluate("() => !!window.chrome?.app?.isInstalled")
        # Without stealth patches, chrome.app.isInstalled is not defined
        assert result is False
