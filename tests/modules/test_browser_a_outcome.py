# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the browser modules are entitled to claim, and the line that earns it.

Named for the `browser-a` slice of the browser category rather than for the
category itself, so that a second pass over the remaining browser modules can
land beside this file instead of on top of it.

Every browser module in this group had the same defect in the same place: the
thing it reported about its own effect was a parameter it had been handed.
`browser.type` reported ``text_length`` -- ``len(self.text)``. `browser.select`
returned ``[str(self.target)]`` from its custom-dropdown path. `browser.upload`
reported ``path.stat().st_size`` on the LOCAL file. `browser.viewport` returned
the width and height it was asked for. `browser.screenshot` returned the path it
was asked to write to, having never looked at the filesystem. Each is
`file.write`'s ``bytes_written`` wearing different clothes: a number that is
byte-identical whether the effect happened or not.

So the tests come in two layers, and the second is the one that matters:

* the ``TestRung*`` classes drive the decision functions directly and pin every
  branch, including the ones a real browser will not produce on demand.
* the ``@pytest.mark.browser`` classes run the modules against a real Chromium
  and, where a file is involved, a real HTTP server -- and check the reported
  number against an INDEPENDENT measurement taken by the test itself. A value
  that quietly goes back to being an echo of the input fails there, which is the
  only place it can be caught.

Two negative results are pinned here as tests rather than left as prose, because
both are about a rung that was written and then taken back out:

* :class:`TestSmoothScrollCannotBeObserved` -- ``behavior='smooth'`` is this
  module's DEFAULT, ``scrollBy`` returns before the animation runs, and the
  scroll offset is therefore unchanged when it is read. ACCEPTED is not a
  shortcoming of the measurement there; it is the measurement working.
* :class:`TestHoverHasNoObservableSignal` -- `browser.hover` is deliberately
  still undeclared. The test records the reason as an executable fact so that
  the next person to reach for ``:hover`` finds the measurement rather than the
  argument.
"""

import http.server
import socketserver
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import core.modules.atomic.browser.close as close_module
import core.modules.atomic.browser.cookies as cookies_module
import core.modules.atomic.browser.download as download_module
import core.modules.atomic.browser.evaluate as evaluate_module
import core.modules.atomic.browser.goto as goto_module
import core.modules.atomic.browser.pdf as pdf_module
import core.modules.atomic.browser.screenshot as screenshot_module
import core.modules.atomic.browser.scroll as scroll_module
import core.modules.atomic.browser.select as select_module
import core.modules.atomic.browser.storage as storage_module
import core.modules.atomic.browser.type as type_module
import core.modules.atomic.browser.upload as upload_module
import core.modules.atomic.browser.viewport as viewport_module
from core.engine.outcome import ClaimBy, Outcome, ceiling_for, read_envelope
from core.modules import atomic  # noqa: F401 - registers every module
from core.modules.registry import ModuleRegistry


# ---------------------------------------------------------------------------
# Reading a result the way step_executor reads it
# ---------------------------------------------------------------------------

def envelope_of(result):
    """The outcome envelope, read exactly as `_payload_outcome` reads it.

    These modules return a flat dict with no ``data`` key, so
    ``wrap_legacy_result`` sweeps their fields into ``data`` and the envelope
    survives at the top level. Reading it through ``read_envelope`` rather than
    ``result['outcome']`` is deliberate: a malformed rung comes back as None
    here, the same way it would reach a consumer.
    """
    return read_envelope(result)


def rung_of(result):
    return envelope_of(result)["rung"]


def effect_kinds(found):
    return [effect["kind"] for effect in found["effects"]]


def effect_named(found, kind):
    return next(effect for effect in found["effects"] if effect["kind"] == kind)


async def run_module(module_id, params, context):
    """Execute a module the way the engine does, and return its result dict."""
    return await ModuleRegistry.get(module_id)(params, context).execute()


# ---------------------------------------------------------------------------
# Real browser, real server
# ---------------------------------------------------------------------------

PAGE_HTML = (
    b'<html><body style="height:5000px;width:5000px">'
    b'<h1>hello</h1>'
    b'<input id="text-field" placeholder="Email">'
    b'<input id="readonly-field" value="fixed" readonly>'
    b'<div id="editor" contenteditable="true">rich</div>'
    b'<select id="picker"><option value="x">X</option><option value="y">Y</option></select>'
    b'<a id="dl" href="/file.bin" download="f.bin">download</a>'
    b'<input type="file" id="file-input">'
    b'</body></html>'
)

DOWNLOAD_BYTES = b"0123456789"


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the test output readable
        pass

    def do_GET(self):
        if self.path == "/file.bin":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="f.bin"')
            self.end_headers()
            self.wfile.write(DOWNLOAD_BYTES)
            return
        if self.path == "/missing":
            self.send_response(404)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>not here</body></html>")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(PAGE_HTML)


@pytest.fixture
def http_site(monkeypatch):
    """A real origin to navigate to, with the SSRF guard opened for loopback.

    A real server rather than ``set_content``: `browser.goto`'s rung rests on
    ``response.status``, and a page that was never fetched has no response
    object at all. Loopback is exactly what the guard exists to refuse, so the
    opt-out is scoped to this fixture and nothing else.
    """
    monkeypatch.setenv("FLYTO_ALLOW_PRIVATE_NETWORK", "true")
    server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


async def _launch_driver():
    from core.browser.driver import BrowserDriver

    driver = BrowserDriver(headless=True)
    await driver.launch(stealth=False)
    return driver


@pytest.fixture
async def browser_ctx():
    """A launched driver in an execution context, torn down after the test."""
    driver = await _launch_driver()
    try:
        yield {"browser": driver}
    finally:
        try:
            await driver.close()
        except Exception:  # noqa: BLE001 - teardown must not mask a failure
            pass


@pytest.fixture
async def loaded_ctx(browser_ctx):
    """`browser_ctx`, with the fixture page rendered into it."""
    await browser_ctx["browser"].real_page.set_content(PAGE_HTML.decode())
    return browser_ctx


@pytest.fixture
def sandbox(sandboxed_tmp_path):
    """A directory the path-restricted browser modules are allowed to write to."""
    return sandboxed_tmp_path


# ===========================================================================
# browser.goto -- the URL is not the evidence, the status code is
# ===========================================================================

class TestRungGoto:
    """Every branch of `_navigation_outcome`, driven directly."""

    def test_a_status_code_is_observed(self):
        found = goto_module._navigation_outcome(
            final_url="https://example.test/", status_code=200
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "navigation_response")["status_code"] == 200

    @pytest.mark.parametrize("code", [301, 404, 500])
    def test_a_non_2xx_status_is_still_observed(self, code):
        """The rung says how far we followed the effect, not whether we liked it."""
        found = goto_module._navigation_outcome(
            final_url="https://example.test/", status_code=code
        )
        assert found["rung"] == Outcome.OBSERVED.value

    def test_no_response_object_is_only_accepted(self):
        found = goto_module._navigation_outcome(
            final_url="https://example.test/#anchor", status_code=None
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "navigation_not_measured")["measured_by"] is None

    def test_a_recovered_http_error_carries_its_warning(self):
        found = goto_module._navigation_outcome(
            final_url="https://example.test/",
            status_code=None,
            warning="HTTP error response, but page loaded",
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert "HTTP error" in effect_named(found, "navigation_not_measured")["reason"]

    def test_a_bool_is_not_a_status_code(self):
        """`True` is an `int` in Python and is not an HTTP status.

        Worth a test rather than a comment: `isinstance(True, int)` is the
        classic way a guard like this one lets a non-measurement through.
        """
        found = goto_module._navigation_outcome(final_url="x", status_code=True)
        assert found["rung"] == Outcome.ACCEPTED.value


@pytest.mark.browser
class TestGotoAgainstARealServer:
    async def test_a_served_page_is_observed_with_its_status(self, browser_ctx, http_site):
        result = await run_module("browser.goto", {"url": http_site + "/"}, browser_ctx)
        assert result["status_code"] == 200
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "navigation_response")["status_code"] == 200

    async def test_a_404_is_observed_and_says_so(self, browser_ctx, http_site):
        """The page loaded and the server said 404. Both are true at once."""
        result = await run_module("browser.goto", {"url": http_site + "/missing"}, browser_ctx)
        assert result["status_code"] == 404
        assert rung_of(result) == Outcome.OBSERVED.value

    async def test_the_status_code_reaches_the_output(self, browser_ctx, http_site):
        """It was measured by the driver and then dropped on the floor."""
        result = await run_module("browser.goto", {"url": http_site + "/"}, browser_ctx)
        assert "status_code" in result


# ===========================================================================
# browser.type -- text_length is the input; input_value is the page
# ===========================================================================

class TestRungType:
    def test_the_field_holding_baseline_plus_text_is_verified(self):
        """The predicate this module declares, evaluated and holding.

        INFERRED even at VERIFIED: the predicate is this module's own
        declaration, not something a caller passed in, so the holding and the
        failing case stay attributable to one author. `file.edit` uses the same
        value for the same reason.
        """
        found = type_module._type_outcome(
            baseline="", after="hello", typed_characters=5,
            expected="hello", read_error=None,
        )
        assert found["rung"] == Outcome.VERIFIED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value
        assert found["postcondition"] == type_module.POSTCONDITION
        assert effect_named(found, "field_value_observed")["matches_expected"] is True

    def test_only_the_holding_branch_carries_the_postcondition(self):
        """The other three evaluated it and it did NOT hold, or never ran it.

        A predicate sentence on those would be the engine-side overreach in
        module form: `postcondition` names what held, so a branch where nothing
        held must leave it empty.
        """
        mask = type_module._type_outcome(
            baseline="", after="he", typed_characters=5,
            expected="hello", read_error=None,
        )
        unchanged = type_module._type_outcome(
            baseline="x", after="x", typed_characters=5,
            expected="xhello", read_error=None,
        )
        unread = type_module._type_outcome(
            baseline=None, after=None, typed_characters=5,
            expected=None, read_error="detached",
        )

        assert mask["rung"] == Outcome.OBSERVED.value
        assert unchanged["rung"] == Outcome.INDETERMINATE.value
        assert unread["rung"] == Outcome.ACCEPTED.value
        for found in (mask, unchanged, unread):
            assert found["postcondition"] is None

    def test_a_field_that_changed_to_something_else_is_still_observed(self):
        """An input mask reformatting a correct type. The world changed."""
        found = type_module._type_outcome(
            baseline="", after="(555) 123-4567", typed_characters=10,
            expected="5551234567", read_error=None,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert "field_value_differs" in effect_kinds(found)

    def test_a_field_that_did_not_change_is_indeterminate(self):
        found = type_module._type_outcome(
            baseline="fixed", after="fixed", typed_characters=5,
            expected="fixedhello", read_error=None,
        )
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert found["claim_by"] == ClaimBy.INFERRED.value

    def test_without_the_read_back_it_is_only_accepted(self):
        found = type_module._type_outcome(
            baseline=None, after=None, typed_characters=5,
            expected=None, read_error="Error: not an <input> element",
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "field_value_not_observed")["measured_by"] is None

    def test_no_effect_carries_the_typed_value(self):
        """This module types passwords into an envelope that is copied to a DB."""
        secret = "hunter2-correct-horse"
        found = type_module._type_outcome(
            baseline="", after=secret, typed_characters=len(secret),
            expected=secret, read_error=None,
        )
        assert secret not in repr(found)
        assert effect_named(found, "field_value_observed")["characters_after"] == len(secret)


@pytest.mark.browser
class TestTypeAgainstARealPage:
    async def test_typing_into_an_input_is_verified(self, loaded_ctx):
        """The read-back holds, so this is the one branch that may say VERIFIED.

        It goes through a different channel than the write -- keyboard out,
        `page.input_value` back -- which is what makes it evidence rather than
        an echo of the parameter.
        """
        result = await run_module(
            "browser.type",
            {"type_method": "id", "target": "text-field", "text": "hello"},
            loaded_ctx,
        )
        assert rung_of(result) == Outcome.VERIFIED.value
        assert envelope_of(result)["postcondition"], (
            "a VERIFIED claim has to name the predicate that held"
        )
        # Independent of anything the module reported.
        page = loaded_ctx["browser"].real_page
        assert await page.input_value("#text-field") == "hello"

    async def test_a_readonly_field_is_indeterminate(self, loaded_ctx):
        """The keystrokes went somewhere. Nothing we can see moved."""
        result = await run_module(
            "browser.type",
            {"type_method": "id", "target": "readonly-field", "text": "hello",
             "clear": False},
            loaded_ctx,
        )
        assert rung_of(result) == Outcome.INDETERMINATE.value
        assert "field_value_unchanged" in effect_kinds(envelope_of(result))

    async def test_a_contenteditable_falls_back_to_accepted(self, loaded_ctx):
        """`input_value` raises on a div. The typing is fine; the looking is not."""
        result = await run_module(
            "browser.type",
            {"type_method": "id", "target": "editor", "text": "more"},
            loaded_ctx,
        )
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert "field_value_not_observed" in effect_kinds(envelope_of(result))

    async def test_retyping_the_same_value_is_not_indeterminate(self, loaded_ctx):
        """The baseline is read AFTER the clear, and this is why.

        Reading it before would make "clear the field, type back what was
        already there" look like a field that never changed.
        """
        page = loaded_ctx["browser"].real_page
        await page.fill("#text-field", "same")
        result = await run_module(
            "browser.type",
            {"type_method": "id", "target": "text-field", "text": "same", "clear": True},
            loaded_ctx,
        )
        assert rung_of(result) == Outcome.VERIFIED.value

    async def test_the_claim_falls_when_the_measurement_is_blinded(self, loaded_ctx, monkeypatch):
        """Stage 1: with no read-back, the honest floor is ACCEPTED."""
        async def blind(page, selector):
            return None, "OSError: stubbed unavailable"

        monkeypatch.setattr(type_module, "_read_field_value", blind)
        result = await run_module(
            "browser.type",
            {"type_method": "id", "target": "text-field", "text": "hello"},
            loaded_ctx,
        )
        assert rung_of(result) == Outcome.ACCEPTED.value


# ===========================================================================
# browser.select -- one output key, two very different amounts of evidence
# ===========================================================================

class TestRungSelect:
    def test_a_native_select_that_reported_options_is_observed(self):
        found = select_module._select_outcome(
            native=True, selected=["y"], selector="#picker"
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "options_selected")["selected_measured"] is True

    def test_a_native_select_that_reported_nothing_is_accepted(self):
        found = select_module._select_outcome(native=True, selected=[], selector="#picker")
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_a_custom_dropdown_is_accepted_however_full_the_list_looks(self):
        """`[str(self.target)]` is the parameter. A longer list changes nothing."""
        found = select_module._select_outcome(
            native=False, selected=["us", "ca", "mx"], selector=".combo"
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "custom_dropdown_option_clicked")["selected_measured"] is False


@pytest.mark.browser
class TestSelectAgainstARealPage:
    async def test_a_native_select_is_observed_and_the_dom_agrees(self, loaded_ctx):
        result = await run_module(
            "browser.select",
            {"selector": "#picker", "select_method": "value", "target": "y"},
            loaded_ctx,
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        page = loaded_ctx["browser"].real_page
        assert await page.input_value("#picker") == "y"
        assert effect_named(envelope_of(result), "options_selected")["values"] == ["y"]


# ===========================================================================
# browser.upload -- st_size is this host; el.files is the page
# ===========================================================================

class TestRungUpload:
    def test_an_attached_file_is_observed(self):
        found = upload_module._upload_outcome(
            offered_name="up.txt", offered_bytes=6,
            attached=[{"name": "up.txt", "size": 6}],
            read_error=None, selector="#file-input",
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "files_attached")["count"] == 1

    def test_an_empty_file_list_is_indeterminate(self):
        found = upload_module._upload_outcome(
            offered_name="up.txt", offered_bytes=6, attached=[],
            read_error=None, selector="#file-input",
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_an_unreadable_element_is_accepted(self):
        found = upload_module._upload_outcome(
            offered_name="up.txt", offered_bytes=6, attached=None,
            read_error="the element exposes no FileList (not a file input)",
            selector="#not-a-file-input",
        )
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_the_offered_size_is_labelled_as_the_input_it_is(self):
        found = upload_module._upload_outcome(
            offered_name="up.txt", offered_bytes=6, attached=None,
            read_error="x", selector="#file-input",
        )
        offered = effect_named(found, "file_offered")
        assert "local file" in offered["measured_by"]


@pytest.mark.browser
class TestUploadAgainstARealPage:
    async def test_the_browser_reports_the_file_it_holds(self, loaded_ctx, sandbox):
        source = sandbox / "up.txt"
        source.write_bytes(b"abcdef")

        result = await run_module(
            "browser.upload",
            {"selector": "#file-input", "file_path": str(source)},
            loaded_ctx,
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        # The read-back is the page's, not a copy of the parameters: compare it
        # against an independent stat taken here.
        assert result["attached_files"] == [{"name": "up.txt", "size": source.stat().st_size}]

    async def test_a_non_file_input_falls_back_to_accepted(self, loaded_ctx, sandbox, monkeypatch):
        """`set_input_files` is stubbed out; only the read-back is under test."""
        source = sandbox / "up.txt"
        source.write_bytes(b"abcdef")

        async def no_op(*args, **kwargs):
            return None

        monkeypatch.setattr(loaded_ctx["browser"].page, "set_input_files", no_op)
        result = await run_module(
            "browser.upload",
            {"selector": "#text-field", "file_path": str(source)},
            loaded_ctx,
        )
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert result["attached_files"] is None


# ===========================================================================
# browser.scroll -- the baseline is the whole difference
# ===========================================================================

class TestRungScroll:
    def test_a_moved_offset_is_observed(self):
        found = scroll_module._scroll_outcome(
            before={"x": 0, "y": 0}, after={"x": 0, "y": 300},
            smooth=False, target="down",
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "scroll_offset_changed")["moved"] == {"x": 0, "y": 300}

    def test_an_unmoved_offset_is_accepted(self):
        found = scroll_module._scroll_outcome(
            before={"x": 0, "y": 300}, after={"x": 0, "y": 300},
            smooth=False, target="down",
        )
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_the_smooth_case_says_why_it_could_not_see(self):
        found = scroll_module._scroll_outcome(
            before={"x": 0, "y": 0}, after={"x": 0, "y": 0},
            smooth=True, target="down",
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert "smooth" in effect_named(found, "scroll_offset_unchanged")["detail"]

    def test_an_unreadable_offset_is_accepted(self):
        found = scroll_module._scroll_outcome(
            before=None, after={"x": 0, "y": 1}, smooth=False, target="#footer",
        )
        assert found["rung"] == Outcome.ACCEPTED.value


@pytest.mark.browser
class TestScrollAgainstARealPage:
    async def test_an_instant_scroll_is_observed(self, loaded_ctx):
        result = await run_module(
            "browser.scroll",
            {"direction": "down", "amount": 300, "behavior": "instant"},
            loaded_ctx,
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        page = loaded_ctx["browser"].real_page
        assert await page.evaluate("() => window.scrollY") == 300

    async def test_scrolling_at_the_top_of_a_page_is_accepted(self, loaded_ctx):
        """A correct no-op. Nothing moved, so nothing is observed."""
        result = await run_module(
            "browser.scroll",
            {"direction": "up", "amount": 300, "behavior": "instant"},
            loaded_ctx,
        )
        assert rung_of(result) == Outcome.ACCEPTED.value


@pytest.mark.browser
class TestSmoothScrollCannotBeObserved:
    """The DEFAULT behaviour of this module cannot see its own effect.

    ``behavior='smooth'`` reaches ``window.scrollBy``, which returns immediately
    and lets the compositor animate afterwards; the offset read on the next line
    is the offset the page was already at. This is pinned as a test because it is
    the reason the unchanged case must be ACCEPTED and not FAILED -- a correct
    scroll lands here, every time, on the default settings.
    """

    async def test_the_default_smooth_scroll_reports_accepted(self, loaded_ctx):
        result = await run_module(
            "browser.scroll", {"direction": "down", "amount": 300}, loaded_ctx
        )
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert result["scroll_offset"]["moved"] == {"x": 0, "y": 0}


# ===========================================================================
# browser.screenshot / browser.pdf / browser.download -- the file, or not
# ===========================================================================

class TestRungScreenshot:
    def test_a_file_on_disk_is_observed(self):
        found = screenshot_module._screenshot_outcome(
            path="/tmp/s.png", bytes_on_disk=9510, stat_error=None, image_bytes=9510,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "image_file_written")["bytes_on_disk"] == 9510

    def test_a_requested_path_with_no_file_is_indeterminate(self):
        found = screenshot_module._screenshot_outcome(
            path="/tmp/s.png", bytes_on_disk=None,
            stat_error="FileNotFoundError: No such file or directory",
            image_bytes=9510,
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_bytes_without_a_path_are_observed(self):
        found = screenshot_module._screenshot_outcome(
            path=None, bytes_on_disk=None, stat_error=None, image_bytes=9510,
        )
        assert found["rung"] == Outcome.OBSERVED.value

    def test_neither_a_path_nor_bytes_is_accepted(self):
        found = screenshot_module._screenshot_outcome(
            path=None, bytes_on_disk=None, stat_error=None, image_bytes=None,
        )
        assert found["rung"] == Outcome.ACCEPTED.value

    @pytest.mark.parametrize(
        "payload,expected",
        [("", 0), ("QQ==", 1), ("QUJD", 3), ("QUJDRA==", 4), ("not-base64", None)],
    )
    def test_the_byte_count_is_exact_without_decoding(self, payload, expected):
        assert screenshot_module._decoded_length(payload) == expected


@pytest.mark.browser
class TestScreenshotAgainstARealPage:
    async def test_the_written_image_is_read_back_off_disk(self, loaded_ctx, sandbox):
        target = sandbox / "shot.png"
        result = await run_module(
            "browser.screenshot", {"path": str(target)}, loaded_ctx
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        # Independent measurement. If `bytes_on_disk` ever goes back to being
        # the path we asked for, this is where it fails.
        assert result["bytes_on_disk"] == target.stat().st_size
        assert result["image_bytes"] == target.stat().st_size

    async def test_a_vanished_file_is_indeterminate_not_success(self, loaded_ctx, sandbox, monkeypatch):
        """The defect this fixes: `filepath` was the request, never a finding."""
        monkeypatch.setattr(
            screenshot_module, "_observe_file_on_disk",
            lambda path: (None, "FileNotFoundError: No such file or directory"),
        )
        result = await run_module(
            "browser.screenshot", {"path": str(sandbox / "shot.png")}, loaded_ctx
        )
        assert result["status"] == "success"
        assert rung_of(result) == Outcome.INDETERMINATE.value


class TestRungPdf:
    def test_a_written_pdf_is_observed(self):
        found = pdf_module._pdf_outcome(path="/tmp/p.pdf", exists=True, size=6564)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "pdf_file_written")["bytes_on_disk"] == 6564

    def test_a_missing_pdf_is_indeterminate(self):
        found = pdf_module._pdf_outcome(path="/tmp/p.pdf", exists=False, size=0)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "literal" in effect_named(found, "pdf_file_missing")["detail"]

    def test_an_empty_but_present_file_is_still_observed(self):
        """0 bytes ON DISK is a fact about the export, not a gap in the looking."""
        found = pdf_module._pdf_outcome(path="/tmp/p.pdf", exists=True, size=0)
        assert found["rung"] == Outcome.OBSERVED.value


@pytest.mark.browser
class TestPdfAgainstARealPage:
    async def test_the_written_pdf_is_read_back_off_disk(self, loaded_ctx, sandbox):
        target = sandbox / "out.pdf"
        result = await run_module("browser.pdf", {"path": str(target)}, loaded_ctx)
        assert rung_of(result) == Outcome.OBSERVED.value
        assert result["size"] == target.stat().st_size > 0


class TestRungDownload:
    def test_a_saved_file_is_observed(self):
        found = download_module._download_outcome(
            save_path="/tmp/d.bin", exists=True, size=10, suggested_filename="f.bin",
        )
        assert found["rung"] == Outcome.OBSERVED.value

    def test_a_missing_file_is_indeterminate(self):
        """It reported `status: success` with `size: 0` before this."""
        found = download_module._download_outcome(
            save_path="/tmp/d.bin", exists=False, size=0, suggested_filename="f.bin",
        )
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert found["claim_by"] == ClaimBy.INFERRED.value

    def test_the_two_zeroes_are_told_apart(self):
        """`size == 0` alone cannot distinguish an empty file from no file."""
        empty = download_module._download_outcome(
            save_path="/tmp/d.bin", exists=True, size=0, suggested_filename=None,
        )
        absent = download_module._download_outcome(
            save_path="/tmp/d.bin", exists=False, size=0, suggested_filename=None,
        )
        assert empty["rung"] != absent["rung"]


@pytest.mark.browser
class TestDownloadAgainstARealServer:
    async def test_the_saved_bytes_are_read_back_off_disk(self, browser_ctx, http_site, sandbox):
        await run_module("browser.goto", {"url": http_site + "/"}, browser_ctx)
        target = sandbox / "saved.bin"
        result = await run_module(
            "browser.download",
            {"selector": "#dl", "save_path": str(target)},
            browser_ctx,
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        assert result["size"] == len(DOWNLOAD_BYTES) == target.stat().st_size


# ===========================================================================
# browser.viewport -- the request, and what the document says about itself
# ===========================================================================

class TestRungViewport:
    def test_the_requested_size_is_observed(self):
        found = viewport_module._viewport_outcome(
            requested={"width": 500, "height": 400},
            before={"width": 1920, "height": 1080},
            after={"width": 500, "height": 400},
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "inner_size_observed")["matches_requested"] is True

    def test_a_no_op_resize_to_the_current_size_is_observed(self):
        """State-setting: the page is in the requested state, and we measured it."""
        size = {"width": 500, "height": 400}
        found = viewport_module._viewport_outcome(
            requested=dict(size), before=dict(size), after=dict(size)
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "inner_size_observed")["changed"] is False

    def test_a_changed_but_clamped_size_is_observed(self):
        found = viewport_module._viewport_outcome(
            requested={"width": 500, "height": 400},
            before={"width": 1920, "height": 1080},
            after={"width": 485, "height": 400},
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert "inner_size_differs" in effect_kinds(found)

    def test_neither_changed_nor_matching_is_indeterminate(self):
        found = viewport_module._viewport_outcome(
            requested={"width": 500, "height": 400},
            before={"width": 1920, "height": 1080},
            after={"width": 1920, "height": 1080},
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_an_unaskable_page_is_accepted(self):
        found = viewport_module._viewport_outcome(
            requested={"width": 500, "height": 400}, before=None, after=None
        )
        assert found["rung"] == Outcome.ACCEPTED.value


@pytest.mark.browser
class TestViewportAgainstARealPage:
    async def test_the_document_reports_the_new_size(self, loaded_ctx):
        result = await run_module(
            "browser.viewport", {"width": 500, "height": 400}, loaded_ctx
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        page = loaded_ctx["browser"].real_page
        assert await page.evaluate("() => window.innerWidth") == 500
        assert result["inner_size"]["after"] == {"width": 500, "height": 400}


# ===========================================================================
# browser.evaluate -- ACCEPTED is the ceiling, not a gap
# ===========================================================================

class TestRungEvaluate:
    @pytest.mark.parametrize("value", [None, 0, 2, "", "text", [], {}, [1, 2]])
    def test_every_return_value_is_accepted(self, value):
        """The rung is flat because the effect is the caller's opaque script."""
        found = evaluate_module._evaluate_outcome(returned=value)
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_the_effect_records_the_shape_and_not_the_value(self):
        found = evaluate_module._evaluate_outcome(returned="sk-secret-token")
        assert "sk-secret-token" not in repr(found)
        assert effect_named(found, "script_executed")["returned_type"] == "str"


@pytest.mark.browser
class TestEvaluateAgainstARealPage:
    async def test_a_script_that_changes_nothing_and_one_that_does_agree(self, loaded_ctx):
        """Same rung both ways, which is the point of the ceiling."""
        pure = await run_module("browser.evaluate", {"script": "return 1 + 1"}, loaded_ctx)
        mutating = await run_module(
            "browser.evaluate",
            {"script": "document.querySelector('h1').remove(); return 'done'"},
            loaded_ctx,
        )
        assert pure["result"] == 2
        assert rung_of(pure) == rung_of(mutating) == Outcome.ACCEPTED.value
        page = loaded_ctx["browser"].real_page
        assert await page.evaluate("() => !!document.querySelector('h1')") is False


# ===========================================================================
# browser.close -- "closed successfully" was a string literal
# ===========================================================================

class _StubBrowser:
    def __init__(self, connected):
        self._connected = connected

    def is_connected(self):
        return self._connected


class TestRungClose:
    def test_a_disconnected_browser_is_observed(self):
        disconnected, reason = close_module._observe_disconnected(_StubBrowser(False))
        assert (disconnected, reason) == (True, None)
        found = close_module._close_outcome(disconnected=disconnected, reason=reason)
        assert found["rung"] == Outcome.OBSERVED.value

    def test_a_still_connected_browser_is_indeterminate(self):
        disconnected, reason = close_module._observe_disconnected(_StubBrowser(True))
        assert disconnected is False
        found = close_module._close_outcome(disconnected=disconnected, reason=reason)
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_no_browser_object_is_accepted(self):
        disconnected, reason = close_module._observe_disconnected(None)
        assert disconnected is None and reason
        found = close_module._close_outcome(disconnected=disconnected, reason=reason)
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_a_raising_browser_object_is_accepted_not_crashed(self):
        class Exploding:
            def is_connected(self):
                raise RuntimeError("connection already disposed")

        disconnected, reason = close_module._observe_disconnected(Exploding())
        assert disconnected is None
        assert "RuntimeError" in reason


@pytest.mark.browser
class TestCloseAgainstARealBrowser:
    async def test_a_persistent_context_has_no_browser_object_to_ask(self, browser_ctx):
        """The default local launch. ACCEPTED is the honest ceiling for it."""
        driver = browser_ctx["browser"]
        assert driver._browser is None
        result = await run_module("browser.close", {}, dict(browser_ctx))
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert "browser_state_not_observed" in effect_kinds(envelope_of(result))

    async def test_a_regular_launch_observes_the_disconnect(self, monkeypatch):
        """DEPLOYMENT_MODE=worker skips the persistent context, so there is a
        real `Browser` object to hold across close() and ask afterwards."""
        monkeypatch.setenv("DEPLOYMENT_MODE", "worker")
        driver = await _launch_driver()
        assert driver._browser is not None
        result = await run_module("browser.close", {}, {"browser": driver})
        assert rung_of(result) == Outcome.OBSERVED.value
        assert "browser_disconnected" in effect_kinds(envelope_of(result))

    async def test_nothing_to_close_claims_nothing(self):
        """No driver in context: no instruction was issued, so no rung is written."""
        result = await run_module("browser.close", {}, {})
        assert result["status"] == "warning"
        assert envelope_of(result) is None


# ===========================================================================
# browser.storage -- three actions that used to return a literal True
# ===========================================================================

class TestRungStorage:
    def test_a_read_is_observed(self):
        found = storage_module._read_outcome(
            action="get", storage_name="localStorage",
            measured="localStorage.getItem(key) evaluated in the page", value="5",
        )
        assert found["rung"] == Outcome.OBSERVED.value

    def test_a_null_get_is_still_observed(self):
        """`getItem` answers about one key. null means that key is absent.

        Deliberately different from `database.query`, where an empty result set
        is only ACCEPTED because several different things produce it.
        """
        found = storage_module._read_outcome(
            action="get", storage_name="localStorage",
            measured="localStorage.getItem(key) evaluated in the page", value=None,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "storage_read")["result_type"] == "NoneType"

    def test_a_confirmed_write_is_observed(self):
        found = storage_module._write_outcome(
            action="set", storage_name="localStorage", holds=True,
            predicate="p", measured="m", observed_detail="held", unmet_detail="not",
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value

    def test_a_write_the_store_disagrees_with_is_indeterminate(self):
        found = storage_module._write_outcome(
            action="set", storage_name="localStorage", holds=False,
            predicate="p", measured="m", observed_detail="held", unmet_detail="not",
        )
        assert found["rung"] == Outcome.INDETERMINATE.value


@pytest.mark.browser
class TestStorageAgainstARealPage:
    @pytest.fixture
    async def origin_ctx(self, browser_ctx, http_site):
        """localStorage needs a real origin; about:blank has no store."""
        await run_module("browser.goto", {"url": http_site + "/"}, browser_ctx)
        await run_module("browser.storage", {"action": "clear"}, browser_ctx)
        return browser_ctx

    async def test_set_reports_what_the_store_holds_not_what_was_sent(self, origin_ctx):
        result = await run_module(
            "browser.storage", {"action": "set", "key": "k", "value": 5}, origin_ctx
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        # The store is a string store. `value` is the parameter, 5; the
        # read-back is what it actually holds.
        assert result["value"] == 5
        assert result["stored_value"] == "5"

    async def test_remove_is_read_back_rather_than_asserted(self, origin_ctx):
        await run_module(
            "browser.storage", {"action": "set", "key": "k", "value": "v"}, origin_ctx
        )
        result = await run_module(
            "browser.storage", {"action": "remove", "key": "k"}, origin_ctx
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        assert result["removed"] is True
        page = origin_ctx["browser"].real_page
        assert await page.evaluate("() => localStorage.getItem('k')") is None

    async def test_a_key_written_back_by_the_page_makes_remove_indeterminate(self, origin_ctx):
        """`removed: True` used to be a literal, and this is what it hid."""
        page = origin_ctx["browser"].real_page
        # A page script that reinstates the key the moment it is removed. The
        # module's removeItem runs, and the key is back before it can look.
        await page.evaluate(
            "() => { localStorage.setItem('k', 'v');"
            "  const o = localStorage.removeItem.bind(localStorage);"
            "  localStorage.removeItem = (k) => { o(k); localStorage.setItem(k, 'v'); }; }"
        )
        result = await run_module(
            "browser.storage", {"action": "remove", "key": "k"}, origin_ctx
        )
        assert rung_of(result) == Outcome.INDETERMINATE.value
        assert result["removed"] is False

    async def test_clear_reports_what_remains(self, origin_ctx):
        await run_module(
            "browser.storage", {"action": "set", "key": "k", "value": "v"}, origin_ctx
        )
        result = await run_module("browser.storage", {"action": "clear"}, origin_ctx)
        assert rung_of(result) == Outcome.OBSERVED.value
        assert result["cleared"] is True and result["remaining"] == 0

    async def test_keys_and_length_are_observed(self, origin_ctx):
        await run_module(
            "browser.storage", {"action": "set", "key": "k", "value": "v"}, origin_ctx
        )
        keys = await run_module("browser.storage", {"action": "keys"}, origin_ctx)
        length = await run_module("browser.storage", {"action": "length"}, origin_ctx)
        assert rung_of(keys) == rung_of(length) == Outcome.OBSERVED.value
        assert keys["keys"] == ["k"] and length["length"] == 1


# ===========================================================================
# browser.cookies -- `count: 1` was a literal, and add_cookies drops silently
# ===========================================================================

class TestRungCookies:
    def test_a_jar_read_is_observed_even_when_empty(self):
        found = cookies_module._jar_read_outcome(action="get", count=0, filtered_by="x")
        assert found["rung"] == Outcome.OBSERVED.value

    def test_a_confirmed_jar_write_is_observed(self):
        found = cookies_module._jar_write_outcome(
            action="set", holds=True, predicate="p",
            observed_detail="held", unmet_detail="not",
        )
        assert found["rung"] == Outcome.OBSERVED.value

    def test_a_jar_that_disagrees_is_indeterminate(self):
        found = cookies_module._jar_write_outcome(
            action="set", holds=False, predicate="p",
            observed_detail="held", unmet_detail="not",
        )
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert found["claim_by"] == ClaimBy.INFERRED.value


@pytest.mark.browser
class TestCookiesAgainstARealBrowser:
    @pytest.fixture
    async def origin_ctx(self, browser_ctx, http_site):
        await run_module("browser.goto", {"url": http_site + "/"}, browser_ctx)
        await run_module("browser.cookies", {"action": "clear"}, browser_ctx)
        return browser_ctx

    async def test_a_stored_cookie_is_observed_and_the_jar_agrees(self, origin_ctx):
        result = await run_module(
            "browser.cookies",
            {"action": "set", "name": "c1", "value": "v1", "domain": "127.0.0.1"},
            origin_ctx,
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        assert result["stored"] is True
        jar = await origin_ctx["browser"]._context.cookies()
        assert any(c["name"] == "c1" and c["value"] == "v1" for c in jar)

    async def test_a_silently_dropped_cookie_is_indeterminate(self, origin_ctx):
        """The defect, reproduced. `add_cookies` neither raises nor stores.

        An `expires` in the past is accepted by the API and lands nowhere. This
        used to report `status: success` with `count: 1`.
        """
        result = await run_module(
            "browser.cookies",
            {"action": "set", "name": "gone", "value": "v",
             "domain": "127.0.0.1", "expires": 1000000},
            origin_ctx,
        )
        assert rung_of(result) == Outcome.INDETERMINATE.value
        assert result["stored"] is False and result["count"] == 0
        jar = await origin_ctx["browser"]._context.cookies()
        assert not [c for c in jar if c["name"] == "gone"]

    async def test_delete_checks_that_the_survivors_came_back(self, origin_ctx):
        """This action empties the jar and re-adds the rest. Both halves matter."""
        for name in ("keep", "drop"):
            await run_module(
                "browser.cookies",
                {"action": "set", "name": name, "value": "v", "domain": "127.0.0.1"},
                origin_ctx,
            )
        result = await run_module(
            "browser.cookies", {"action": "delete", "name": "drop"}, origin_ctx
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        assert result["remaining_count"] == result["expected_remaining_count"]
        jar = await origin_ctx["browser"]._context.cookies()
        assert sorted(c["name"] for c in jar) == ["keep"]

    async def test_clear_reports_what_the_jar_still_holds(self, origin_ctx):
        await run_module(
            "browser.cookies",
            {"action": "set", "name": "c1", "value": "v1", "domain": "127.0.0.1"},
            origin_ctx,
        )
        result = await run_module("browser.cookies", {"action": "clear"}, origin_ctx)
        assert rung_of(result) == Outcome.OBSERVED.value
        assert result["remaining_count"] == 0

    async def test_get_is_observed(self, origin_ctx):
        result = await run_module("browser.cookies", {"action": "get"}, origin_ctx)
        assert rung_of(result) == Outcome.OBSERVED.value


# ===========================================================================
# The rung that was written and taken back out
# ===========================================================================

@pytest.mark.browser
class TestHoverHasNoObservableSignal:
    """`browser.hover` stays undeclared, and this is the measurement that decided it.

    ``el.matches(':hover')`` would have been a genuine observation of the
    browser's own hit-testing. It reads false for every hover in the Chromium
    this repository drives, including hovers that worked -- so a rung resting on
    it would have produced INDETERMINATE on every correct hover in the product.

    If this test ever starts failing, that is the good news: the signal has
    become usable and `browser.hover` can be given the rung it was denied.
    """

    async def test_the_css_hover_state_never_arrives(self, loaded_ctx):
        page = loaded_ctx["browser"].real_page
        await page.hover("#text-field")
        assert await page.evaluate(
            "() => document.querySelectorAll(':hover').length"
        ) == 0

    async def test_and_so_hover_reports_no_envelope_of_its_own(self, loaded_ctx):
        result = await run_module("browser.hover", {"selector": "#text-field"}, loaded_ctx)
        assert result["status"] == "success"
        assert envelope_of(result) is None


# ===========================================================================
# What none of these modules may claim
# ===========================================================================

class TestNobodyReachedForVerified:
    """VERIFIED means a postcondition was evaluated and held.

    The ceiling is enforced by `_apply_outcome_contract`, so a module claiming
    VERIFIED without declaring one would be silently lowered rather than
    caught. This asserts the intent directly for the twelve that declare
    nothing: no postcondition on the decorator, and the word nowhere in the
    source.

    `browser.type` is the exception, and it is named here rather than deleted
    from the list, because the list is the argument. It reads the field back
    through `page.input_value` -- a different channel from the keyboard it
    wrote with -- and compares against `baseline + text` exactly. That is a
    predicate that was evaluated and held, which is what the rung means.
    The other twelve still have nothing of the kind, and this guard is what
    stops one of them acquiring the word without acquiring the read-back.
    """

    #: The twelve with no read-back to declare anything about.
    DECLARED = [
        "browser.goto", "browser.select", "browser.upload",
        "browser.scroll", "browser.download", "browser.screenshot",
        "browser.pdf", "browser.viewport", "browser.evaluate", "browser.close",
        "browser.storage", "browser.cookies",
    ]

    @pytest.mark.parametrize("module_id", DECLARED)
    def test_no_postcondition_is_declared(self, module_id):
        metadata = ModuleRegistry.get_metadata(module_id)
        assert metadata.get("postcondition") is None
        assert ceiling_for(metadata.get("postcondition")) is Outcome.OBSERVED

    @pytest.mark.parametrize("module_id", DECLARED)
    def test_the_outcome_key_is_in_the_output_schema(self, module_id):
        """A consumer reading the catalogue has to be able to find the field."""
        schema = ModuleRegistry.get_metadata(module_id)["output_schema"]
        assert schema["outcome"]["type"] == "object"
        assert schema["outcome"]["description"]

    @pytest.mark.parametrize(
        "module",
        [goto_module, select_module, upload_module, scroll_module,
         download_module, screenshot_module, pdf_module, viewport_module,
         evaluate_module, close_module, storage_module, cookies_module],
    )
    def test_no_module_source_mentions_the_verified_rung(self, module):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "Outcome.VERIFIED" not in source

    def test_the_one_that_does_declare_names_its_read_back(self):
        """The other side of the list above, so removing the guard is deliberate.

        `browser.type` may claim VERIFIED, and what entitles it to is a
        postcondition naming the reading that earns it. If the declaration ever
        goes away while `Outcome.VERIFIED` stays in the source, the engine
        silently lowers the claim and nothing else notices; this notices.
        """
        metadata = ModuleRegistry.get_metadata("browser.type")
        declared = metadata.get("postcondition")

        assert declared, "browser.type claims VERIFIED and must say what it verified"
        assert "input_value" in declared, (
            "the postcondition has to name the reading that earns it"
        )
        assert ceiling_for(declared) is Outcome.VERIFIED
        assert "Outcome.VERIFIED" in Path(type_module.__file__).read_text(encoding="utf-8")
