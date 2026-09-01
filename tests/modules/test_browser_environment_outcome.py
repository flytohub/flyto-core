# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the browser-environment modules are entitled to claim, and what earns it.

The `browser-environment` slice: the modules that configure the browser
(`emulate`, `geolocation`, `throttle`, `proxy_rotate`), the ones that record it
(`record`, `trace`, `cookies_file`), and the ones that watch it (`console`,
`network`, `performance`, `response`).

Two layers, and the second is the one that matters:

* the ``TestRung*`` classes drive each decision function directly and pin every
  branch, including ones a real browser will not produce on demand.
* the ``@pytest.mark.browser`` classes run the modules against a real Chromium
  and a real HTTP server, and check every claim against an INDEPENDENT
  measurement the test takes itself. A number that quietly goes back to being an
  echo of the input fails there, which is the only place it can be caught.

Three of these tests exist because of something that was measured rather than
argued, and each is pinned as an executable fact:

* :class:`TestEmulationSurvivesTheCdpSession` -- ``browser.emulate``'s
  persistent-context path detached its CDP session in a ``finally``, and
  DETACHING REVERTS EVERY ``Emulation.*`` OVERRIDE THE SESSION INSTALLED. On
  this machine the default ``BrowserDriver.launch()`` takes exactly that path,
  so device emulation applied nothing but the viewport and every request went
  out with the real Chromium fingerprint. The test asserts the user agent from
  a fresh evaluate the module had no hand in.
* :class:`TestCookiesFileImportIsReadBackFromTheJar` -- ``add_cookies()``
  returns normally for a cookie with an expiry in the past and the jar does not
  hold it. A cookies file on disk is exactly where stale expiries come from, so
  the module used to report the file's own length as the number restored.
* :class:`TestInnerWidthCannotDecideAnEmulation` -- the withdrawal. The obvious
  predicate for `browser.emulate` is ``window.innerWidth == requested width``,
  and under ``is_mobile`` Chromium reports the LAYOUT viewport instead: 980 for
  a device emulated at 390. Shipping it would have marked every correct phone
  emulation INDETERMINATE. The measurement is pinned here instead, the way
  `browser.hover`'s ``:hover`` reading is.
"""

import asyncio
import http.server
import json
import socketserver
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import core.modules.atomic.browser.console as console_module
import core.modules.atomic.browser.cookies_file as cookies_file_module
import core.modules.atomic.browser.emulate as emulate_module
import core.modules.atomic.browser.geolocation as geolocation_module
import core.modules.atomic.browser.network as network_module
import core.modules.atomic.browser.performance as performance_module
import core.modules.atomic.browser.proxy_rotate as proxy_rotate_module
import core.modules.atomic.browser.record as record_module
import core.modules.atomic.browser.response as response_module
import core.modules.atomic.browser.throttle as throttle_module
import core.modules.atomic.browser.trace as trace_module
from core.engine.outcome import ClaimBy, Outcome, read_envelope
from core.modules import atomic  # noqa: F401 - registers every module
from core.modules.registry import ModuleRegistry


# ---------------------------------------------------------------------------
# Reading a result the way step_executor reads it
# ---------------------------------------------------------------------------

def envelope_of(result):
    """The envelope, read through `read_envelope` rather than ``result['outcome']``.

    These modules return a flat dict with no ``data`` key, so
    ``wrap_legacy_result`` sweeps their fields into ``data`` and the envelope
    survives at the top level. Going through `read_envelope` means a malformed
    rung comes back as None here, the same way it would reach a consumer.
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
    b"<html><body><h1>hello</h1>"
    b"<script>window.__ping = () => fetch('/api/data');</script>"
    b"</body></html>"
)

API_BODY = b'{"rows": [1, 2, 3]}'


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the test output readable
        pass

    def do_GET(self):
        if self.path.startswith("/api/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            # /api/null serves the literal JSON `null`, which parses to None.
            self.wfile.write(b"null" if self.path == "/api/null" else API_BODY)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(PAGE_HTML)


@pytest.fixture
def http_site(monkeypatch):
    """A real origin, with the SSRF guard opened for loopback.

    A real server rather than ``set_content``: `browser.geolocation` cannot be
    read back at all on a non-secure origin (about:blank included), and
    `browser.response` needs an exchange that really happened. Loopback is what
    the guard exists to refuse, so the opt-out is scoped to this fixture.
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


@pytest.fixture
async def browser_ctx():
    """A launched driver in an execution context, torn down after the test."""
    from core.browser.driver import BrowserDriver

    driver = BrowserDriver(headless=True)
    await driver.launch(stealth=False)
    try:
        yield {"browser": driver}
    finally:
        try:
            await driver.close()
        except Exception:  # noqa: BLE001 - teardown must not mask a failure
            pass


@pytest.fixture
async def loaded_ctx(browser_ctx, http_site):
    """`browser_ctx`, sitting on the fixture page at a real origin."""
    await browser_ctx["browser"].goto(http_site + "/")
    return browser_ctx


@pytest.fixture
def sandbox(sandboxed_tmp_path):
    """A directory the path-restricted browser modules are allowed to write to."""
    return sandboxed_tmp_path


# ===========================================================================
# browser.emulate -- the settings dict is the request, the page is the answer
# ===========================================================================

IPHONE = {
    "viewport": {"width": 390, "height": 844},
    "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0) FAKE",
    "device_scale_factor": 3,
    "is_mobile": True,
    "has_touch": True,
}


def _page_says(**overrides):
    reading = {
        "user_agent": IPHONE["user_agent"],
        "device_scale_factor": 3,
        "max_touch_points": 1,
        "inner_width": 980,
        "inner_height": 2121,
    }
    reading.update(overrides)
    return reading


class TestRungEmulate:
    def test_a_page_reporting_all_three_is_observed(self):
        found = emulate_module._emulate_outcome(
            settings=IPHONE, reading=_page_says(), read_error=None,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value
        assert effect_named(found, "emulation_reported_by_page")["agreement"] == {
            "user_agent": True, "device_scale_factor": True, "has_touch": True,
        }

    @pytest.mark.parametrize(
        "override,expected",
        [
            ({"user_agent": "HeadlessChrome/151"}, ["user_agent"]),
            ({"device_scale_factor": 1}, ["device_scale_factor"]),
            ({"max_touch_points": 0}, ["has_touch"]),
        ],
    )
    def test_any_single_disagreement_is_indeterminate(self, override, expected):
        """Two of three matching is not evidence: they routinely match for free."""
        found = emulate_module._emulate_outcome(
            settings=IPHONE, reading=_page_says(**override), read_error=None,
        )
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert effect_named(found, "emulation_not_reflected")["disagreed"] == expected

    def test_the_detached_cdp_session_shape_is_indeterminate(self):
        """The measured failure: the viewport applied, nothing else did."""
        found = emulate_module._emulate_outcome(
            settings=IPHONE,
            reading=_page_says(
                user_agent="Mozilla/5.0 (Macintosh) HeadlessChrome/151",
                device_scale_factor=1,
                max_touch_points=0,
                inner_width=390,
                inner_height=844,
            ),
            read_error=None,
        )
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert effect_named(found, "emulation_not_reflected")["disagreed"] == [
            "device_scale_factor", "has_touch", "user_agent",
        ]

    def test_without_the_read_back_it_is_only_accepted(self):
        found = emulate_module._emulate_outcome(
            settings=IPHONE, reading=None, read_error="Error: page closed",
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "emulation_not_observed")["measured_by"] is None

    def test_the_requested_settings_are_marked_as_not_a_measurement(self):
        found = emulate_module._emulate_outcome(
            settings=IPHONE, reading=_page_says(), read_error=None,
        )
        assert effect_named(found, "emulation_requested")["measured_by"] is None

    def test_a_fractional_scale_factor_survives_the_float_round_trip(self):
        """The preset table carries 2.625 and 2.75."""
        settings = dict(IPHONE, device_scale_factor=2.625)
        found = emulate_module._emulate_outcome(
            settings=settings,
            reading=_page_says(device_scale_factor=2.6250000001),
            read_error=None,
        )
        assert found["rung"] == Outcome.OBSERVED.value

    def test_a_missing_scale_factor_is_a_disagreement_not_a_crash(self):
        found = emulate_module._emulate_outcome(
            settings=IPHONE, reading=_page_says(device_scale_factor=None), read_error=None,
        )
        assert found["rung"] == Outcome.INDETERMINATE.value


class TestInnerWidthCannotDecideAnEmulation:
    """The withdrawal, pinned so the next person finds the measurement.

    ``window.innerWidth == requested width`` is the obvious predicate for a
    device emulation and it is wrong. Under ``is_mobile`` Chromium answers with
    the LAYOUT viewport, which for a page carrying no ``<meta name=viewport>``
    is the 980px fallback. A rung resting on it would read INDETERMINATE for
    every correct phone emulation -- `browser.hover`'s ``:hover`` failure with a
    different API.
    """

    def test_a_correct_phone_emulation_reports_980_and_is_still_observed(self):
        found = emulate_module._emulate_outcome(
            settings=IPHONE,
            reading=_page_says(inner_width=980, inner_height=2121),
            read_error=None,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        layout = effect_named(found, "layout_viewport_reported")
        assert layout["inner_width"] == 980
        assert layout["requested_width"] == 390
        assert "inner_width" not in effect_named(found, "emulation_reported_by_page")["agreement"]

    @pytest.mark.browser
    async def test_chromium_really_does_report_the_layout_viewport(self, loaded_ctx):
        """Measured, not asserted from memory. Delete this only with a rerun."""
        result = await run_module("browser.emulate", {"device": "iphone_14"}, loaded_ctx)
        page = loaded_ctx["browser"].real_page
        inner_width = await page.evaluate("() => window.innerWidth")
        assert inner_width != 390, (
            "innerWidth now matches the emulated device width; re-check whether "
            "it may join the predicate"
        )
        assert rung_of(result) == Outcome.OBSERVED.value


@pytest.mark.browser
class TestEmulationSurvivesTheCdpSession:
    """`cdp.detach()` used to revert every override it had just installed.

    On this machine ``BrowserDriver.launch()`` reaches a persistent context, so
    ``browser.emulate`` takes ``_emulate_via_cdp`` -- the path that was broken --
    and every assertion below fails against the version with the ``finally``.
    """

    async def test_the_page_reports_the_emulated_user_agent(self, loaded_ctx):
        result = await run_module("browser.emulate", {"device": "iphone_14"}, loaded_ctx)
        assert rung_of(result) == Outcome.OBSERVED.value

        # Independent of anything the module reported.
        page = loaded_ctx["browser"].real_page
        assert "iPhone" in await page.evaluate("() => navigator.userAgent")
        assert await page.evaluate("() => window.devicePixelRatio") == 3
        assert await page.evaluate("() => navigator.maxTouchPoints") > 0

    async def test_a_second_emulation_replaces_the_first(self, loaded_ctx):
        """The previous session is detached before the next one is installed."""
        await run_module("browser.emulate", {"device": "iphone_14"}, loaded_ctx)
        result = await run_module("browser.emulate", {"device": "desktop_edge"}, loaded_ctx)
        assert rung_of(result) == Outcome.OBSERVED.value

        page = loaded_ctx["browser"].real_page
        user_agent = await page.evaluate("() => navigator.userAgent")
        assert "Edg/" in user_agent and "iPhone" not in user_agent

    async def test_a_custom_user_agent_reaches_the_page(self, loaded_ctx):
        result = await run_module(
            "browser.emulate",
            {"device": "custom", "width": 800, "height": 600,
             "user_agent": "FlytoProbe/1.0", "device_scale_factor": 2},
            loaded_ctx,
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        page = loaded_ctx["browser"].real_page
        assert await page.evaluate("() => navigator.userAgent") == "FlytoProbe/1.0"


# ===========================================================================
# browser.geolocation -- the parameters are not where the page thinks it is
# ===========================================================================

SF = {"latitude": 37.7749, "longitude": -122.4194, "accuracy": 100}


class TestRungGeolocation:
    def test_the_page_reporting_the_mock_is_observed(self):
        found = geolocation_module._geolocation_outcome(
            requested=SF, reported=dict(SF), read_error=None,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value

    def test_a_different_position_is_indeterminate(self):
        found = geolocation_module._geolocation_outcome(
            requested=SF,
            reported={"latitude": 51.5074, "longitude": -0.1278, "accuracy": 10},
            read_error=None,
        )
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "geolocation_differs" in effect_kinds(found)

    def test_an_insecure_origin_is_accepted_not_indeterminate(self):
        """Setting the mock before navigating is the ordinary usage and works."""
        found = geolocation_module._geolocation_outcome(
            requested=SF, reported=None,
            read_error="code 1: Only secure origins are allowed",
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert "secure origins" in effect_named(found, "geolocation_not_observed")["reason"]

    def test_the_requested_coordinates_are_marked_as_not_a_measurement(self):
        found = geolocation_module._geolocation_outcome(
            requested=SF, reported=dict(SF), read_error=None,
        )
        assert effect_named(found, "geolocation_requested")["measured_by"] is None

    def test_a_hair_of_float_drift_still_matches(self):
        found = geolocation_module._geolocation_outcome(
            requested=SF,
            reported={"latitude": 37.77490000001, "longitude": -122.4194, "accuracy": 100},
            read_error=None,
        )
        assert found["rung"] == Outcome.OBSERVED.value


@pytest.mark.browser
class TestGeolocationAgainstARealPage:
    async def test_the_page_is_served_the_mocked_position(self, loaded_ctx):
        result = await run_module("browser.geolocation", SF, loaded_ctx)
        assert rung_of(result) == Outcome.OBSERVED.value

        # Independent read, through the page's own API.
        page = loaded_ctx["browser"].real_page
        got = await page.evaluate(geolocation_module._READ_POSITION)
        assert got["latitude"] == pytest.approx(37.7749)
        assert got["longitude"] == pytest.approx(-122.4194)

    async def test_a_page_that_was_never_navigated_is_only_accepted(self, browser_ctx):
        """about:blank is not a secure origin, so nothing can be read back."""
        result = await run_module("browser.geolocation", SF, browser_ctx)
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert result["reported_location"] is None


# ===========================================================================
# browser.throttle -- three parameters coming back, and one clock reading
# ===========================================================================

class TestRungThrottle:
    def test_elapsed_time_is_observed(self):
        found = throttle_module._throttle_outcome(
            domain="example.test", waited_ms=1800, interval_ms=2000,
            strategy="fixed", reused_limiter=True,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "wait_elapsed")["waited_ms"] == 1800

    def test_no_wait_is_only_accepted(self):
        found = throttle_module._throttle_outcome(
            domain="example.test", waited_ms=0, interval_ms=2000,
            strategy="fixed", reused_limiter=False,
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "no_wait_elapsed")["reused_limiter"] is False

    def test_the_configured_interval_is_marked_as_not_a_measurement(self):
        """Under the default strategy `interval_ms` IS `min_interval_ms`."""
        found = throttle_module._throttle_outcome(
            domain="example.test", waited_ms=1800, interval_ms=2000,
            strategy="fixed", reused_limiter=True,
        )
        assert effect_named(found, "interval_requested")["measured_by"] is None


class _StubBrowser:
    """Enough of a driver for `browser.throttle`, which only checks it is there."""


@pytest.mark.asyncio
class TestThrottleWaitsForReal:
    async def test_the_first_call_waits_nothing_and_the_second_waits(self):
        """The clock, checked against a clock the test reads itself."""
        context = {"browser": _StubBrowser()}
        params = {"url": "https://example.test/a", "min_interval_ms": 300}

        first = await run_module("browser.throttle", params, context)
        assert first["waited_ms"] == 0
        assert rung_of(first) == Outcome.ACCEPTED.value
        assert first["reused_limiter"] is False

        started = time.monotonic()
        second = await run_module("browser.throttle", params, context)
        independent_ms = (time.monotonic() - started) * 1000

        assert rung_of(second) == Outcome.OBSERVED.value
        assert second["reused_limiter"] is True
        assert second["waited_ms"] > 0
        # The module's own number, checked against the test's stopwatch.
        assert independent_ms >= second["waited_ms"] * 0.8

    async def test_a_context_that_does_not_survive_never_waits(self):
        """The failure the zero rung exists to surface, reproduced."""
        params = {"url": "https://example.test/a", "min_interval_ms": 300}
        for _ in range(3):
            fresh_context = {"browser": _StubBrowser()}
            result = await run_module("browser.throttle", params, fresh_context)
            assert result["waited_ms"] == 0
            assert rung_of(result) == Outcome.ACCEPTED.value


# ===========================================================================
# browser.console / browser.network / browser.response -- the empty capture
# ===========================================================================

class TestRungConsole:
    def test_messages_that_arrived_are_observed(self):
        found = console_module._console_outcome(count=3, level="all", listened_ms=5000)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "console_messages_captured")["count"] == 3

    def test_a_quiet_window_is_only_accepted(self):
        found = console_module._console_outcome(count=0, level="error", listened_ms=5000)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "no_console_messages")["measured_by"] is None


class TestRungNetwork:
    @pytest.mark.parametrize(
        "action,kind",
        [("monitor", "requests_captured"),
         ("block", "routes_aborted"),
         ("intercept", "routes_fulfilled")],
    )
    def test_each_action_names_what_its_count_counts(self, action, kind):
        found = network_module._network_outcome(
            action=action, count=2, listened_ms=1000,
            url_pattern=".*api.*", resource_type=None,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, kind)["count"] == 2

    @pytest.mark.parametrize("action", ["monitor", "block", "intercept"])
    def test_a_zero_is_only_accepted_whichever_action_produced_it(self, action):
        found = network_module._network_outcome(
            action=action, count=0, listened_ms=1000,
            url_pattern=".*api.*", resource_type=None,
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert found["effects"][0]["measured_by"] is None


class TestRungResponse:
    def test_captured_responses_are_observed(self):
        found = response_module._response_outcome(
            count=2, unreadable_bodies=0, url_pattern="/api/", listened_ms=5000,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert "response_bodies_unreadable" not in effect_kinds(found)

    def test_unreadable_bodies_are_counted_beside_the_captures(self):
        found = response_module._response_outcome(
            count=3, unreadable_bodies=1, url_pattern="/api/", listened_ms=5000,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "response_bodies_unreadable")["count"] == 1

    def test_an_empty_capture_is_only_accepted(self):
        found = response_module._response_outcome(
            count=0, unreadable_bodies=0, url_pattern="/api/", listened_ms=5000,
        )
        assert found["rung"] == Outcome.ACCEPTED.value


@pytest.mark.browser
class TestCapturingAgainstARealServer:
    async def test_a_page_that_logs_nothing_is_only_accepted(self, loaded_ctx):
        result = await run_module("browser.console", {"timeout": 300}, loaded_ctx)
        assert result["count"] == 0
        assert rung_of(result) == Outcome.ACCEPTED.value

    async def test_a_console_message_is_observed(self, loaded_ctx):
        page = loaded_ctx["browser"].real_page
        await page.evaluate("() => setTimeout(() => console.log('flyto-probe'), 100)")
        result = await run_module("browser.console", {"timeout": 800}, loaded_ctx)
        assert rung_of(result) == Outcome.OBSERVED.value
        assert any(m["text"] == "flyto-probe" for m in result["messages"])

    async def test_a_captured_request_is_observed(self, loaded_ctx):
        page = loaded_ctx["browser"].real_page
        await page.evaluate("() => setTimeout(() => window.__ping(), 100)")
        result = await run_module(
            "browser.network",
            {"action": "monitor", "url_pattern": ".*api.*", "timeout": 900},
            loaded_ctx,
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        assert any("/api/data" in r["url"] for r in result["requests"])

    async def test_a_window_that_matches_nothing_is_only_accepted(self, loaded_ctx):
        result = await run_module(
            "browser.network",
            {"action": "monitor", "url_pattern": ".*never-requested.*", "timeout": 300},
            loaded_ctx,
        )
        assert rung_of(result) == Outcome.ACCEPTED.value

    async def test_an_aborted_route_is_observed_and_the_fetch_really_fails(self, loaded_ctx):
        page = loaded_ctx["browser"].real_page
        task = asyncio.create_task(run_module(
            "browser.network",
            {"action": "block", "url_pattern": ".*api.*", "timeout": 1200},
            loaded_ctx,
        ))
        await asyncio.sleep(0.3)
        # Independent of the module: the page is told the fetch failed.
        failed = await page.evaluate(
            "() => fetch('/api/data').then(() => false).catch(() => true)"
        )
        result = await task

        assert failed is True
        assert result["blocked_count"] >= 1
        assert rung_of(result) == Outcome.OBSERVED.value

    async def test_a_json_null_body_is_not_counted_as_unreadable(self, loaded_ctx):
        """`json.loads(b'null')` is None, and that body was read perfectly well.

        Counting unreadable bodies as ``body is None`` would report this one as
        a failure to read the payload.
        """
        page = loaded_ctx["browser"].real_page
        task = asyncio.create_task(run_module(
            "browser.response",
            {"url_pattern": "/api/null", "wait_ms": 1500, "max_responses": 1},
            loaded_ctx,
        ))
        await asyncio.sleep(0.3)
        await page.evaluate("() => fetch('/api/null').catch(() => {})")
        result = await task

        assert result["count"] == 1
        assert result["responses"][0]["body"] is None
        assert result["unreadable_body_count"] == 0
        assert rung_of(result) == Outcome.OBSERVED.value
        assert "response_bodies_unreadable" not in effect_kinds(envelope_of(result))

    async def test_a_captured_response_carries_a_body_off_the_wire(self, loaded_ctx):
        page = loaded_ctx["browser"].real_page
        task = asyncio.create_task(run_module(
            "browser.response",
            {"url_pattern": "/api/", "wait_ms": 1500, "max_responses": 1},
            loaded_ctx,
        ))
        await asyncio.sleep(0.3)
        await page.evaluate("() => window.__ping()")
        result = await task

        assert rung_of(result) == Outcome.OBSERVED.value
        assert result["count"] == 1
        # The bytes the fixture server sent, not anything the module was handed.
        assert result["responses"][0]["body"] == json.loads(API_BODY)
        assert result["unreadable_body_count"] == 0


# ===========================================================================
# browser.performance -- real numbers, and an error path that looked the same
# ===========================================================================

class TestRungPerformance:
    def test_metrics_from_the_browser_are_observed(self):
        found = performance_module._metrics_outcome(
            metrics={"ttfb": 12.5, "load": 88.0}, requested=["all"],
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "performance_metrics_read")["metrics"] == ["load", "ttfb"]

    def test_an_empty_answer_is_only_accepted(self):
        found = performance_module._metrics_outcome(metrics={}, requested=["lcp"])
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "no_performance_metrics")["measured_by"] is None

    def test_the_caught_exception_is_failed_not_accepted(self):
        """The branch that used to be indistinguishable from an empty answer."""
        found = performance_module._metrics_failed_outcome(
            error="Execution context was destroyed", requested=["all"],
        )
        assert found["rung"] == Outcome.FAILED.value
        assert found["claim_by"] == ClaimBy.CALLER.value

    def test_a_failure_and_an_empty_answer_are_different_rungs(self):
        empty = performance_module._metrics_outcome(metrics={}, requested=["all"])
        failed = performance_module._metrics_failed_outcome(error="boom", requested=["all"])
        assert empty["rung"] != failed["rung"]


@pytest.mark.browser
class TestPerformanceAgainstARealPage:
    async def test_a_loaded_page_reports_timings(self, loaded_ctx):
        result = await run_module(
            "browser.performance", {"timeout_ms": 0, "metrics": ["all"]}, loaded_ctx,
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        assert "ttfb" in result["metrics"]

    async def test_a_filter_the_page_has_no_entry_for_is_only_accepted(self, loaded_ctx):
        """`fid` needs a real user input; a scripted page never produces one."""
        result = await run_module(
            "browser.performance", {"timeout_ms": 0, "metrics": ["fid"]}, loaded_ctx,
        )
        assert result["metrics"] == {}
        assert rung_of(result) == Outcome.ACCEPTED.value


# ===========================================================================
# browser.trace -- start cannot be read back, stop writes a file
# ===========================================================================

class TestRungTrace:
    def test_a_trace_file_on_disk_is_observed(self):
        found = trace_module._trace_stopped_outcome(
            bytes_on_disk=4096, path="/tmp/t.zip", stat_error=None,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "trace_file_written")["bytes_on_disk"] == 4096

    def test_a_missing_trace_file_is_indeterminate(self):
        found = trace_module._trace_stopped_outcome(
            bytes_on_disk=None, path="/tmp/t.zip",
            stat_error="FileNotFoundError: No such file or directory",
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_start_cannot_climb_past_accepted(self):
        """Playwright offers nothing to ask whether tracing is running."""
        found = trace_module._trace_started_outcome(
            categories=["devtools.timeline"], screenshots=True,
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "tracing_start_accepted")["measured_by"] is None

    @pytest.mark.parametrize(
        "code", ["CHROMIUM_ONLY", "TRACING_ACTIVE", "NO_ACTIVE_TRACE", "CDP_UNAVAILABLE"],
    )
    def test_every_refusal_is_failed_and_claimed_by_the_caller(self, code):
        found = trace_module._trace_refused_outcome(
            action="start", error_code=code, reason="nope",
        )
        assert found["rung"] == Outcome.FAILED.value
        assert found["claim_by"] == ClaimBy.CALLER.value
        assert effect_named(found, "tracing_refused")["error_code"] == code


@pytest.mark.browser
class TestTraceAgainstARealBrowser:
    async def test_a_stopped_trace_reports_the_size_on_disk(self, loaded_ctx, sandbox):
        started = await run_module("browser.trace", {"action": "start"}, loaded_ctx)
        assert rung_of(started) == Outcome.ACCEPTED.value

        target = sandbox / "trace.zip"
        stopped = await run_module(
            "browser.trace", {"action": "stop", "path": str(target)}, loaded_ctx,
        )
        assert rung_of(stopped) == Outcome.OBSERVED.value
        # Independent of the module's own arithmetic.
        assert target.stat().st_size == stopped["size_bytes"] > 0

    async def test_stopping_a_trace_that_never_started_is_failed(self, loaded_ctx):
        result = await run_module("browser.trace", {"action": "stop"}, loaded_ctx)
        assert result["error_code"] == "NO_ACTIVE_TRACE"
        assert rung_of(result) == Outcome.FAILED.value

    async def test_starting_twice_is_failed(self, loaded_ctx):
        await run_module("browser.trace", {"action": "start"}, loaded_ctx)
        second = await run_module("browser.trace", {"action": "start"}, loaded_ctx)
        assert second["error_code"] == "TRACING_ACTIVE"
        assert rung_of(second) == Outcome.FAILED.value
        await run_module("browser.trace", {"action": "stop"}, loaded_ctx)


# ===========================================================================
# browser.record -- the injected flag is the only thing the page said
# ===========================================================================

class TestRungRecord:
    def test_the_flag_read_back_is_observed(self):
        found = record_module._start_outcome(flag=True, read_error=None)
        assert found["rung"] == Outcome.OBSERVED.value

    def test_a_flag_that_is_not_set_is_indeterminate(self):
        found = record_module._start_outcome(flag=False, read_error=None)
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_a_page_that_could_not_be_asked_is_accepted(self):
        found = record_module._start_outcome(flag=None, read_error="Error: page closed")
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_recorded_events_are_observed(self):
        found = record_module._stop_or_get_outcome(action="get", event_count=4)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "events_recorded")["count"] == 4

    def test_an_empty_recording_is_only_accepted(self):
        found = record_module._stop_or_get_outcome(action="get", event_count=0)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "no_events_recorded")["measured_by"] is None

    def test_a_written_workflow_file_is_observed_even_with_no_events(self):
        """The file is the effect when a path was asked for; the count rides along."""
        found = record_module._stop_or_get_outcome(
            action="stop", event_count=0, path="/tmp/w.yaml", bytes_on_disk=91,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "workflow_file_written")["bytes_on_disk"] == 91
        assert "no_events_recorded" in effect_kinds(found)

    def test_a_missing_workflow_file_is_indeterminate(self):
        found = record_module._stop_or_get_outcome(
            action="stop", event_count=3, path="/tmp/w.yaml",
            bytes_on_disk=None, stat_error="FileNotFoundError: nope",
        )
        assert found["rung"] == Outcome.INDETERMINATE.value


@pytest.mark.browser
class TestRecordAgainstARealPage:
    async def test_starting_sets_a_flag_the_page_reports(self, loaded_ctx):
        result = await run_module("browser.record", {"action": "start"}, loaded_ctx)
        assert rung_of(result) == Outcome.OBSERVED.value

        # Independent read of the page's own JS world.
        page = loaded_ctx["browser"].page
        assert await page.evaluate("() => window._flytoRecording") is True

    async def test_a_recording_with_no_actions_is_only_accepted(self, loaded_ctx):
        await run_module("browser.record", {"action": "start"}, loaded_ctx)
        result = await run_module("browser.record", {"action": "get"}, loaded_ctx)
        assert result["event_count"] == 0
        assert rung_of(result) == Outcome.ACCEPTED.value

    async def test_stopping_to_a_path_measures_the_file(self, loaded_ctx, sandbox):
        await run_module("browser.record", {"action": "start"}, loaded_ctx)
        target = sandbox / "workflow.yaml"
        result = await run_module(
            "browser.record", {"action": "stop", "output_path": str(target)}, loaded_ctx,
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        assert target.stat().st_size == result["bytes_on_disk"] > 0


# ===========================================================================
# browser.cookies_file -- one count was the jar, the other was the file
# ===========================================================================

class TestRungCookiesFile:
    def test_a_file_that_reads_back_is_observed(self):
        found = cookies_file_module._export_outcome(
            path="/tmp/c.json", jar_count=3, entries_on_disk=3,
            bytes_on_disk=420, read_error=None,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "cookie_file_written")["entries_on_disk"] == 3

    def test_a_truncated_file_is_indeterminate(self):
        """`st_size` alone would call a half-written array a success."""
        found = cookies_file_module._export_outcome(
            path="/tmp/c.json", jar_count=3, entries_on_disk=None,
            bytes_on_disk=88, read_error="JSONDecodeError: Expecting value",
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_a_file_with_the_wrong_count_is_indeterminate(self):
        found = cookies_file_module._export_outcome(
            path="/tmp/c.json", jar_count=3, entries_on_disk=1,
            bytes_on_disk=90, read_error=None,
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_the_jar_read_is_present_but_is_not_the_rung(self):
        found = cookies_file_module._export_outcome(
            path="/tmp/c.json", jar_count=3, entries_on_disk=None,
            bytes_on_disk=None, read_error="FileNotFoundError: nope",
        )
        assert "cookies_read_from_jar" in effect_kinds(found)
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_cookies_that_reached_the_jar_are_observed(self):
        found = cookies_file_module._import_outcome(
            path="/tmp/c.json", offered=2, stored=2, missing=[],
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert "cookies_dropped" not in effect_kinds(found)

    def test_a_partial_import_is_observed_and_names_what_went(self):
        found = cookies_file_module._import_outcome(
            path="/tmp/c.json", offered=2, stored=1, missing=["past"],
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "cookies_dropped")["names"] == ["past"]

    def test_an_import_the_jar_refused_entirely_is_indeterminate(self):
        found = cookies_file_module._import_outcome(
            path="/tmp/c.json", offered=2, stored=0, missing=["a", "b"],
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_a_file_that_offered_nothing_is_only_accepted(self):
        found = cookies_file_module._import_outcome(
            path="/tmp/c.json", offered=0, stored=0, missing=[],
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "no_cookies_offered")["measured_by"] is None

    def test_the_offered_count_is_marked_as_not_a_measurement(self):
        found = cookies_file_module._import_outcome(
            path="/tmp/c.json", offered=2, stored=2, missing=[],
        )
        assert "add_cookies() returns normally" in effect_named(found, "cookies_offered")["detail"]


@pytest.mark.browser
class TestCookiesFileImportIsReadBackFromTheJar:
    """The measured failure: an expiry in the past is dropped without raising.

    Every jar assertion here is scoped to the names the test put there.
    ``BrowserDriver`` reaches a PERSISTENT context backed by a profile directory
    on this machine, so the jar arrives holding whatever that profile collected
    -- an ``NID`` from a previous session is what caught this. Asserting on the
    whole jar would make these tests pass or fail on the contents of a directory
    they did not create.
    """

    @staticmethod
    async def _empty_jar(context):
        await context.clear_cookies()
        return context

    async def test_an_expired_cookie_is_not_counted_as_imported(self, loaded_ctx, sandbox):
        context = await self._empty_jar(loaded_ctx["browser"]._context)
        target = sandbox / "cookies.json"
        target.write_text(json.dumps([
            {"name": "live", "value": "1", "domain": "127.0.0.1", "path": "/"},
            {"name": "past", "value": "2", "domain": "127.0.0.1", "path": "/",
             "expires": 1000000},
        ]))

        result = await run_module(
            "browser.cookies_file",
            {"action": "import", "file_path": str(target)},
            loaded_ctx,
        )

        assert result["offered_count"] == 2
        assert result["cookie_count"] == 1
        assert result["dropped_names"] == ["past"]
        assert rung_of(result) == Outcome.OBSERVED.value

        # Independent of the module: ask the jar directly.
        names = {c["name"] for c in await context.cookies()}
        assert "live" in names
        assert "past" not in names

    async def test_an_export_is_measured_by_re_reading_the_file(self, loaded_ctx, sandbox):
        context = await self._empty_jar(loaded_ctx["browser"]._context)
        await context.add_cookies(
            [{"name": "one", "value": "1", "domain": "127.0.0.1", "path": "/"}]
        )
        target = sandbox / "out.json"
        result = await run_module(
            "browser.cookies_file",
            {"action": "export", "file_path": str(target)},
            loaded_ctx,
        )
        assert rung_of(result) == Outcome.OBSERVED.value
        # Independent parse of the file the module wrote.
        on_disk = json.loads(target.read_text())
        assert len(on_disk) == result["entries_on_disk"] == result["cookie_count"]
        assert "one" in {c["name"] for c in on_disk}

    async def test_a_round_trip_restores_the_session(self, loaded_ctx, sandbox):
        context = await self._empty_jar(loaded_ctx["browser"]._context)
        await context.add_cookies(
            [{"name": "session", "value": "abc", "domain": "127.0.0.1", "path": "/"}]
        )
        target = sandbox / "session.json"
        await run_module(
            "browser.cookies_file",
            {"action": "export", "file_path": str(target)},
            loaded_ctx,
        )
        await context.clear_cookies()
        assert "session" not in {c["name"] for c in await context.cookies()}

        restored = await run_module(
            "browser.cookies_file",
            {"action": "import", "file_path": str(target)},
            loaded_ctx,
        )
        assert rung_of(restored) == Outcome.OBSERVED.value
        assert restored["dropped_names"] == []
        assert "session" in {c["name"] for c in await context.cookies()}


# ===========================================================================
# browser.proxy_rotate -- one action reaches the world, three do not
# ===========================================================================

class TestRungProxyRotate:
    @pytest.mark.parametrize("action", ["init", "status", "mark_dead"])
    def test_the_pool_only_actions_stay_on_the_floor(self, action):
        """`pool.size` is `len()` of the caller's own list. Nothing was contacted."""
        found = proxy_rotate_module._pool_only_outcome(
            action=action, pool_size=4, alive=3,
        )
        assert found["rung"] == Outcome.DISPATCHED.value
        assert effect_named(found, "proxy_pool_state")["measured_by"] is None

    def test_a_status_code_through_the_new_proxy_is_observed(self):
        found = proxy_rotate_module._rotate_outcome(
            proxy_fingerprint="http://proxy.test:8080", pool_size=2, alive=2,
            saved_url="https://example.test/a", landed_url="https://example.test/a",
            status_code=200, nav_error=None,
            cookies_offered=3, cookies_in_new_context=3, cookie_error=None,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "navigation_through_new_proxy")["status_code"] == 200

    def test_a_non_2xx_is_still_an_observation(self):
        found = proxy_rotate_module._rotate_outcome(
            proxy_fingerprint="http://proxy.test:8080", pool_size=2, alive=2,
            saved_url="https://example.test/a", landed_url="https://example.test/a",
            status_code=407, nav_error=None,
            cookies_offered=0, cookies_in_new_context=None, cookie_error=None,
        )
        assert found["rung"] == Outcome.OBSERVED.value

    def test_a_dead_proxy_is_indeterminate_rather_than_a_green_tick(self):
        """This used to be a logger.warning beside status: "success"."""
        found = proxy_rotate_module._rotate_outcome(
            proxy_fingerprint="http://proxy.test:8080", pool_size=2, alive=1,
            saved_url="https://example.test/a", landed_url=None,
            status_code=None, nav_error="RuntimeError: ERR_PROXY_CONNECTION_FAILED",
            cookies_offered=3, cookies_in_new_context=3, cookie_error=None,
        )
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "PROXY_CONNECTION_FAILED" in effect_named(
            found, "navigation_through_new_proxy_unconfirmed"
        )["reason"]

    def test_nowhere_to_navigate_back_to_is_accepted(self):
        found = proxy_rotate_module._rotate_outcome(
            proxy_fingerprint="http://proxy.test:8080", pool_size=2, alive=2,
            saved_url=None, landed_url=None, status_code=None, nav_error=None,
            cookies_offered=0, cookies_in_new_context=None, cookie_error=None,
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert "no_navigation_attempted" in effect_kinds(found)

    def test_a_bool_is_not_a_status_code(self):
        """`isinstance(True, int)` is how a guard like this lets junk through."""
        found = proxy_rotate_module._rotate_outcome(
            proxy_fingerprint="http://proxy.test:8080", pool_size=1, alive=1,
            saved_url="https://example.test/a", landed_url=None,
            status_code=True, nav_error=None,
            cookies_offered=0, cookies_in_new_context=None, cookie_error=None,
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_the_cookie_count_comes_from_the_new_context(self):
        found = proxy_rotate_module._rotate_outcome(
            proxy_fingerprint="http://proxy.test:8080", pool_size=1, alive=1,
            saved_url="https://example.test/a", landed_url="https://example.test/a",
            status_code=200, nav_error=None,
            cookies_offered=5, cookies_in_new_context=2, cookie_error=None,
        )
        cookies = effect_named(found, "cookies_in_new_context")
        assert cookies["offered"] == 5 and cookies["present"] == 2
        assert "NEW context" in cookies["measured_by"]

    def test_no_credential_reaches_the_envelope(self):
        """This envelope is copied into a database column and a websocket frame."""
        found = proxy_rotate_module._rotate_outcome(
            proxy_fingerprint=proxy_rotate_module._fingerprint(
                "http://user:hunter2@proxy.test:8080"
            ),
            pool_size=1, alive=1,
            saved_url="https://example.test/a", landed_url="https://example.test/a",
            status_code=200, nav_error=None,
            cookies_offered=0, cookies_in_new_context=None, cookie_error=None,
        )
        assert "hunter2" not in repr(found)
        assert "proxy.test:8080" in repr(found)

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("http://user:hunter2@proxy.test:8080", "http://proxy.test:8080"),
            ("socks5://proxy.test:1080", "socks5://proxy.test:1080"),
            # No scheme is an ordinary way to write one, and the credential
            # still has to come off.
            ("user:hunter2@proxy.test:8080", "proxy.test:8080"),
            ("proxy.test:8080", "proxy.test:8080"),
            ("", ""),
        ],
    )
    def test_the_fingerprint_never_carries_a_credential(self, raw, expected):
        assert proxy_rotate_module._fingerprint(raw) == expected
        assert "hunter2" not in proxy_rotate_module._fingerprint(raw)


@pytest.mark.asyncio
class TestProxyRotatePoolActions:
    async def test_init_and_status_report_the_floor(self):
        context = {}
        started = await run_module(
            "browser.proxy_rotate",
            {"action": "init", "proxies": ["http://a:1", "http://b:2"]},
            context,
        )
        assert started["pool_size"] == 2
        assert rung_of(started) == Outcome.DISPATCHED.value

        marked = await run_module("browser.proxy_rotate", {"action": "status"}, context)
        assert rung_of(marked) == Outcome.DISPATCHED.value


# ===========================================================================
# Every module in this group is registered and its envelope is well formed
# ===========================================================================

GROUP = [
    "browser.console", "browser.cookies_file", "browser.emulate",
    "browser.geolocation", "browser.network", "browser.performance",
    "browser.proxy_rotate", "browser.record", "browser.response",
    "browser.throttle", "browser.trace",
]


class TestTheGroupIsWiredUp:
    @pytest.mark.parametrize("module_id", GROUP)
    def test_the_module_declares_an_outcome_in_its_output_schema(self, module_id):
        """A consumer reading the catalogue can see the field exists."""
        metadata = ModuleRegistry.get_all_metadata(filter_by_stability=False)[module_id]
        assert "outcome" in (metadata.get("output_schema") or {})

    @pytest.mark.parametrize("module_id", GROUP)
    def test_no_module_in_this_group_claims_verified(self, module_id):
        """VERIFIED needs a declared postcondition. None of these declares one."""
        metadata = ModuleRegistry.get_all_metadata(filter_by_stability=False)[module_id]
        assert not metadata.get("postcondition")
