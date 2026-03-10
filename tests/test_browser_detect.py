"""
Real browser integration tests for browser.detect module.

Uses a local HTML test page served via Python's HTTP server.
Launches a REAL Chromium browser via Playwright — NO mocks.

Usage:
    pytest tests/test_browser_detect.py -v
    pytest tests/test_browser_detect.py -v -k "test_exact_text"
"""
import asyncio
import os
import sys
import threading
import http.server
import functools
from pathlib import Path

import pytest
import pytest_asyncio

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
os.environ["FLYTO_VSCODE_LOCAL_MODE"] = "true"
os.environ.setdefault("FLYTO_ENV", "test")

from core.modules.registry import ModuleRegistry
import core.modules.atomic.browser  # trigger registration

TEST_HTML = Path(__file__).parent / "fixtures" / "detect_test_page.html"


# ─── Fixtures ───────────────────────────────────────────────────

@pytest.fixture(scope="module")
def event_loop():
    """Single event loop for all tests — browser connection persists."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def local_server():
    """Start a local HTTP server serving the test HTML page."""
    fixtures_dir = str(TEST_HTML.parent)
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=fixtures_dir
    )
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}/detect_test_page.html"
    srv.shutdown()


@pytest_asyncio.fixture(scope="module")
async def ctx(local_server):
    """Launch a real browser, navigate to test page. Shared across all tests."""
    context = {}
    launch_cls = ModuleRegistry.get("browser.launch")
    launch_mod = launch_cls({"headless": True}, context)
    await launch_mod.execute()

    goto_cls = ModuleRegistry.get("browser.goto")
    goto_mod = goto_cls({"url": local_server}, context)
    await goto_mod.execute()

    yield context

    if context.get("browser"):
        await context["browser"].close()


async def _detect(ctx, params):
    """Run browser.detect and return result dict."""
    cls = ModuleRegistry.get("browser.detect")
    return await cls(params, ctx).execute()


# ─── Tests: CSS / XPath Selector (confidence 100) ────────────────

class TestSelector:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_id_selector(self, ctx):
        r = await _detect(ctx, {"selector": "#login-btn"})
        assert r["found"] is True
        assert r["strategy"] == "selector"
        assert r["confidence"] == 100
        assert r["element"]["tag"] == "button"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_name_selector(self, ctx):
        r = await _detect(ctx, {"selector": 'input[name="email"]'})
        assert r["found"] is True
        assert r["element"]["tag"] == "input"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_data_testid(self, ctx):
        r = await _detect(ctx, {"selector": '[data-testid="submit-btn"]'})
        assert r["found"] is True
        assert "Submit" in r["element"]["text"]

    @pytest.mark.asyncio(loop_scope="module")
    async def test_not_found(self, ctx):
        r = await _detect(ctx, {"selector": "#nonexistent"})
        assert r["found"] is False
        assert r["status"] == "not_found"


# ─── Tests: Text Matching ────────────────────────────────────────

class TestTextMatch:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_exact(self, ctx):
        r = await _detect(ctx, {"text": "Login", "match_mode": "exact"})
        assert r["found"] is True
        assert r["confidence"] >= 85

    @pytest.mark.asyncio(loop_scope="module")
    async def test_contains(self, ctx):
        r = await _detect(ctx, {"text": "Confirm", "match_mode": "contains"})
        assert r["found"] is True
        assert "Confirm" in r["element"]["text"]

    @pytest.mark.asyncio(loop_scope="module")
    async def test_not_found(self, ctx):
        r = await _detect(ctx, {"text": "NoSuchTextAnywhere", "match_mode": "exact"})
        assert r["found"] is False


# ─── Tests: Playwright get_by_role ───────────────────────────────

class TestRole:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_button(self, ctx):
        r = await _detect(ctx, {"text": "Login", "role": "button"})
        assert r["found"] is True
        assert r["strategy"] == "role"
        assert r["confidence"] == 95
        assert r["element"]["tag"] == "button"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_link(self, ctx):
        r = await _detect(ctx, {"text": "About Us", "role": "link"})
        assert r["found"] is True
        assert r["element"]["tag"] == "a"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_textbox(self, ctx):
        r = await _detect(ctx, {"text": "Email Address", "role": "textbox"})
        assert r["found"] is True
        assert r["element"]["tag"] == "input"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_checkbox(self, ctx):
        r = await _detect(ctx, {"text": "I agree to terms", "role": "checkbox"})
        assert r["found"] is True

    @pytest.mark.asyncio(loop_scope="module")
    async def test_heading(self, ctx):
        r = await _detect(ctx, {"text": "Main Title", "role": "heading"})
        assert r["found"] is True
        assert r["element"]["tag"] == "h1"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_aria_button(self, ctx):
        r = await _detect(ctx, {"text": "Add to Cart", "role": "button"})
        assert r["found"] is True
        assert r["element"]["ariaLabel"] == "Add to Cart"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_img(self, ctx):
        r = await _detect(ctx, {"text": "Product Photo", "role": "img"})
        assert r["found"] is True
        assert r["element"]["tag"] == "img"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_combobox(self, ctx):
        r = await _detect(ctx, {"text": "Country", "role": "combobox"})
        assert r["found"] is True
        assert r["element"]["tag"] == "select"


# ─── Tests: Label / Placeholder / Alt / Title ────────────────────

class TestSemanticLocators:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_label(self, ctx):
        r = await _detect(ctx, {"text": "Email Address"})
        assert r["found"] is True

    @pytest.mark.asyncio(loop_scope="module")
    async def test_placeholder(self, ctx):
        r = await _detect(ctx, {"text": "Enter your email"})
        assert r["found"] is True
        assert r["element"]["tag"] == "input"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_alt_text(self, ctx):
        r = await _detect(ctx, {"text": "User Avatar"})
        assert r["found"] is True
        assert r["element"]["tag"] == "img"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_title(self, ctx):
        r = await _detect(ctx, {"text": "Documentation"})
        assert r["found"] is True
        assert r["element"]["tag"] == "a"


# ─── Tests: Alternative Texts ────────────────────────────────────

class TestAlternatives:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_primary_miss_alt_hit(self, ctx):
        r = await _detect(ctx, {
            "text": "Iniciar sesion",
            "alternatives": "Login, Sign In",
            "role": "button",
        })
        assert r["found"] is True
        assert "Login" in r["element"]["text"]

    @pytest.mark.asyncio(loop_scope="module")
    async def test_multiple_alts(self, ctx):
        r = await _detect(ctx, {
            "text": "提交",
            "alternatives": "送出, Submit Form, Envoyer",
        })
        assert r["found"] is True
        assert "Submit" in r["element"]["text"]


# ─── Tests: Fuzzy Matching ───────────────────────────────────────

class TestFuzzy:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_misspelled(self, ctx):
        r = await _detect(ctx, {"text": "Confirm Purchas", "match_mode": "fuzzy"})
        assert r["found"] is True
        assert "Confirm Purchase" in r["element"]["text"]

    @pytest.mark.asyncio(loop_scope="module")
    async def test_partial(self, ctx):
        r = await _detect(ctx, {"text": "Forgot Pass", "match_mode": "fuzzy"})
        assert r["found"] is True
        assert "Forgot" in r["element"]["text"]

    @pytest.mark.asyncio(loop_scope="module")
    async def test_no_match(self, ctx):
        r = await _detect(ctx, {"text": "zzzzxyzzy", "match_mode": "fuzzy"})
        assert r["found"] is False

    @pytest.mark.asyncio(loop_scope="module")
    async def test_best_mode(self, ctx):
        r = await _detect(ctx, {"text": "Create New Accoun", "match_mode": "best"})
        assert r["found"] is True
        assert "Account" in r["element"]["text"]


# ─── Tests: Proximity ────────────────────────────────────────────

class TestProximity:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_near_text(self, ctx):
        r = await _detect(ctx, {
            "text": "Save",
            "near_text": "Username",
            "role": "button",
            "match_mode": "best",
        })
        assert r["found"] is True
        assert "Save" in r["element"]["text"]


# ─── Tests: Role Filter ──────────────────────────────────────────

class TestRoleFilter:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_excludes_wrong_type(self, ctx):
        """'Home' is a link, not a button."""
        r = await _detect(ctx, {"text": "Home", "role": "button", "match_mode": "exact"})
        if r["found"]:
            assert r["element"]["tag"] != "a"
        else:
            assert r["status"] == "not_found"


# ─── Tests: Hidden Elements ──────────────────────────────────────

class TestHidden:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_hidden_button_skipped(self, ctx):
        r = await _detect(ctx, {"text": "Hidden Button", "match_mode": "exact"})
        assert r["found"] is False


# ─── Tests: Fallback Chain ───────────────────────────────────────

class TestFallback:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_selector_fails_text_succeeds(self, ctx):
        r = await _detect(ctx, {
            "selector": "#old-deleted-button",
            "text": "Login",
        })
        assert r["found"] is True
        assert r["strategy"] != "selector"
        assert "Login" in r["element"]["text"]

    @pytest.mark.asyncio(loop_scope="module")
    async def test_selector_wins_over_text(self, ctx):
        """When both provided, selector (higher confidence) wins."""
        r = await _detect(ctx, {
            "selector": "#login-btn",
            "text": "Cancel",
        })
        assert r["found"] is True
        assert r["strategy"] == "selector"
        assert r["element"]["id"] == "login-btn"


# ─── Tests: Actions ──────────────────────────────────────────────

class TestActions:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_type(self, ctx):
        r = await _detect(ctx, {
            "text": "Enter your email",
            "role": "textbox",
            "action": "type",
            "action_value": "test@example.com",
        })
        assert r["found"] is True
        assert r["action_result"] == "typed"
        page = ctx["browser"].page
        assert await page.input_value("#email") == "test@example.com"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_click(self, ctx, local_server):
        r = await _detect(ctx, {
            "text": "Cancel",
            "role": "button",
            "action": "click",
        })
        assert r["found"] is True
        assert r["action_result"] == "clicked"
        # Navigate back
        goto_cls = ModuleRegistry.get("browser.goto")
        await goto_cls({"url": local_server}, ctx).execute()


# ─── Tests: Element Hints Output ─────────────────────────────────

class TestHints:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_has_hints(self, ctx):
        r = await _detect(ctx, {"text": "Login", "role": "button"})
        assert r["found"] is True
        assert any(k in r for k in ("buttons", "inputs", "links", "selects"))

    @pytest.mark.asyncio(loop_scope="module")
    async def test_buttons(self, ctx):
        r = await _detect(ctx, {"selector": "#login-btn"})
        buttons = r.get("buttons", [])
        assert len(buttons) > 0
        texts = [b.get("text", "") for b in buttons]
        assert any("Login" in t for t in texts)

    @pytest.mark.asyncio(loop_scope="module")
    async def test_inputs(self, ctx):
        r = await _detect(ctx, {"selector": "#login-btn"})
        inputs = r.get("inputs", [])
        assert len(inputs) > 0
        assert any("email" in i.get("selector", "") for i in inputs)

    @pytest.mark.asyncio(loop_scope="module")
    async def test_links(self, ctx):
        r = await _detect(ctx, {"selector": "#login-btn"})
        links = r.get("links", [])
        assert len(links) > 0
        assert any("About" in l.get("text", "") for l in links)

    @pytest.mark.asyncio(loop_scope="module")
    async def test_selects_with_options(self, ctx):
        r = await _detect(ctx, {"selector": "#country"})
        assert r["found"] is True
        selects = r.get("selects", [])
        assert len(selects) > 0
        country = next((s for s in selects if "country" in s.get("selector", "")), None)
        assert country is not None
        opts = country.get("options", [])
        assert len(opts) >= 4
        us = next((o for o in opts if o["value"] == "us"), None)
        assert us is not None
        assert us["label"] == "United States"


# ─── Tests: Validation ───────────────────────────────────────────

class TestValidation:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_no_params_raises(self, ctx):
        with pytest.raises(ValueError, match="Must provide at least one"):
            await _detect(ctx, {})

    @pytest.mark.asyncio(loop_scope="module")
    async def test_type_without_value_raises(self, ctx):
        with pytest.raises(ValueError, match="action_value"):
            await _detect(ctx, {"text": "Login", "action": "type"})

    @pytest.mark.asyncio(loop_scope="module")
    async def test_empty_alternatives(self, ctx):
        r = await _detect(ctx, {"text": "Login", "alternatives": ""})
        assert r["found"] is True

    @pytest.mark.asyncio(loop_scope="module")
    async def test_only_alternatives(self, ctx):
        r = await _detect(ctx, {"alternatives": "Login, Cancel"})
        assert r["found"] is True


# ─── Tests: Confidence Scoring ────────────────────────────────────

class TestConfidence:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_selector_100(self, ctx):
        r = await _detect(ctx, {"selector": "#login-btn"})
        assert r["confidence"] == 100

    @pytest.mark.asyncio(loop_scope="module")
    async def test_role_95(self, ctx):
        r = await _detect(ctx, {"text": "Login", "role": "button"})
        assert r["confidence"] >= 90

    @pytest.mark.asyncio(loop_scope="module")
    async def test_exact_text_high(self, ctx):
        r = await _detect(ctx, {"text": "Login", "match_mode": "exact"})
        assert r["confidence"] >= 85

    @pytest.mark.asyncio(loop_scope="module")
    async def test_fuzzy_lower(self, ctx):
        r = await _detect(ctx, {"text": "Confirm Purchas", "match_mode": "fuzzy"})
        if r["found"]:
            assert r["confidence"] < 95

    @pytest.mark.asyncio(loop_scope="module")
    async def test_not_found_has_candidates(self, ctx):
        r = await _detect(ctx, {"text": "zzzzxyzzy", "match_mode": "best"})
        assert r["found"] is False
        assert "candidates" in r


# ─── Tests: Edge Cases ───────────────────────────────────────────

class TestEdgeCases:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_multiple_matching(self, ctx):
        """'Buy Now' appears twice."""
        r = await _detect(ctx, {"text": "Buy Now", "role": "button"})
        assert r["found"] is True
        assert r["element"]["tag"] == "button"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_whitespace(self, ctx):
        r = await _detect(ctx, {"text": "Submit Form"})
        assert r["found"] is True

    @pytest.mark.asyncio(loop_scope="module")
    async def test_element_info_fields(self, ctx):
        r = await _detect(ctx, {"selector": "#email"})
        assert r["found"] is True
        el = r["element"]
        assert el["tag"] == "input"
        assert el["type"] == "email"
        assert el["name"] == "email"
        assert el["placeholder"] == "Enter your email"
        assert el["visible"] is True

    @pytest.mark.asyncio(loop_scope="module")
    async def test_status_success(self, ctx):
        r = await _detect(ctx, {"selector": "#login-btn"})
        assert r["status"] == "success"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_status_not_found(self, ctx):
        r = await _detect(ctx, {"selector": "#gone"})
        assert r["status"] == "not_found"


# ─── Tests: Dynamic Elements (timeout retry) ─────────────────────

class TestDynamic:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_delayed_element_found_with_timeout(self, ctx, local_server):
        """Element appears after 800ms — timeout=5000 should find it."""
        # Re-navigate to reset the timer
        goto_cls = ModuleRegistry.get("browser.goto")
        await goto_cls({"url": local_server}, ctx).execute()

        r = await _detect(ctx, {
            "selector": "#delayed-btn",
            "timeout": 5000,
        })
        assert r["found"] is True
        assert r["element"]["text"] == "Delayed Action"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_delayed_element_missed_with_zero_timeout(self, ctx, local_server):
        """Element appears after 800ms — timeout=0 should miss it."""
        goto_cls = ModuleRegistry.get("browser.goto")
        await goto_cls({"url": local_server}, ctx).execute()

        r = await _detect(ctx, {
            "text": "Delayed Action",
            "match_mode": "exact",
            "timeout": 0,
        })
        # With 0 timeout, only one immediate check — element hasn't appeared yet
        assert r["found"] is False


# ─── Tests: Radio Buttons ────────────────────────────────────────

class TestRadio:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_radio_by_role(self, ctx):
        r = await _detect(ctx, {"text": "Free Plan", "role": "radio"})
        assert r["found"] is True

    @pytest.mark.asyncio(loop_scope="module")
    async def test_radio_by_label(self, ctx):
        r = await _detect(ctx, {"text": "Pro Plan"})
        assert r["found"] is True


# ─── Tests: Special Characters ───────────────────────────────────

class TestSpecialChars:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_quotes_in_text(self, ctx):
        r = await _detect(ctx, {"text": 'Link with "quotes"'})
        assert r["found"] is True
        assert r["element"]["tag"] == "a"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_apostrophe_and_html(self, ctx):
        r = await _detect(ctx, {"text": "It's a", "match_mode": "contains"})
        assert r["found"] is True


# ─── Tests: Role Filter with Wrong-Type First Match ──────────────

class TestRoleFilterOrdering:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_text_matches_heading_but_role_wants_button(self, ctx):
        """'Login' matches <h2>Login</h2> first, but role=button should skip it."""
        r = await _detect(ctx, {"text": "Login", "role": "button", "match_mode": "exact"})
        assert r["found"] is True
        assert r["element"]["tag"] == "button"
        assert r["element"]["tag"] != "h2"


# ─── Tests: iframe Fallback ──────────────────────────────────────

class TestIframe:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_find_button_inside_iframe(self, ctx):
        """Button inside iframe should be found via frame fallback."""
        r = await _detect(ctx, {"text": "Login Inside Frame", "role": "button"})
        assert r["found"] is True
        assert "iframe" in r["strategy"]
        assert r["element"]["tag"] == "button"
        # Should have frame metadata
        assert r["element"].get("_frame_url") is not None or r["element"].get("_frame_name") is not None

    @pytest.mark.asyncio(loop_scope="module")
    async def test_find_input_inside_iframe(self, ctx):
        """Input inside iframe should be found."""
        r = await _detect(ctx, {"text": "Email in iframe", "role": "textbox"})
        assert r["found"] is True
        assert "iframe" in r["strategy"]

    @pytest.mark.asyncio(loop_scope="module")
    async def test_iframe_confidence_slightly_lower(self, ctx):
        """iframe matches should have slightly lower confidence."""
        r = await _detect(ctx, {"text": "Login Inside Frame", "role": "button"})
        assert r["found"] is True
        # Role match is normally 95, iframe penalty -5 = 90
        assert r["confidence"] == 90

    @pytest.mark.asyncio(loop_scope="module")
    async def test_main_page_preferred_over_iframe(self, ctx):
        """'Login' exists in both main page and iframe — main page should win."""
        r = await _detect(ctx, {"text": "Login", "role": "button"})
        assert r["found"] is True
        # Should NOT be iframe strategy — main page match wins
        assert "iframe" not in r["strategy"]


# ─── Tests: Shadow DOM ───────────────────────────────────────────

class TestShadowDOM:
    @pytest.mark.asyncio(loop_scope="module")
    async def test_find_button_in_shadow_dom(self, ctx):
        """Playwright locators can pierce open shadow DOM."""
        r = await _detect(ctx, {"text": "Shadow Button", "role": "button"})
        assert r["found"] is True
        assert r["element"]["tag"] == "button"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_find_input_in_shadow_dom(self, ctx):
        """Input inside shadow DOM found via placeholder."""
        r = await _detect(ctx, {"text": "Shadow Input"})
        assert r["found"] is True
