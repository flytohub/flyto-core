"""browser.type finds fields by explicit label association, and keeps passwords out.

Two defects, both reproduced from a real login run before this file existed:

* ``type_method: label, target: "Password"`` failed with "Could not find input
  field" on a page whose ``<label for="pw">Password</label>`` sat in a
  different container from ``<input id="pw">``. Every structural selector
  (label wrapping the input, label followed by it) misses that markup, and it
  is the ordinary output of most form frameworks. ``aria-labelledby`` is the
  same association without a ``<label>`` element.
* The typed password was recorded in plaintext, because neither ``text`` nor
  ``sensitive_text`` is named like a credential.

Run against real Chromium with ``set_content``: the association is resolved by
the page's DOM, and a stub would only test that the stub agrees with itself.
"""
import contextlib

import pytest

from core.engine.redaction import SENSITIVE_PARAMS_KEY
from core.modules import atomic  # noqa: F401 - registers every module
from core.modules.registry import ModuleRegistry

PAGE = """
<!doctype html><html><body>
  <div class="row"><label for="user-field">Email address</label></div>
  <div class="row"><div class="wrap"><input id="user-field" type="text"></div></div>

  <div class="row"><label for="pw">Password</label></div>
  <div class="row"><input id="pw" type="password"></div>

  <div class="row"><label for="pw-confirm">Confirm password</label></div>
  <div class="row"><input id="pw-confirm" type="password"></div>

  <span id="code-label">Verification code</span>
  <div><input aria-labelledby="code-label" type="text" name="code"></div>

  <label for="weird&quot;id">Nickname</label>
  <div><input id='weird"id' type="text"></div>

  <div><label for="not-a-field">Decoy</label>
  <div id="not-a-field">plain div</div></div>

  <label>Wrapped <input id="wrapped" type="text"></label>

  <input id="masked" type="password">
</body></html>
"""


async def _launch_driver():
    from core.browser.driver import BrowserDriver

    driver = BrowserDriver(headless=True)
    await driver.launch(stealth=False)
    return driver


@pytest.fixture
async def page_ctx():
    driver = await _launch_driver()
    try:
        await driver.real_page.set_content(PAGE)
        yield {"browser": driver}
    finally:
        # Teardown must not mask a failure.
        with contextlib.suppress(Exception):
            await driver.close()


async def run_type(params, context):
    return await ModuleRegistry.get("browser.type")(params, context).execute()


class TestLabelAssociation:
    async def test_label_for_in_another_container_resolves_to_the_field(self, page_ctx):
        result = await run_type(
            {"type_method": "label", "target": "Email address", "text": "a@example.test"},
            page_ctx,
        )
        assert result["selector"] == '[id="user-field"]'
        page = page_ctx["browser"].real_page
        assert await page.input_value("#user-field") == "a@example.test"

    async def test_an_exact_label_wins_over_one_that_only_contains_the_text(self, page_ctx):
        """"Password" is also a substring of "Confirm password"."""
        result = await run_type(
            {"type_method": "label", "target": "Password", "text": "x"},
            page_ctx,
        )
        assert result["selector"] == '[id="pw"]'
        page = page_ctx["browser"].real_page
        assert await page.input_value("#pw") == "x"
        assert await page.input_value("#pw-confirm") == ""

    async def test_aria_labelledby_resolves_to_the_field(self, page_ctx):
        result = await run_type(
            {"type_method": "label", "target": "Verification code", "text": "123456"},
            page_ctx,
        )
        assert result["selector"] == '[aria-labelledby="code-label"]'
        page = page_ctx["browser"].real_page
        assert await page.input_value("input[name=code]") == "123456"

    async def test_an_id_with_a_quote_is_escaped_not_broken(self, page_ctx):
        result = await run_type(
            {"type_method": "label", "target": "Nickname", "text": "nick"},
            page_ctx,
        )
        page = page_ctx["browser"].real_page
        assert await page.input_value(result["selector"]) == "nick"

    async def test_a_label_pointing_at_a_non_field_is_not_used(self, page_ctx):
        with pytest.raises(RuntimeError, match="label\\[for\\]"):
            await run_type(
                {"type_method": "label", "target": "Decoy", "text": "nope"},
                page_ctx,
            )

    async def test_a_wrapping_label_still_resolves(self, page_ctx):
        result = await run_type(
            {"type_method": "label", "target": "Wrapped", "text": "w"},
            page_ctx,
        )
        assert result["selector"] == '[id="wrapped"]'
        page = page_ctx["browser"].real_page
        assert await page.input_value("#wrapped") == "w"


class TestPasswordStaysOutOfTheResult:
    async def test_a_password_field_named_by_label_is_masked(self, page_ctx):
        result = await run_type(
            {"type_method": "label", "target": "Password", "input_type": "text",
             "text": "hunter2-not-real"},
            page_ctx,
        )
        assert result["text"] == "***"
        assert "hunter2-not-real" not in repr(result)
        assert "text" in result[SENSITIVE_PARAMS_KEY]

    async def test_element_hints_never_carry_a_password_value(self, page_ctx):
        """The hints ride along in the result; they used to quote the field."""
        result = await run_type(
            {"type_method": "id", "target": "masked", "text": "hunter2-not-real"},
            page_ctx,
        )
        assert "hunter2-not-real" not in repr(result)
        masked = [i for i in result.get("inputs", []) if i.get("id") == "masked"]
        assert masked and masked[0]["value"] == "[REDACTED]"

    async def test_a_password_input_is_detected_on_the_page(self, page_ctx):
        """Nothing in the parameters says password; the DOM does."""
        params = {"type_method": "id", "target": "masked", "input_type": "text",
                  "text": "hunter2-not-real"}
        assert ModuleRegistry.get("browser.type").sensitive_params(params) == frozenset()
        result = await run_type(params, page_ctx)
        assert result["text"] == "***"
        assert "text" in result[SENSITIVE_PARAMS_KEY]

    async def test_an_ordinary_field_is_not_flagged(self, page_ctx):
        result = await run_type(
            {"type_method": "label", "target": "Email address", "text": "a@example.test"},
            page_ctx,
        )
        assert result["text"] == "a@example.test"
        assert SENSITIVE_PARAMS_KEY not in result


class TestStaticSensitivity:
    @pytest.mark.parametrize("params", [
        {"input_type": "password", "text": "x"},
        {"type_method": "label", "target": "Password", "text": "x"},
        {"type_method": "selector", "selector": "#login-passwd", "text": "x"},
        {"type_method": "placeholder", "target": "One-time code", "text": "x"},
        {"type_method": "name", "target": "api_key", "text": "x"},
    ])
    def test_credential_fields_mark_text_sensitive(self, params):
        assert "text" in ModuleRegistry.get("browser.type").sensitive_params(params)

    @pytest.mark.parametrize("params", [
        {"type_method": "label", "target": "Email", "text": "x"},
        {"type_method": "placeholder", "target": "Footprint (m2)", "text": "x"},
        {"type_method": "selector", "selector": "#search", "text": "x"},
    ])
    def test_ordinary_fields_do_not(self, params):
        assert ModuleRegistry.get("browser.type").sensitive_params(params) == frozenset()


AMBIGUOUS_PAGES = {
    # A "Show password" checkbox wrapped in its label used to win: the
    # wrapping-label selector ran first and filled a checkbox.
    "show_password_checkbox": """
      <label for="pw">Password</label><div><input id="pw" type="password"></div>
      <label><input id="show" type="checkbox"> Show password</label>""",
    # A wrapping "Confirm password" label ahead of the real field took the
    # password: partial text matched before the exact label[for] one.
    "wrapped_confirm_first": """
      <label>Confirm password <input id="c" type="password"></label>
      <label for="pw">Password</label><div><input id="pw" type="password"></div>""",
    # A partial label[for] match ("Password hint", a plain text box) ranked
    # above the exact aria-label: the password landed in a visible field.
    "aria_exact_beats_partial_for": """
      <label for="h">Password hint</label><input id="h" type="text">
      <input id="pw" aria-label="Password" type="password">""",
    # The same form twice, the first copy hidden (mobile/desktop variants).
    "hidden_duplicate_first": """
      <div style="display:none"><label for="pw-m">Password</label><input id="pw-m" type="password"></div>
      <label for="pw">Password</label><input id="pw" type="password">""",
    # A wrapping label with no id or name on the field: a structural path.
    "wrapped_without_attributes": """
      <div><label>Hint <input type="text"></label></div>
      <div><label>Password <input type="password"></label></div>""",
}


@pytest.fixture
async def driver():
    drv = await _launch_driver()
    try:
        yield drv
    finally:
        with contextlib.suppress(Exception):
            await drv.close()


class TestTheExactVisibleFieldWins:
    @pytest.mark.parametrize("name", sorted(AMBIGUOUS_PAGES))
    async def test_password_lands_in_the_field_labelled_password(self, driver, name):
        page = driver.real_page
        await page.set_content(f"<!doctype html><html><body>{AMBIGUOUS_PAGES[name]}</body></html>")
        await run_type(
            {"type_method": "label", "target": "Password", "text": "hunter2-not-real"},
            {"browser": driver},
        )
        values = await page.evaluate(
            "() => [...document.querySelectorAll('input')].map((e) =>"
            " [e.closest('label') ? e.closest('label').textContent.trim() : (e.id || ''),"
            "  e.type === 'checkbox' ? String(e.checked) : e.value])"
        )
        typed = [label for label, value in values if value == "hunter2-not-real"]
        assert len(typed) == 1, values
        target = await page.evaluate(
            "() => { const e = [...document.querySelectorAll('input')]"
            ".find((n) => n.value === 'hunter2-not-real');"
            " return [e.type, e.id, e.closest('label') ? e.closest('label').textContent.trim() : '',"
            " e.getAttribute('aria-label') || ''] }"
        )
        assert target[0] == "password"
        assert target[1] in ("pw", "") and (target[1] == "pw" or target[2] == "Password")
