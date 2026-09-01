# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the browser SESSION modules may claim, and the line that earns it.

The `browser-session` slice: the modules that start a browser, end one, or move
around inside one — launch, connect, ensure, release, pool, tab, pages, frame,
wait, navigation. They shared one defect with the rest of the category and one
of their own.

The shared one is `file.write`'s ``bytes_written``: every field these modules
reported about their own effect came out of their own parameters.
``browser.launch`` returned the ``browser_type`` it was asked for;
``browser.connect`` returned ``connected: True``, a literal; ``browser.pool``
returned ``len(_browser_pool)``, the size of its own dictionary;
``browser.tab``'s new-tab path returned ``self.url or "about:blank"``, the URL
it was handed rather than the one the tab landed on.

The one of their own is subtler and it decides half of this file.
``Browser.is_connected()`` is not one measurement, it is two, and only one of
them is evidence — see :class:`TestIsConnectedIsOnlyEvidenceInOneDirection`.

So the tests come in two layers, and the second is the one that matters:

* the ``TestRung*`` classes drive the decision functions directly and pin every
  branch, including ones a real browser will not produce on demand.
* the ``@pytest.mark.browser`` classes run the modules against a real Chromium
  and check the reported value against an INDEPENDENT measurement taken by the
  test — the version read straight off the driver's own Browser object and out
  of ``navigator.userAgent``, the page count read straight off the context, the
  elapsed time read off the test's own clock. A field that quietly goes back to
  echoing its input fails there and nowhere else.

Two negative results are pinned as executable facts rather than left as prose:

* :class:`TestBringToFrontHasNoObservableSignal` — the `browser.hover` case
  again. ``document.visibilityState`` and ``document.hasFocus()`` read the same
  for every open page whichever one was brought to front, so `browser.tab`'s
  switch stops at ACCEPTED.
* :class:`TestGoForwardWithNoHistoryReportedSuccess` — the defect the
  navigation rung exists to surface, asserted against a real browser.
"""

import http.server
import json
import socket
import socketserver
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import core.modules.atomic.browser._session_outcome as session_outcome
import core.modules.atomic.browser.connect as connect_module
import core.modules.atomic.browser.ensure as ensure_module
import core.modules.atomic.browser.frame as frame_module
import core.modules.atomic.browser.navigation as navigation_module
import core.modules.atomic.browser.pages as pages_module
import core.modules.atomic.browser.pool as pool_module
import core.modules.atomic.browser.tab as tab_module
import core.modules.atomic.browser.wait as wait_module
from core.engine.outcome import ClaimBy, Outcome, envelope, read_envelope
from core.modules import atomic  # noqa: F401 - registers every module
from core.modules.registry import ModuleRegistry
from core.utils import SSRFError


# ---------------------------------------------------------------------------
# Reading a result the way step_executor reads it
# ---------------------------------------------------------------------------

def envelope_of(result):
    """The envelope, read through ``read_envelope`` rather than ``['outcome']``.

    These modules return a flat dict with no ``data`` key, so
    ``wrap_legacy_result`` sweeps their fields into ``data`` and the envelope
    survives at the top level. Going through ``read_envelope`` means a malformed
    rung comes back as None here, the way it would reach a consumer.
    """
    return read_envelope(result)


def rung_of(result):
    return envelope_of(result)["rung"]


def effect_kinds(found):
    return [effect["kind"] for effect in found["effects"]]


def effect_named(found, kind):
    return next(effect for effect in found["effects"] if effect["kind"] == kind)


def claim_envelope(parts):
    """``envelope()`` applied to a ``(rung, claim_by, effect)`` triple.

    The session helpers hand back parts and let the module make the claim, so
    the tests assemble them the same way the modules do.
    """
    rung, claim_by, effect = parts
    return envelope(rung, claim_by=claim_by, effects=[effect])


async def run_module(module_id, params, context):
    """Execute a module the way the engine does, and return its result dict."""
    return await ModuleRegistry.get(module_id)(params, context).execute()


# ---------------------------------------------------------------------------
# Fakes for the branches a real browser will not produce on demand
# ---------------------------------------------------------------------------

class FakeBrowserType:
    def __init__(self, name):
        self.name = name


class FakeBrowser:
    """Enough of a Playwright ``Browser`` for the two values that matter."""

    def __init__(self, version="151.0.7922.34", engine="chromium", connected=True):
        self.version = version
        self.browser_type = FakeBrowserType(engine)
        self._connected = connected

    def is_connected(self):
        return self._connected


class RaisingBrowser:
    browser_type = FakeBrowserType("chromium")

    @property
    def version(self):
        raise RuntimeError("Target page, context or browser has been closed")

    def is_connected(self):
        raise RuntimeError("connection closed")


class FakeContext:
    def __init__(self, browser):
        self.browser = browser


class FakeDriver:
    """A driver holding a Browser directly, or only through its context.

    The second shape is the persistent-context path, where
    ``BrowserDriver._launch_persistent`` sets ``_browser = None`` outright.
    """

    browser_type = "chromium"

    def __init__(self, browser=None, via_context=None):
        self._browser = browser
        self._context = FakeContext(via_context) if via_context is not None else None


# ---------------------------------------------------------------------------
# Real browser, real server
# ---------------------------------------------------------------------------

PAGE_ONE = (
    b'<html><head><title>one</title></head><body>'
    b'<h1 id="heading">one</h1>'
    b'<div id="late" style="display:none">later</div>'
    b'<iframe id="framed" name="inner" src="/two"></iframe>'
    b'</body></html>'
)

PAGE_TWO = b'<html><head><title>two</title></head><body><h1>two</h1></body></html>'


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the test output readable
        pass

    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/two")
            self.end_headers()
            return
        body = PAGE_TWO if self.path.startswith("/two") else PAGE_ONE
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def http_site(monkeypatch):
    """A real origin, with the SSRF guard opened for loopback.

    A real server rather than ``set_content``: `browser.navigation` rests its
    rung on ``Response.status``, and there is no response object for a page that
    was never fetched. Loopback is exactly what the guard exists to refuse, so
    the opt-out is scoped to this fixture and nothing else.
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
def empty_pool():
    """`browser.pool`'s module-global dictionary, emptied before and after.

    It is process-global with no execution scope — the defect `browser.pool`'s
    docstring records — so a test that leaves entries in it leaks into every
    later test in the same process.
    """
    pool_module._browser_pool.clear()
    yield pool_module._browser_pool
    pool_module._browser_pool.clear()


# ===========================================================================
# The asymmetry the whole group rests on
# ===========================================================================

class TestIsConnectedIsOnlyEvidenceInOneDirection:
    """Why nothing here claims a rung from ``is_connected() is True``.

    ``playwright/_impl/_browser.py`` sets ``self._is_connected = True`` in
    ``__init__`` and clears it only in ``_on_close``, which runs when a
    disconnect event arrives from the browser process. So `True` is the value
    the attribute was born with — `browser.storage`'s literal `True` one
    indirection away — and `False` is a real event that travelled to us.

    These tests pin the consequence, not the Playwright internals: a launch is
    never allowed to rest on the affirming direction, and a teardown is allowed
    to rest on the falsifying one.
    """

    def test_a_launch_rung_does_not_come_from_the_connected_flag(self):
        """A browser that says it is connected but cannot name itself.

        The exact shape a killed process leaves behind for a moment: the flag
        still reads True, and nothing can be read out of it.
        """
        found = claim_envelope(session_outcome.started_claim(
            engine=None, version=None, requested_engine="chromium",
            reason="the Browser object reports an empty version string",
        ))
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "browser_process_not_identified")["measured_by"] is None

    def test_a_teardown_rung_does_come_from_the_cleared_flag(self):
        found = claim_envelope(session_outcome.closed_claim(disconnected=True, reason=None))
        assert found["rung"] == Outcome.OBSERVED.value

    def test_reusing_a_connected_session_claims_nothing(self):
        """`browser.ensure`'s reuse path, on the direction that is not evidence."""
        assert ensure_module._reused_session_outcome(
            FakeDriver(browser=FakeBrowser(connected=True))
        ) is None

    def test_reusing_a_disconnected_session_is_indeterminate(self):
        """The direction that is. A dead driver is about to be handed downstream."""
        found = ensure_module._reused_session_outcome(
            FakeDriver(browser=FakeBrowser(connected=False))
        )
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert found["claim_by"] == ClaimBy.INFERRED.value

    def test_a_session_that_cannot_be_asked_claims_nothing(self):
        assert ensure_module._reused_session_outcome(FakeDriver()) is None
        assert ensure_module._reused_session_outcome(FakeDriver(browser=RaisingBrowser())) is None


# ===========================================================================
# _session_outcome — the reading shared by launch, ensure, pool and release
# ===========================================================================

class TestRungSessionStarted:
    def test_a_reported_version_is_observed(self):
        found = claim_envelope(session_outcome.started_claim(
            engine="chromium", version="151.0.7922.34",
            requested_engine="chromium", reason=None,
        ))
        assert found["rung"] == Outcome.OBSERVED.value
        effect = effect_named(found, "browser_process_identified")
        assert effect["version"] == "151.0.7922.34"
        assert "Browser.version" in effect["measured_by"]

    def test_the_requested_engine_rides_beside_the_measured_one(self):
        """They are different facts, and this is the module that can tell them
        apart. ``_chromium_channel_candidates`` falls through to system Chrome
        and Edge when no channel is pinned."""
        found = claim_envelope(session_outcome.started_claim(
            engine="chromium", version="141.0.1.2",
            requested_engine="firefox", reason=None,
        ))
        effect = effect_named(found, "browser_process_identified")
        assert effect["requested_engine"] == "firefox"
        assert effect["engine"] == "chromium"

    def test_no_version_is_only_accepted(self):
        found = claim_envelope(session_outcome.started_claim(
            engine=None, version=None, requested_engine="chromium",
            reason="no Browser object to ask",
        ))
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_the_persistent_context_path_can_still_be_measured(self):
        """``_launch_persistent`` sets ``_browser = None``; the context knows."""
        engine, version, reason = session_outcome.read_engine(
            FakeDriver(via_context=FakeBrowser(version="151.0.0.1"))
        )
        assert (engine, version, reason) == ("chromium", "151.0.0.1", None)

    def test_a_driver_with_nothing_to_ask_says_why(self):
        engine, version, reason = session_outcome.read_engine(FakeDriver())
        assert version is None and "no Browser object" in reason

    def test_a_raising_browser_is_a_reason_and_not_an_exception(self):
        engine, version, reason = session_outcome.read_engine(
            FakeDriver(browser=RaisingBrowser())
        )
        assert version is None
        assert reason.startswith("RuntimeError:")

    def test_an_empty_version_string_is_not_a_version(self):
        engine, version, reason = session_outcome.read_engine(
            FakeDriver(browser=FakeBrowser(version=""))
        )
        assert version is None and "empty version" in reason


class TestRungSessionClosed:
    def test_a_gone_connection_is_observed(self):
        found = claim_envelope(session_outcome.closed_claim(disconnected=True, reason=None))
        assert found["rung"] == Outcome.OBSERVED.value
        assert "is_connected()" in effect_named(found, "browser_disconnected")["measured_by"]

    def test_a_live_connection_after_close_is_indeterminate_not_failed(self):
        """Teardown is asynchronous: "not finished" and "refused" read alike."""
        found = claim_envelope(session_outcome.closed_claim(disconnected=False, reason=None))
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert found["claim_by"] == ClaimBy.INFERRED.value

    def test_nothing_to_ask_is_only_accepted(self):
        found = claim_envelope(session_outcome.closed_claim(
            disconnected=None, reason="persistent context",
        ))
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "browser_state_not_observed")["measured_by"] is None


class TestRungPoolCloseAll:
    def test_an_empty_pool_claims_nothing(self):
        assert pool_module._close_all_outcome([]) is None

    def test_every_browser_gone_is_observed(self):
        found = pool_module._close_all_outcome([
            {"name": "a", "disconnected": True, "reason": None},
            {"name": "b", "disconnected": True, "reason": None},
        ])
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "browser_disconnected")["browsers_asked"] == 2

    def test_one_still_connected_sinks_the_whole_answer(self):
        """Aggregation is by the weakest reading. Four gone and one live is not
        "all closed"."""
        found = pool_module._close_all_outcome(
            [{"name": str(i), "disconnected": True, "reason": None} for i in range(4)]
            + [{"name": "stuck", "disconnected": False, "reason": None}]
        )
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert effect_named(found, "browser_still_connected")["browsers_still_connected"] == 1

    def test_nothing_askable_anywhere_is_accepted(self):
        found = pool_module._close_all_outcome([
            {"name": "a", "disconnected": None, "reason": "persistent"},
        ])
        assert found["rung"] == Outcome.ACCEPTED.value


# ===========================================================================
# browser.tab
# ===========================================================================

class TestRungTabOpened:
    def test_one_more_page_than_before_is_observed(self):
        found = tab_module._tab_opened_outcome(
            pages_before=1, pages_after=2, requested_url=None,
            landed_url="about:blank", status_code=None,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        effect = effect_named(found, "tab_opened")
        assert (effect["pages_before"], effect["pages_after"]) == (1, 2)

    def test_a_count_that_did_not_move_is_indeterminate(self):
        found = tab_module._tab_opened_outcome(
            pages_before=1, pages_after=1, requested_url=None,
            landed_url="about:blank", status_code=None,
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_a_navigation_status_rides_along(self):
        found = tab_module._tab_opened_outcome(
            pages_before=1, pages_after=2, requested_url="https://example.test/a",
            landed_url="https://example.test/b", status_code=200,
        )
        effect = effect_named(found, "navigation_response")
        assert effect["status_code"] == 200
        assert effect["requested_url"] != effect["landed_url"]

    def test_no_response_object_is_named_as_not_measured(self):
        found = tab_module._tab_opened_outcome(
            pages_before=1, pages_after=2, requested_url="about:blank",
            landed_url="about:blank", status_code=None,
        )
        assert found["rung"] == Outcome.OBSERVED.value  # the tab still opened
        assert effect_named(found, "navigation_not_measured")["measured_by"] is None

    def test_a_bool_is_not_a_status_code(self):
        """``isinstance(True, int)`` is True in Python — the classic way a guard
        like this one lets a non-measurement through."""
        found = tab_module._tab_opened_outcome(
            pages_before=1, pages_after=2, requested_url="https://example.test/",
            landed_url="https://example.test/", status_code=True,
        )
        assert "navigation_response" not in effect_kinds(found)

    def test_a_refused_url_is_failed_and_the_caller_owns_the_claim(self):
        """It did not happen, and we know it did not — which is the distinction
        an error path exists to preserve."""
        found = tab_module._tab_blocked_outcome("http://169.254.169.254/", "blocked")
        assert found["rung"] == Outcome.FAILED.value
        assert found["claim_by"] == ClaimBy.CALLER.value


class TestRungTabClosed:
    def test_both_readings_agreeing_is_observed(self):
        found = tab_module._tab_closed_outcome(pages_before=2, pages_after=1, is_closed=True)
        assert found["rung"] == Outcome.OBSERVED.value

    @pytest.mark.parametrize(
        "before,after,is_closed",
        [(2, 1, False), (2, 2, True), (2, 2, False), (2, 1, None)],
    )
    def test_either_reading_disagreeing_is_indeterminate(self, before, after, is_closed):
        found = tab_module._tab_closed_outcome(
            pages_before=before, pages_after=after, is_closed=is_closed
        )
        assert found["rung"] == Outcome.INDETERMINATE.value


class TestRungTabListed:
    def test_tabs_found_are_tabs_observed(self):
        found = tab_module._tab_list_outcome(3)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "tabs_listed")["count"] == 3

    def test_an_empty_listing_is_the_empty_read(self):
        """`database.query`'s zero rows: it reads the same whether the browser
        has no tabs or this is the wrong context."""
        found = tab_module._tab_list_outcome(0)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "no_tabs_listed")["measured_by"] is None


class TestRungTabSwitched:
    def test_a_switch_never_climbs_past_accepted(self):
        found = tab_module._tab_switched_outcome(index=1, tab_count=2, url="https://a.test/")
        assert found["rung"] == Outcome.ACCEPTED.value
        assert "bring_to_front" in effect_named(found, "bring_to_front_acknowledged")["measured_by"]


# ===========================================================================
# browser.pages
# ===========================================================================

class TestRungPages:
    def test_a_round_tripped_listing_is_observed(self):
        found = pages_module._pages_outcome(page_count=2, round_tripped=True)
        assert found["rung"] == Outcome.OBSERVED.value
        assert "title()" in effect_named(found, "pages_read")["measured_by"]

    def test_a_bare_count_is_only_accepted(self):
        """include_details=False speaks to no page at all; the list is
        Playwright's, and a page that crashed is still in it."""
        found = pages_module._pages_outcome(page_count=2, round_tripped=False)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "pages_counted")["count"] == 2

    def test_no_pages_is_the_empty_read(self):
        found = pages_module._pages_outcome(page_count=0, round_tripped=True)
        assert found["rung"] == Outcome.ACCEPTED.value


# ===========================================================================
# browser.frame
# ===========================================================================

class TestRungFrame:
    def test_frames_found_are_frames_observed(self):
        found = frame_module._frames_listed_outcome(3)
        assert found["rung"] == Outcome.OBSERVED.value

    def test_a_page_reporting_no_frames_at_all_is_accepted(self):
        found = frame_module._frames_listed_outcome(0)
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_an_attached_frame_is_observed(self):
        found = frame_module._frame_entered_outcome(
            how="name", frame_url="https://a.test/f", frame_name="inner", detached=False
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "frame_located")["frame_url"] == "https://a.test/f"

    def test_a_detached_frame_is_indeterminate(self):
        found = frame_module._frame_entered_outcome(
            how="selector", frame_url="", frame_name="(unnamed)", detached=True
        )
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert found["claim_by"] == ClaimBy.INFERRED.value

    def test_the_selector_path_names_the_dom_wait_it_did(self):
        found = frame_module._frame_entered_outcome(
            how="selector", frame_url="https://a.test/f", frame_name="x", detached=False
        )
        assert "wait_for_selector" in effect_named(found, "frame_located")["measured_by"]

    def test_an_unreadable_detached_flag_does_not_invent_a_detachment(self):
        """The frame was still located. Not being able to ask is not a finding."""
        found = frame_module._frame_entered_outcome(
            how="url", frame_url="https://a.test/f", frame_name="x", detached=None
        )
        assert found["rung"] == Outcome.OBSERVED.value


# ===========================================================================
# browser.wait
# ===========================================================================

class TestRungWait:
    @pytest.mark.parametrize("state", ["visible", "attached"])
    def test_a_satisfied_wait_for_presence_is_observed(self, state):
        """These two cannot be satisfied by a selector that matches nothing.

        Measured: `#typo-xyz state=visible` raises TimeoutError after 1502ms.
        So the return itself is the observation and no count is needed.
        """
        found = wait_module._element_state_outcome(selector="#x", state=state)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "element_state_observed")["state"] == state

    @pytest.mark.parametrize(
        "state,counts",
        [("hidden", {"count_after": 1}), ("detached", {"count_before": 1})],
    )
    def test_a_state_that_held_of_a_real_element_is_observed(self, state, counts):
        found = wait_module._element_state_outcome(selector="#x", state=state, **counts)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "element_state_observed")["matching_nodes"] == 1

    @pytest.mark.parametrize(
        "state,counts",
        [
            ("hidden", {"count_before": 0, "count_after": 0}),
            ("detached", {"count_before": 0, "count_after": 0}),
        ],
    )
    def test_a_state_no_element_ever_had_is_indeterminate(self, state, counts):
        """The typo case. `#nosuchthing state=hidden` returned in 7.3ms, and
        this used to be OBSERVED -- a wait satisfied faster by a misspelling
        than by the element it was meant to watch."""
        found = wait_module._element_state_outcome(selector="#nope", state=state, **counts)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert found["claim_by"] == ClaimBy.INFERRED.value
        assert effect_named(found, "element_state_observed")["matching_nodes"] == 0

    def test_a_detachment_is_not_inferred_from_a_node_that_appeared_afterwards(self):
        """`detached` accepts the before-count ONLY, and that is load-bearing.

        A selector matching nothing satisfies a `detached` wait immediately. If
        a node matching it then appears, an after-count would read 1 and call
        that a detachment nobody watched. The asymmetry with `hidden` is not
        stylistic: collapsing the two to one rule turns this red.
        """
        found = wait_module._element_state_outcome(
            selector="#x", state="detached", count_before=0, count_after=1
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_a_hidden_state_reached_by_removal_is_observed(self):
        """The other side of that coin, and a bug this file used to encode.

        A wait for something to disappear is satisfied two honest ways: the node
        stays in the DOM and turns invisible, or the page removes it outright.
        The after-count sees only the first. Reading it alone marked the second
        `indeterminate` -- measured against Chromium on five nodes deleted by a
        timer, with the wait satisfied by the deletion. Had the page not removed
        them the count would still read 5 and the wait would have timed out, so
        the before/after pair is evidence and the rung says so.
        """
        found = wait_module._element_state_outcome(
            selector="#x", state="hidden", count_before=5, count_after=0
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "element_state_observed")["matching_nodes"] == 5

    @pytest.mark.parametrize("state", ["hidden", "detached"])
    def test_a_count_that_could_not_be_read_claims_less(self, state):
        found = wait_module._element_state_outcome(
            selector="#x", state=state, count_error="Error: frame detached"
        )
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert effect_named(found, "element_state_observed")["count_error"] == "Error: frame detached"

    def test_a_sleep_that_ran_its_course_observed_the_clock(self):
        found = wait_module._duration_outcome(requested_ms=1000, elapsed_ms=1002.4)
        assert found["rung"] == Outcome.OBSERVED.value
        effect = effect_named(found, "elapsed_time_observed")
        assert effect["requested_ms"] == 1000
        assert "time.monotonic()" in effect["measured_by"]

    def test_a_sleep_that_came_up_short_is_indeterminate(self):
        found = wait_module._duration_outcome(requested_ms=1000, elapsed_ms=3.0)
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_the_duration_rung_says_nothing_about_the_page(self):
        """It is a clock reading. Claiming it saw the browser would be the
        overreach this whole contract exists to stop."""
        found = wait_module._duration_outcome(requested_ms=10, elapsed_ms=11)
        assert "No page was touched" in effect_named(found, "elapsed_time_observed")["detail"]


# ===========================================================================
# browser.navigation
# ===========================================================================

class TestRungNavigation:
    def test_a_response_status_is_observed(self):
        found = navigation_module._navigation_outcome(
            action="back", status_code=200,
            url_before="https://a.test/2", url_after="https://a.test/1",
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "navigation_response")["status_code"] == 200

    @pytest.mark.parametrize("code", [301, 404, 500])
    def test_a_non_2xx_status_is_still_observed(self, code):
        found = navigation_module._navigation_outcome(
            action="reload", status_code=code,
            url_before="https://a.test/", url_after="https://a.test/",
        )
        assert found["rung"] == Outcome.OBSERVED.value

    def test_no_response_but_a_moved_url_is_a_same_document_navigation(self):
        """``go_back`` across a '#fragment' entry returns None and changes the
        URL. Measured, not assumed — see the real-browser class below."""
        found = navigation_module._navigation_outcome(
            action="back", status_code=None,
            url_before="https://a.test/p#frag", url_after="https://a.test/p",
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert "same_document_navigation" in effect_kinds(found)

    def test_neither_reading_moving_is_indeterminate(self):
        found = navigation_module._navigation_outcome(
            action="forward", status_code=None,
            url_before="https://a.test/p", url_after="https://a.test/p",
        )
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert effect_named(found, "navigation_not_observed")["measured_by"] is None

    def test_a_bool_is_not_a_status_code(self):
        found = navigation_module._navigation_outcome(
            action="reload", status_code=True,
            url_before="https://a.test/", url_after="https://a.test/",
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_the_effect_names_the_playwright_call_that_measured_it(self):
        found = navigation_module._navigation_outcome(
            action="forward", status_code=200,
            url_before="https://a.test/1", url_after="https://a.test/2",
        )
        assert "go_forward" in effect_named(found, "navigation_response")["measured_by"]


# ===========================================================================
# browser.connect
# ===========================================================================

class TestRungConnect:
    def test_creating_a_page_on_the_remote_is_observed(self):
        found = connect_module._connect_outcome(
            version="151.0.7922.34", created_context=False, created_page=True,
            contexts_before=1, contexts_after=1, pages_before=0, pages_after=1,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "remote_targets_counted")["pages_after"] == 1

    def test_adopting_what_was_already_there_is_only_accepted(self):
        """Nothing on the far side changed. The remote answered and named
        itself, which is exactly what ACCEPTED means."""
        found = connect_module._connect_outcome(
            version="151.0.7922.34", created_context=False, created_page=False,
            contexts_before=1, contexts_after=1, pages_before=2, pages_after=2,
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert "remote_browser_identified" in effect_kinds(found)

    def test_a_create_that_did_not_move_the_count_is_indeterminate(self):
        found = connect_module._connect_outcome(
            version="151.0.7922.34", created_context=False, created_page=True,
            contexts_before=1, contexts_after=1, pages_before=0, pages_after=0,
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_a_remote_that_never_named_itself_says_so(self):
        found = connect_module._connect_outcome(
            version=None, created_context=False, created_page=False,
            contexts_before=1, contexts_after=1, pages_before=1, pages_after=1,
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "remote_browser_not_identified")["measured_by"] is None

    def test_the_version_alone_never_lifts_it_to_observed(self):
        """A remote naming itself is an acknowledgement, not a change we saw."""
        found = connect_module._connect_outcome(
            version="151.0.7922.34", created_context=False, created_page=False,
            contexts_before=3, contexts_after=3, pages_before=9, pages_after=9,
        )
        assert found["rung"] != Outcome.OBSERVED.value


# ===========================================================================
# Against a real Chromium
# ===========================================================================

@pytest.mark.browser
class TestLaunchAgainstARealBrowser:
    async def test_the_reported_version_is_the_process_and_not_the_parameter(self):
        """The independent measurement: the same version has to come back out of
        the page's own ``navigator.userAgent``. An echoed parameter cannot."""
        context = {}
        result = await run_module("browser.launch", {"headless": True, "stealth": False}, context)
        driver = context["browser"]
        try:
            assert rung_of(result) == Outcome.OBSERVED.value
            version = result["engine_version"]
            assert version, "no version came back out of the process"
            user_agent = await driver.real_page.evaluate("navigator.userAgent")
            assert version in user_agent
            effect = effect_named(envelope_of(result), "browser_process_identified")
            assert effect["version"] == version
        finally:
            await driver.close()

    async def test_the_requested_engine_is_carried_but_is_not_the_evidence(self):
        context = {}
        result = await run_module("browser.launch", {"headless": True, "stealth": False}, context)
        try:
            effect = effect_named(envelope_of(result), "browser_process_identified")
            assert effect["requested_engine"] == "chromium"
            assert effect["version"] != effect["requested_engine"]
        finally:
            await context["browser"].close()


@pytest.mark.browser
class TestEnsureAndReleaseAgainstARealBrowser:
    async def test_launching_is_observed_and_reusing_claims_nothing(self):
        context = {}
        launched = await run_module("browser.ensure", {"headless": True}, context)
        try:
            assert launched["action"] == "launched"
            assert rung_of(launched) == Outcome.OBSERVED.value

            reused = await run_module("browser.ensure", {"headless": True}, context)
            assert reused["action"] == "reused"
            assert envelope_of(reused) is None
        finally:
            await context["browser"].close()

    async def test_a_forced_release_observes_the_connection_go(self, browser_ctx):
        """Checked against Playwright directly, not against the module's word."""
        driver = browser_ctx["browser"]
        held = session_outcome.browser_object(driver)
        assert held.is_connected()

        result = await run_module("browser.release", {"force": True}, browser_ctx)

        assert rung_of(result) == Outcome.OBSERVED.value
        assert not held.is_connected()
        assert browser_ctx.get("browser") is None

    async def test_a_skipped_release_closes_nothing_and_claims_nothing(self, browser_ctx):
        result = await run_module("browser.release", {}, browser_ctx)
        assert result["action"] == "skipped"
        assert envelope_of(result) is None
        assert session_outcome.browser_object(browser_ctx["browser"]).is_connected()


@pytest.mark.browser
class TestTabAgainstARealBrowser:
    async def test_opening_a_tab_is_measured_by_the_contexts_own_count(
        self, browser_ctx, http_site
    ):
        driver = browser_ctx["browser"]
        before = len(driver._context.pages)

        result = await run_module(
            "browser.tab", {"action": "new", "url": http_site + "/"}, browser_ctx
        )

        assert len(driver._context.pages) == before + 1
        assert rung_of(result) == Outcome.OBSERVED.value
        effect = effect_named(envelope_of(result), "tab_opened")
        assert (effect["pages_before"], effect["pages_after"]) == (before, before + 1)
        assert effect_named(envelope_of(result), "navigation_response")["status_code"] == 200

    async def test_the_url_reported_is_where_the_tab_landed(self, browser_ctx, http_site):
        """It used to be ``self.url or "about:blank"`` — the parameter. A 302
        makes the two disagree, which is the only way to tell them apart."""
        result = await run_module(
            "browser.tab", {"action": "new", "url": http_site + "/redirect"}, browser_ctx
        )
        assert result["requested_url"].endswith("/redirect")
        assert result["url"].endswith("/two")
        assert result["url"] == browser_ctx["browser"]._context.pages[-1].url

    async def test_a_refused_url_is_failed_and_leaves_no_tab_behind(
        self, browser_ctx, monkeypatch
    ):
        driver = browser_ctx["browser"]
        before = len(driver._context.pages)

        def refuse(url, *args, **kwargs):
            raise SSRFError("blocked by policy")

        monkeypatch.setattr(tab_module, "validate_url_with_env_config", refuse)
        result = await run_module(
            "browser.tab", {"action": "new", "url": "http://169.254.169.254/"}, browser_ctx
        )

        assert result["error_code"] == "SSRF_BLOCKED"
        assert rung_of(result) == Outcome.FAILED.value
        assert len(driver._context.pages) == before

    async def test_closing_a_tab_is_measured_and_not_asserted(self, browser_ctx, http_site):
        driver = browser_ctx["browser"]
        await run_module("browser.tab", {"action": "new", "url": http_site + "/"}, browser_ctx)
        before = len(driver._context.pages)

        result = await run_module("browser.tab", {"action": "close"}, browser_ctx)

        assert len(driver._context.pages) == before - 1
        assert rung_of(result) == Outcome.OBSERVED.value
        effect = effect_named(envelope_of(result), "tab_closed")
        assert effect["page_reports_closed"] is True

    async def test_listing_tabs_observes_the_ones_it_found(self, browser_ctx, http_site):
        await run_module("browser.tab", {"action": "new", "url": http_site + "/"}, browser_ctx)
        result = await run_module("browser.tab", {"action": "list"}, browser_ctx)

        assert rung_of(result) == Outcome.OBSERVED.value
        assert result["tab_count"] == len(browser_ctx["browser"]._context.pages)
        # The titles came back from the pages themselves, not from the URLs.
        assert {tab["title"] for tab in result["tabs"]} >= {"one"}

    async def test_switching_stops_at_accepted(self, browser_ctx, http_site):
        await run_module("browser.tab", {"action": "new", "url": http_site + "/two"}, browser_ctx)
        result = await run_module("browser.tab", {"action": "switch", "index": 0}, browser_ctx)
        assert rung_of(result) == Outcome.ACCEPTED.value


@pytest.mark.browser
class TestBringToFrontHasNoObservableSignal:
    """Why `browser.tab`'s switch is ACCEPTED, kept as a measurement.

    The candidate predicates for OBSERVED were ``document.visibilityState`` and
    ``document.hasFocus()`` read after ``bring_to_front()``. On the Chromium
    this repo drives, headless, both read identically for every open page
    whichever one was activated — so the predicate is true for a switch that
    worked AND for one that did nothing at all.

    That is the `browser.hover` mistake with the sign flipped: hover's candidate
    read false for every hover, this one reads true for every page. Either way
    it does not discriminate, and shipping it would have decorated a rung with
    something that cannot fail. The test exists so the next person to reach for
    it finds the measurement rather than the argument.
    """

    async def test_neither_visibility_nor_focus_discriminates(self, browser_ctx, http_site):
        driver = browser_ctx["browser"]
        first = driver._context.pages[0]
        await first.goto(http_site + "/")
        second = await driver._context.new_page()
        await second.goto(http_site + "/two")

        async def readings():
            return [
                (
                    await page.evaluate("document.visibilityState"),
                    await page.evaluate("document.hasFocus()"),
                )
                for page in (first, second)
            ]

        await first.bring_to_front()
        after_first = await readings()
        await second.bring_to_front()
        after_second = await readings()

        assert after_first == after_second, (
            "bring_to_front now discriminates; browser.tab's switch could claim "
            "more than ACCEPTED and this test should be replaced by that rung"
        )
        assert after_first[0] == after_first[1]


@pytest.mark.browser
class TestPagesAgainstARealBrowser:
    async def test_details_round_trip_to_every_page_and_are_observed(
        self, browser_ctx, http_site
    ):
        driver = browser_ctx["browser"]
        await driver.real_page.goto(http_site + "/")

        result = await run_module("browser.pages", {"include_details": True}, browser_ctx)

        assert rung_of(result) == Outcome.OBSERVED.value
        assert result["count"] == len(driver._context.pages)
        assert result["pages"][0]["title"] == "one"

    async def test_a_bare_count_stops_at_accepted(self, browser_ctx):
        result = await run_module("browser.pages", {"include_details": False}, browser_ctx)
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert effect_named(envelope_of(result), "pages_counted")["count"] == result["count"]


@pytest.mark.browser
class TestWaitAgainstARealBrowser:
    async def test_an_element_wait_that_returned_observed_the_state(
        self, browser_ctx, http_site
    ):
        await browser_ctx["browser"].real_page.goto(http_site + "/")
        result = await run_module(
            "browser.wait", {"selector": "#heading", "state": "visible"}, browser_ctx
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        assert effect_named(envelope_of(result), "element_state_observed")["state"] == "visible"

    async def test_waiting_for_a_hidden_element_is_the_same_rung(
        self, browser_ctx, http_site
    ):
        """The contract is a state, not a presence: `#late` is display:none."""
        await browser_ctx["browser"].real_page.goto(http_site + "/")
        result = await run_module(
            "browser.wait", {"selector": "#late", "state": "hidden"}, browser_ctx
        )
        assert rung_of(result) == Outcome.OBSERVED.value

    async def test_a_wait_that_times_out_raises_and_carries_no_envelope(
        self, browser_ctx, http_site
    ):
        """The gap this module's docstring records, asserted rather than
        described: a timeout is INDETERMINATE by the contract and reaches a
        consumer as an execution error, because a raise has no return value to
        hang an envelope on."""
        await browser_ctx["browser"].real_page.goto(http_site + "/")
        with pytest.raises(RuntimeError):
            await run_module(
                "browser.wait",
                {"selector": "#nothing-here", "state": "visible", "timeout_ms": 300},
                browser_ctx,
            )

    async def test_the_elapsed_time_is_a_clock_reading_and_not_the_parameter(
        self, browser_ctx
    ):
        started = time.monotonic()
        result = await run_module("browser.wait", {"duration_ms": 250}, browser_ctx)
        outer = (time.monotonic() - started) * 1000

        assert rung_of(result) == Outcome.OBSERVED.value
        effect = effect_named(envelope_of(result), "elapsed_time_observed")
        assert effect["elapsed_ms"] >= 250
        # The test's own clock bounds the module's. An echoed 250 could not.
        assert effect["elapsed_ms"] <= outer


@pytest.mark.browser
class TestNavigationAgainstARealBrowser:
    async def test_going_back_observes_the_status_of_the_document_it_fetched(
        self, browser_ctx, http_site
    ):
        page = browser_ctx["browser"].real_page
        await page.goto(http_site + "/one")
        await page.goto(http_site + "/two")

        result = await run_module("browser.navigation", {"action": "back"}, browser_ctx)

        assert rung_of(result) == Outcome.OBSERVED.value
        assert result["status_code"] == 200
        assert result["previous_url"].endswith("/two")
        assert result["url"].endswith("/one")

    async def test_reloading_observes_its_response(self, browser_ctx, http_site):
        await browser_ctx["browser"].real_page.goto(http_site + "/one")
        result = await run_module("browser.navigation", {"action": "reload"}, browser_ctx)
        assert rung_of(result) == Outcome.OBSERVED.value
        assert result["status_code"] == 200

    async def test_a_fragment_move_is_observed_without_any_response(
        self, browser_ctx, http_site
    ):
        """The branch that would be lost if the rung rested on the status alone."""
        page = browser_ctx["browser"].real_page
        await page.goto(http_site + "/one")
        await page.goto(http_site + "/one#frag")

        result = await run_module("browser.navigation", {"action": "back"}, browser_ctx)

        assert result["status_code"] is None
        assert rung_of(result) == Outcome.OBSERVED.value
        assert "same_document_navigation" in effect_kinds(envelope_of(result))


@pytest.mark.browser
class TestGoForwardWithNoHistoryReportedSuccess:
    """The defect the navigation rung exists to surface.

    ``page.go_forward()`` returns None when there is no entry to move to, and
    ``page.url`` does not move either. This module discarded the return value
    and reported ``{"status": "success", "url": page.url}`` — two fields that
    agreed with each other and with nothing else.
    """

    async def test_a_forward_with_nowhere_to_go_is_indeterminate_not_success(
        self, browser_ctx, http_site
    ):
        page = browser_ctx["browser"].real_page
        await page.goto(http_site + "/one")
        await page.goto(http_site + "/two")
        await page.go_back(wait_until="domcontentloaded")
        await page.go_forward(wait_until="domcontentloaded")  # history now exhausted

        result = await run_module("browser.navigation", {"action": "forward"}, browser_ctx)

        assert result["status"] == "success"  # unchanged, and still not the answer
        assert result["url"] == result["previous_url"]
        assert rung_of(result) == Outcome.INDETERMINATE.value


@pytest.mark.browser
class TestFrameAgainstARealBrowser:
    async def test_listing_frames_observes_the_tree_the_browser_reports(
        self, browser_ctx, http_site
    ):
        await browser_ctx["browser"].real_page.goto(http_site + "/one")
        result = await run_module("browser.frame", {"action": "list"}, browser_ctx)

        assert rung_of(result) == Outcome.OBSERVED.value
        assert result["count"] == len(browser_ctx["browser"].real_page.frames)
        assert "inner" in {f["name"] for f in result["frames"]}

    async def test_entering_by_name_reports_the_url_the_browser_has(
        self, browser_ctx, http_site
    ):
        """``name='inner'`` is the parameter; ``/two`` is what the browser
        actually loaded into it, and that is what comes back."""
        await browser_ctx["browser"].real_page.goto(http_site + "/one")
        result = await run_module(
            "browser.frame", {"action": "enter", "name": "inner"}, browser_ctx
        )

        assert rung_of(result) == Outcome.OBSERVED.value
        assert result["frame_url"].endswith("/two")
        assert effect_named(envelope_of(result), "frame_located")["found_by"] == "name"

    async def test_entering_by_selector_names_the_dom_wait(self, browser_ctx, http_site):
        await browser_ctx["browser"].real_page.goto(http_site + "/one")
        result = await run_module(
            "browser.frame", {"action": "enter", "selector": "#framed"}, browser_ctx
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        assert "wait_for_selector" in effect_named(
            envelope_of(result), "frame_located"
        )["measured_by"]

    async def test_exiting_a_frame_claims_nothing(self, browser_ctx, http_site):
        await browser_ctx["browser"].real_page.goto(http_site + "/one")
        await run_module("browser.frame", {"action": "enter", "name": "inner"}, browser_ctx)
        result = await run_module("browser.frame", {"action": "exit"}, browser_ctx)
        assert envelope_of(result) is None


@pytest.mark.browser
class TestPoolAgainstARealBrowser:
    async def test_create_observes_the_process_it_started(self, empty_pool):
        context = {}
        result = await run_module(
            "browser.pool", {"action": "create", "name": "a", "stealth": False}, context
        )
        try:
            assert rung_of(result) == Outcome.OBSERVED.value
            driver = empty_pool["a"]
            assert result["engine_version"] == session_outcome.browser_object(driver).version
        finally:
            await run_module("browser.pool", {"action": "close_all"}, context)

    async def test_close_observes_the_connection_go(self, empty_pool):
        context = {}
        await run_module(
            "browser.pool", {"action": "create", "name": "a", "stealth": False}, context
        )
        held = session_outcome.browser_object(empty_pool["a"])

        result = await run_module("browser.pool", {"action": "close", "name": "a"}, context)

        assert rung_of(result) == Outcome.OBSERVED.value
        assert not held.is_connected()

    async def test_closing_a_name_that_is_not_in_the_pool_claims_nothing(self, empty_pool):
        result = await run_module("browser.pool", {"action": "close", "name": "ghost"}, {})
        assert result["status"] == "success"
        assert envelope_of(result) is None

    async def test_close_all_asks_every_browser_and_says_how_many(self, empty_pool):
        context = {}
        for name in ("a", "b"):
            await run_module(
                "browser.pool",
                {"action": "create", "name": name, "stealth": False},
                context,
            )
        held = [session_outcome.browser_object(d) for d in empty_pool.values()]

        result = await run_module("browser.pool", {"action": "close_all"}, context)

        assert rung_of(result) == Outcome.OBSERVED.value
        assert effect_named(envelope_of(result), "browser_disconnected")["browsers_asked"] == 2
        assert not any(browser.is_connected() for browser in held)

    async def test_list_and_switch_reach_no_browser_and_claim_nothing(self, empty_pool):
        context = {}
        await run_module(
            "browser.pool", {"action": "create", "name": "a", "stealth": False}, context
        )
        try:
            listed = await run_module("browser.pool", {"action": "list"}, context)
            switched = await run_module(
                "browser.pool", {"action": "switch", "name": "a"}, context
            )
            assert envelope_of(listed) is None
            assert envelope_of(switched) is None
        finally:
            await run_module("browser.pool", {"action": "close_all"}, context)

    async def test_the_pool_count_survives_a_dead_browser(self, empty_pool):
        """Why `count` is not evidence, made concrete: close the browser behind
        the pool's back and the number it reports does not move."""
        context = {}
        await run_module(
            "browser.pool", {"action": "create", "name": "a", "stealth": False}, context
        )
        try:
            await empty_pool["a"].close()
            listed = await run_module("browser.pool", {"action": "list"}, context)
            assert listed["count"] == 1
        finally:
            empty_pool.clear()


@pytest.mark.browser
class TestConnectAgainstARealCdpEndpoint:
    """A real remote: a Chromium started with ``--remote-debugging-port``.

    Not a stand-in for Browserless, but the same protocol on the same code path,
    which is what the rung is about.
    """

    @pytest.fixture
    async def cdp_endpoint(self, monkeypatch):
        from playwright.async_api import async_playwright

        monkeypatch.setenv("FLYTO_ALLOW_PRIVATE_NETWORK", "true")
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True, args=[f"--remote-debugging-port={port}"]
        )
        try:
            info = None
            for _ in range(100):
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/json/version", timeout=1
                    ) as answer:
                        info = json.loads(answer.read())
                    break
                except Exception:  # noqa: BLE001 - the port is not up yet
                    await _sleep(0.1)
            if info is None:
                pytest.skip("the CDP endpoint never came up")
            yield info
        finally:
            await browser.close()
            await playwright.stop()

    async def test_the_version_comes_from_the_remote(self, cdp_endpoint):
        context = {}
        result = await run_module(
            "browser.connect", {"ws_endpoint": cdp_endpoint["webSocketDebuggerUrl"]}, context
        )
        try:
            # /json/version says 'HeadlessChrome/151.0.7922.34'; Browser.version
            # says '151.0.7922.34'. Same process, two channels, one number.
            assert result["remote_version"]
            assert result["remote_version"] in cdp_endpoint["Browser"]
        finally:
            await context["browser"].close()

    async def test_creating_a_page_on_the_remote_is_observed(self, cdp_endpoint):
        context = {}
        result = await run_module(
            "browser.connect", {"ws_endpoint": cdp_endpoint["webSocketDebuggerUrl"]}, context
        )
        try:
            found = envelope_of(result)
            effect = effect_named(found, "remote_targets_counted")
            if effect["created_page"] or effect["created_context"]:
                assert found["rung"] == Outcome.OBSERVED.value
                assert effect["pages_after"] > effect["pages_before"]
            else:  # a provider that hands back a ready page: nothing changed
                assert found["rung"] == Outcome.ACCEPTED.value
        finally:
            await context["browser"].close()


async def _sleep(seconds):
    import asyncio

    await asyncio.sleep(seconds)
