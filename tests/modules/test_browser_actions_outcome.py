# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the page-changing browser modules are entitled to claim.

The `browser-actions` slice: the modules that do not read a page, they alter
one. `browser.form`, `browser.drag`, `browser.dialog`, `browser.interact`,
`browser.login`, `browser.challenge` -- and `browser.press` and `browser.hover`,
which are here as measurements rather than as declarations.

Every module in this group reported the same non-evidence in a different shape.
`browser.form` reported ``success_count``: the number of keys in the caller's
own ``data`` dict for which nothing raised, which is unchanged if every selector
resolved to a ``<div>``. `browser.drag` reported ``from`` and ``to``: arithmetic
on its own inputs, pixel-identical on a page with no drag handler at all.
`browser.login` reported ``logged_in`` computed from a ``success_indicator``
nobody had checked was absent BEFORE the login. `browser.challenge` returned
``status: "human_resolved"`` from two branches that disagreed about whether the
page had actually cleared. `browser.interact` returned ``status`` and its own
parameters on paths where it had dispatched nothing whatsoever.

Two layers, and the second is the one that matters:

* the ``TestRung*`` classes drive each module's decision function directly and
  pin every branch, including the ones a real browser will not produce on
  demand.
* the ``@pytest.mark.browser`` classes run the modules against real Chromium and
  a real HTTP origin, and check the claim against an INDEPENDENT measurement the
  test takes itself. A rung that quietly goes back to resting on an echoed
  parameter fails there, which is the only place it can be caught.

Two negative results are pinned here as executable facts rather than left as
prose, because both are about a rung that was considered and refused:

* :class:`TestPressHasNothingToRead` -- ``document.activeElement`` moves for
  `Tab` and does not move for `Enter` or `Escape`, not even when the `Enter`
  fires a handler that rewrites the document. `Enter` and `Escape` are this
  module's own two examples, so a rung resting on activeElement would be
  INDETERMINATE on every press anybody cares about.
* :class:`TestHoverIsStillUndeclared` -- the ``:hover`` measurement from the
  first pass, re-asserted so that removing it takes a deliberate act.
"""

import asyncio
import http.server
import socketserver
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import core.modules.atomic.browser.challenge as challenge_module
import core.modules.atomic.browser.dialog as dialog_module
import core.modules.atomic.browser.drag as drag_module
import core.modules.atomic.browser.form as form_module
import core.modules.atomic.browser.interact as interact_module
import core.modules.atomic.browser.login as login_module
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
# Real pages, served from a real origin
# ---------------------------------------------------------------------------
#
# A real HTTP server rather than ``set_content``: `browser.login`'s URL reading
# needs an origin that ``history.pushState`` will accept, and on ``about:blank``
# it throws. Everything else could have used set_content and does not, so that
# one fixture serves the whole file.

FORM_HTML = """
<html><body>
<form id="f">
  <input name="email" id="email">
  <input name="password" id="password" type="password">
  <textarea name="bio"></textarea>
  <select name="plan"><option value="free">Free</option><option value="pro">Pro</option></select>
  <input type="checkbox" name="tos">
  <input type="checkbox" name="already" checked>
  <input name="resetme" id="resetme">
  <label><input type="radio" name="color" value="red">red</label>
  <label><input type="radio" name="color" value="blue">blue</label>
  <label><input type="radio" name="quoted" value="plain">plain</label>
  <label><input type="radio" name="quoted" value="say &quot;hi&quot;">quoted</label>
  <button type="submit" id="go">Go</button>
</form>
<div id="submitted"></div>
<script>
  // A field that throws every keystroke away. Not contrived: a controlled
  // component whose state never accepts the value does exactly this, and it is
  // the case a fill count cannot tell from a working one.
  document.getElementById('resetme').addEventListener('input', function () {
    this.value = '';
  });
  document.getElementById('f').addEventListener('submit', function (e) {
    e.preventDefault();
    document.getElementById('submitted').textContent = 'yes';
  });
</script>
</body></html>
"""

_LOGIN_FORM = """
<form id="lf">
  <input id="user" name="username">
  <input id="pass" name="password" type="password">
  <button type="submit" id="go">Sign in</button>
</form>
"""

LOGIN_OK_HTML = """
<html><body>%s<script>
document.getElementById('lf').addEventListener('submit', function (e) {
  e.preventDefault();
  history.pushState({}, '', '/dashboard');
  var d = document.createElement('div');
  d.className = 'dash';
  d.textContent = 'welcome back';
  document.body.appendChild(d);
});
</script></body></html>
""" % _LOGIN_FORM

LOGIN_NOTHING_HTML = """
<html><body>%s<script>
document.getElementById('lf').addEventListener('submit', function (e) { e.preventDefault(); });
</script></body></html>
""" % _LOGIN_FORM

LOGIN_ALREADY_HTML = """
<html><body><div class="dash">welcome back</div>%s<script>
document.getElementById('lf').addEventListener('submit', function (e) { e.preventDefault(); });
</script></body></html>
""" % _LOGIN_FORM

CHALLENGE_CLEARS_HTML = """
<html><head><title>Just a moment...</title></head><body>
<p>one moment</p>
<script>
setTimeout(function () {
  document.title = 'The Real Page';
  document.body.innerHTML = '<p>' + new Array(400).join('x') + '</p>';
}, 1100);
</script>
</body></html>
"""

CHALLENGE_STUCK_HTML = """
<html><head><title>Just a moment...</title></head><body><p>one moment</p></body></html>
"""

PLAIN_HTML = """
<html><head><title>An Ordinary Page</title></head><body><p>nothing to see</p></body></html>
"""

DRAG_LIVE_HTML = """
<html><body style="margin:0">
<div id="src" style="position:absolute;left:10px;top:10px;width:40px;height:40px;background:#c00"></div>
<div id="dst" style="position:absolute;left:200px;top:10px;width:120px;height:120px;background:#eee"></div>
<script>
  // A mousedown-based drag, which is what synthetic mouse events can actually
  // drive. The HTML5 drag-and-drop API cannot be driven this way at all, which
  // is exactly why an unchanged page has to stay INDETERMINATE.
  var dragging = false, ox = 0, oy = 0;
  var src = document.getElementById('src');
  src.addEventListener('mousedown', function (e) {
    dragging = true; ox = e.clientX - src.offsetLeft; oy = e.clientY - src.offsetTop;
  });
  document.addEventListener('mousemove', function (e) {
    if (!dragging) return;
    src.style.left = (e.clientX - ox) + 'px';
    src.style.top = (e.clientY - oy) + 'px';
  });
  document.addEventListener('mouseup', function (e) {
    if (!dragging) return;
    dragging = false;
    var d = document.getElementById('dst');
    var r = d.getBoundingClientRect();
    if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom) {
      d.appendChild(src);
      src.style.left = '0px'; src.style.top = '0px';
    }
  });
</script>
</body></html>
"""

# A dead drop target BELOW THE FOLD on a page tall enough to scroll.
#
# Every part of that sentence is load-bearing, and the short fixture below has
# none of it -- which is why its test passes for the wrong reason. A body that
# cannot scroll cannot expose the defect, and neither can a target already on
# screen: measured against real Chromium, a drag between two elements at the
# same `top` scrolls nothing at all. The scroll comes from Playwright bringing
# the target into view, so the target must start off it.
#
# `bounding_box()` is viewport-relative -- Playwright's own docstring says
# "Scrolling affects the returned bounding box" -- so on this page the box moved
# whether or not the drag did. On a page with no javascript, no drag handler and
# no drop handler, the module read that scroll as movement and reported OBSERVED:
#
#     before  viewport y=100     document y=100  scrollY=0
#     after   viewport y=-3180   document y=100  scrollY=3280
#
# The 40px box "moved" 3280 pixels without the page touching it.
# Three elements a wait can be pointed at: one visible, one genuinely hidden,
# and one that a timer removes from the DOM shortly after `doomLater()` is
# called. The third is what lets a `detached` wait be satisfied by the page
# actually removing a node, rather than by the node never having existed.
WAIT_STATES_HTML = """
<html><body>
<div id="real">here</div>
<div id="gone" style="display:none">hidden but present</div>
<div id="doomed">going away</div>
<div class="crowd">a</div><div class="crowd">b</div><div class="crowd">c</div>
<div class="crowd">d</div><div class="crowd">e</div>
<script>
  function doomLater() {
    setTimeout(function () {
      var el = document.querySelector('#doomed');
      if (el) { el.remove(); }
    }, 500);
  }
  // The other honest way a wait for "hidden" is satisfied: not display:none,
  // but the nodes being taken out of the page entirely.
  function clearCrowdLater() {
    setTimeout(function () {
      document.querySelectorAll('.crowd').forEach(function (n) { n.remove(); });
    }, 500);
  }
</script>
</body></html>
"""

# Three page shapes where a scroll can masquerade as a drag, and one where a
# drag really happens. Between them they defeat every simpler reading: the raw
# viewport rect fails the first two, and the rect plus `window.scroll` fails the
# first and the third. None of the three dead pages contains a single <script>.
#
# An ordinary app shell: the window CANNOT scroll, the content pane does.
# window.scrollY stays 0 throughout while the pane travels ~3900px.
# Drag-to-trash: the drop handler DELETES the source. The least ambiguous
# effect this module can have, and the one it used to miss entirely.
DRAG_TRASH_HTML = """
<html><body style="margin:0">
<div id="src" style="position:absolute;left:10px;top:20px;width:60px;height:40px;background:#c00">X</div>
<div id="trash" style="position:absolute;left:200px;top:20px;width:120px;height:120px;background:#eee"></div>
<script>
 var s = document.querySelector('#src'), t = document.querySelector('#trash'), dragging = false;
 s.addEventListener('mousedown', function () { dragging = true; });
 t.addEventListener('mouseup', function () { if (dragging) { s.remove(); } dragging = false; });
</script>
</body></html>
"""

DRAG_DEAD_SHELL_HTML = """
<!doctype html><html><head><style>
html,body{margin:0;padding:0;height:100%;overflow:hidden}
#pane{position:absolute;left:0;top:0;right:0;bottom:0;overflow:auto}
#src{position:absolute;left:10px;top:120px;width:60px;height:40px;background:#c00}
#dst{position:absolute;left:220px;top:2400px;width:160px;height:160px;background:#eee}
#filler{height:5000px}
</style></head><body>
<div id="pane"><div id="src">CARD</div><div id="dst">DROP</div><div id="filler"></div></div>
</body></html>
"""

# A position:fixed source. Its viewport rect is ALREADY scroll-invariant, so
# adding the window scroll to it invents a displacement out of nothing -- this
# page is here because a fix broke it, not because the original did.
DRAG_DEAD_FIXED_HTML = """
<html><body style="margin:0">
<div id="src" style="position:fixed;left:10px;top:100px;width:40px;height:40px;background:#c00"></div>
<div id="dst" style="position:absolute;left:200px;top:3000px;width:120px;height:120px;background:#eee"></div>
<div style="height:5000px"></div>
</body></html>
"""

# The positive control: a page that really does move the element, and scrolls
# while doing it. Whatever the reading is, it has to still say MOVED here.
DRAG_MOVES_HTML = """
<html><body style="margin:0">
<div id="src" style="position:absolute;left:10px;top:100px;width:40px;height:40px;background:#c00"></div>
<div id="dst" style="position:absolute;left:200px;top:2000px;width:120px;height:120px;background:#eee"></div>
<div style="height:4000px"></div>
<script>
 var s = document.querySelector('#src'), dragging = false;
 s.addEventListener('mousedown', function () { dragging = true; });
 document.addEventListener('mousemove', function (e) {
   if (!dragging) { return; }
   s.style.left = (e.pageX - 20) + 'px';
   s.style.top = (e.pageY - 20) + 'px';
 });
 document.addEventListener('mouseup', function () { dragging = false; });
</script>
</body></html>
"""

DRAG_DEAD_TALL_HTML = """
<html><body style="margin:0">
<div id="src" style="position:absolute;left:10px;top:100px;width:40px;height:40px;background:#c00"></div>
<div id="dst" style="position:absolute;left:200px;top:2000px;width:120px;height:120px;background:#eee"></div>
<div style="height:4000px"></div>
</body></html>
"""

DRAG_DEAD_HTML = """
<html><body style="margin:0">
<div id="src" style="position:absolute;left:10px;top:10px;width:40px;height:40px;background:#c00"></div>
<div id="dst" style="position:absolute;left:200px;top:10px;width:120px;height:120px;background:#eee"></div>
</body></html>
"""

PRESS_HTML = """
<html><body>
<input id="a" value="one">
<input id="b" value="two">
<button id="go">Go</button>
<div id="log"></div>
<script>
document.getElementById('go').addEventListener('click', function () {
  document.getElementById('log').textContent = 'clicked';
});
</script>
</body></html>
"""

DIALOG_HTML = """
<html><body><p>a page that can ask questions</p></body></html>
"""

PAGES = {
    "/form": FORM_HTML,
    "/login-ok": LOGIN_OK_HTML,
    "/login-nothing": LOGIN_NOTHING_HTML,
    "/login-already": LOGIN_ALREADY_HTML,
    "/challenge-clears": CHALLENGE_CLEARS_HTML,
    "/challenge-stuck": CHALLENGE_STUCK_HTML,
    "/plain": PLAIN_HTML,
    "/drag-moves": DRAG_MOVES_HTML,
    "/drag-trash": DRAG_TRASH_HTML,
    "/drag-dead": DRAG_DEAD_HTML,
    "/drag-dead-tall": DRAG_DEAD_TALL_HTML,
    "/drag-dead-shell": DRAG_DEAD_SHELL_HTML,
    "/drag-dead-fixed": DRAG_DEAD_FIXED_HTML,
    "/drag-live": DRAG_LIVE_HTML,
    "/wait-states": WAIT_STATES_HTML,
    "/press": PRESS_HTML,
    "/dialog": DIALOG_HTML,
}


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the test output readable
        pass

    def do_GET(self):
        body = PAGES.get(self.path.split("?")[0], PLAIN_HTML).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def http_site():
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
def at_page(browser_ctx, http_site):
    """``await at_page("/form")`` -> the context, with that page loaded.

    Navigation goes through the raw Playwright page rather than `browser.goto`,
    so that nothing in this file depends on another module's behaviour or on
    the SSRF guard's loopback opt-out.
    """
    async def _load(path):
        await browser_ctx["browser"].real_page.goto(http_site + path)
        return browser_ctx
    return _load


# ===========================================================================
# browser.form -- success_count is the input; the field's own state is the page
# ===========================================================================

def _state(kind="text", **rest):
    """A field-state reading of the shape the in-page reader returns."""
    return dict(kind=kind, **rest)


class TestRungForm:
    """Every branch of `_classify_field` and `_form_outcome`, driven directly."""

    def test_a_field_whose_state_moved_is_changed(self):
        assert form_module._classify_field(
            _state(length=0, matches=False), _state(length=5, matches=True)
        ) == "changed"

    def test_a_same_length_replacement_is_still_changed(self):
        """``abc`` -> ``xyz``. The length is identical; the in-page comparison is not.

        Without ``matches`` in the equality this reads as an unchanged field and
        a correct fill is reported INDETERMINATE.
        """
        assert form_module._classify_field(
            _state(length=3, matches=False), _state(length=3, matches=True)
        ) == "changed"

    def test_a_field_that_already_held_the_target_is_not_a_change(self):
        already = _state("checkbox", checked=True, matches=True)
        assert form_module._classify_field(already, already) == "already_correct"

    def test_a_field_that_did_not_move_and_is_wrong_is_unchanged(self):
        stuck = _state(length=0, matches=False)
        assert form_module._classify_field(stuck, stuck) == "unchanged"

    @pytest.mark.parametrize(
        "before,after",
        [(None, _state(length=1, matches=True)), (_state(length=1, matches=True), None), (None, None)],
    )
    def test_a_missing_reading_on_either_side_is_not_read(self, before, after):
        assert form_module._classify_field(before, after) == "not_read"

    def _outcome(self, results, **rest):
        return form_module._form_outcome(
            measurements=[
                {"name": f"f{i}", "result": r, "kind": "text", "reason": None}
                for i, r in enumerate(results)
            ],
            offered_fields=rest.pop("offered_fields", len(results)),
            filled_count=rest.pop("filled_count", len(results)),
            failed_count=rest.pop("failed_count", 0),
            submit_requested=rest.pop("submit_requested", False),
            submit_dispatched=rest.pop("submit_dispatched", False),
        )

    def test_one_changed_field_is_observed(self):
        found = self._outcome(["changed"])
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value

    def test_one_changed_field_outranks_every_other_answer(self):
        """The rung says how far ANY effect was followed, not how tidy the step was."""
        found = self._outcome(["changed", "unchanged", "already_correct", "not_read"])
        assert found["rung"] == Outcome.OBSERVED.value
        observed = effect_named(found, "field_states_observed")
        assert (observed["changed"], observed["unchanged"]) == (1, 1)
        assert observed["already_correct"] == 1 and observed["not_read"] == 1

    def test_a_readable_field_that_did_not_move_is_indeterminate(self):
        found = self._outcome(["unchanged", "already_correct"])
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "field_states_unchanged" in effect_kinds(found)

    def test_a_field_that_already_held_the_value_is_only_accepted(self):
        """The form holds what was asked for and that is not evidence of a fill."""
        found = self._outcome(["already_correct"])
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "field_states_already_correct")["measured_by"] is None

    def test_without_a_read_back_it_is_only_accepted(self):
        found = self._outcome(["not_read"])
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "field_states_not_observed")["measured_by"] is None

    def test_nothing_filled_at_all_is_indeterminate_not_failed(self):
        """Every attempt raised, and Playwright's raises include timeouts."""
        found = self._outcome([], offered_fields=2, filled_count=0, failed_count=2)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "no_field_was_filled" in effect_kinds(found)

    def test_the_offered_count_says_it_is_not_evidence(self):
        found = self._outcome(["changed"], offered_fields=7)
        offered = effect_named(found, "fields_offered")
        assert offered["count"] == 7
        assert offered["measured_by"] == "len() of the data parameter"

    def test_a_dispatched_submit_never_raises_the_rung(self):
        found = self._outcome(["not_read"], submit_requested=True, submit_dispatched=True)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "form_submit_dispatched")["measured_by"] is None

    def test_the_named_field_lists_are_bounded(self):
        """The envelope is copied into a database column."""
        found = self._outcome(["unchanged"] * 500)
        named = effect_named(found, "field_states_observed")["unchanged_fields"]
        assert len(named) == form_module._MAX_NAMED_FIELDS


@pytest.mark.browser
class TestFormAgainstARealPage:
    async def test_filling_a_text_input_is_observed(self, at_page):
        ctx = await at_page("/form")
        result = await run_module("browser.form", {"data": {"email": "a@b.test"}}, ctx)
        assert rung_of(result) == Outcome.OBSERVED.value
        # Independent of anything the module reported.
        assert await ctx["browser"].real_page.input_value("#email") == "a@b.test"

    async def test_a_select_is_observed_by_its_selected_index(self, at_page):
        ctx = await at_page("/form")
        result = await run_module("browser.form", {"data": {"plan": "pro"}}, ctx)
        assert rung_of(result) == Outcome.OBSERVED.value
        assert await ctx["browser"].real_page.input_value('[name="plan"]') == "pro"

    async def test_a_checkbox_is_observed_by_its_checked_state(self, at_page):
        ctx = await at_page("/form")
        result = await run_module("browser.form", {"data": {"tos": True}}, ctx)
        assert rung_of(result) == Outcome.OBSERVED.value
        assert await ctx["browser"].real_page.is_checked('[name="tos"]')

    async def test_a_radio_is_observed_by_which_member_of_its_group_is_checked(self, at_page):
        """This is the test that found the radio branch had never worked.

        The JS was a non-raw Python literal, so `\\\\` collapsed to one
        backslash and the page received `value.replace(/\\/g, ...)` -- a regex
        literal that never terminates. Chromium answered `SyntaxError: Invalid
        regular expression` for every radio fill, the per-field except swallowed
        it into `failed_fields`, and the step still returned success. The rung
        read INDETERMINATE, which is what pointed at it.
        """
        ctx = await at_page("/form")
        result = await run_module("browser.form", {"data": {"color": "blue"}}, ctx)
        assert result["failed_fields"] == []
        assert rung_of(result) == Outcome.OBSERVED.value
        assert await ctx["browser"].real_page.is_checked('[name="color"][value="blue"]')

    async def test_a_radio_value_with_a_quote_in_it_still_fills(self, at_page):
        """The escaping the broken regex was there to do in the first place."""
        ctx = await at_page("/form")
        result = await run_module("browser.form", {"data": {"quoted": 'say "hi"'}}, ctx)
        assert result["failed_fields"] == []
        assert rung_of(result) == Outcome.OBSERVED.value
        assert await ctx["browser"].real_page.is_checked(
            '[name="quoted"][value="say \\"hi\\""]'
        )

    async def test_a_field_that_throws_the_keystrokes_away_is_indeterminate(self, at_page):
        """The case ``success_count`` reports as a clean success.

        Every keystroke is delivered and the field's own handler wipes it. The
        old count said 1 filled, 0 failed. The read-back says nothing moved.
        """
        ctx = await at_page("/form")
        result = await run_module("browser.form", {"data": {"resetme": "hello"}}, ctx)
        assert result["success_count"] == 1 and result["fail_count"] == 0
        assert rung_of(result) == Outcome.INDETERMINATE.value
        assert await ctx["browser"].real_page.input_value("#resetme") == ""

    async def test_a_checkbox_that_was_already_ticked_is_only_accepted(self, at_page):
        """Nothing was clicked, because nothing needed to be. Nothing was observed."""
        ctx = await at_page("/form")
        result = await run_module("browser.form", {"data": {"already": True}}, ctx)
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert await ctx["browser"].real_page.is_checked('[name="already"]')

    async def test_one_good_field_beside_a_dead_one_is_still_observed(self, at_page):
        ctx = await at_page("/form")
        result = await run_module(
            "browser.form", {"data": {"email": "a@b.test", "resetme": "hello"}}, ctx
        )
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        observed = effect_named(found, "field_states_observed")
        assert observed["changed"] == 1 and observed["unchanged"] == 1
        assert observed["unchanged_fields"] == ["resetme"]

    async def test_the_submit_is_carried_but_never_measured(self, at_page):
        ctx = await at_page("/form")
        result = await run_module(
            "browser.form",
            {"data": {"email": "a@b.test"}, "submit": True, "submit_selector": "#go"},
            ctx,
        )
        assert result["submitted"] is True
        # The page really did handle the submit -- and the envelope still
        # refuses to say so, because this module did not look.
        assert await ctx["browser"].real_page.text_content("#submitted") == "yes"
        assert effect_named(envelope_of(result), "form_submit_dispatched")["measured_by"] is None

    async def test_no_password_reaches_the_envelope(self, at_page):
        """This module fills password fields into a dict that becomes a trace row."""
        ctx = await at_page("/form")
        secret = "-".join(("fixture", "not", "a", "real", "password"))
        result = await run_module("browser.form", {"data": {"password": secret}}, ctx)
        assert rung_of(result) == Outcome.OBSERVED.value
        assert secret not in repr(envelope_of(result))


# ===========================================================================
# browser.login -- logged_in was a boolean; the indicator needed reading twice
# ===========================================================================

class TestRungLogin:
    def _outcome(self, **rest):
        rest.setdefault("url_before", "https://site.test/login")
        rest.setdefault("url_after", "https://site.test/login")
        rest.setdefault("indicator", "")
        rest.setdefault("indicator_before", None)
        rest.setdefault("indicator_after", None)
        rest.setdefault("mfa_detected", False)
        return login_module._login_outcome(**rest)

    def test_a_url_that_moved_with_no_contract_is_observed_and_inferred(self):
        found = self._outcome(url_after="https://site.test/home")
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value
        assert effect_named(found, "page_url_moved")["changed"] is True

    def test_a_url_that_did_not_move_with_no_contract_is_indeterminate(self):
        """A single-page-application login changes no URL. So does a dead submit."""
        found = self._outcome()
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "nothing_observed_to_change" in effect_kinds(found)

    def test_an_indicator_that_appeared_is_observed_and_claimed_by_the_caller(self):
        found = self._outcome(
            indicator=".dash", indicator_before=False, indicator_after=True,
            url_after="https://site.test/home",
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.CALLER.value
        assert found["postcondition"] == (
            "an element matching success_indicator '.dash' is present after the login attempt"
        )
        assert "success_indicator_appeared" in effect_kinds(found)

    def test_an_absent_indicator_is_failed_because_the_caller_declared_it(self):
        found = self._outcome(indicator=".dash", indicator_before=False, indicator_after=False)
        assert found["rung"] == Outcome.FAILED.value
        assert found["claim_by"] == ClaimBy.CALLER.value

    def test_an_indicator_that_was_already_there_is_only_accepted(self):
        """The one this module used to render as a green login.

        ``/home`` matched, or ``.dashboard`` was on the page the whole time. The
        reading is identical had the step done nothing.
        """
        found = self._outcome(indicator=".dash", indicator_before=True, indicator_after=True)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert "success_indicator_was_already_present" in effect_kinds(found)

    def test_an_indicator_that_was_already_there_plus_a_moved_url_is_observed(self):
        """The URL is a second, independent reading, and it did move."""
        found = self._outcome(
            indicator="/home", indicator_before=True, indicator_after=True,
            url_before="https://site.test/home?next=1", url_after="https://site.test/home",
        )
        assert found["rung"] == Outcome.OBSERVED.value

    def test_an_indicator_we_could_not_evaluate_is_indeterminate_not_failed(self):
        """A selector that raises is not a login that failed."""
        found = self._outcome(indicator="::bogus", indicator_before=None, indicator_after=None)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "success_indicator_not_evaluable" in effect_kinds(found)

    def test_the_url_form_and_the_selector_form_are_labelled(self):
        as_url = self._outcome(indicator="/home", indicator_after=True)
        as_css = self._outcome(indicator=".dash", indicator_after=True)
        assert effect_named(as_url, "success_indicator_evaluated")["read_as"] == "url fragment"
        assert effect_named(as_css, "success_indicator_evaluated")["read_as"] == "CSS selector"
        # ...and the predicate the envelope names says which reading was done.
        assert "appears in page.url" in as_url["postcondition"]
        assert "an element matching" in as_css["postcondition"]

    def test_an_unfinished_mfa_prompt_is_indeterminate(self):
        found = login_module._mfa_unresolved_outcome(url_changed=True)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "mfa_prompt_unresolved" in effect_kinds(found)


@pytest.mark.browser
class TestLoginAgainstARealPage:
    CREDS = {"username": "someone", "password": "secret", "wait_ms": 1000}

    async def test_a_login_that_reveals_the_indicator_is_observed(self, at_page):
        ctx = await at_page("/login-ok")
        result = await run_module(
            "browser.login", {**self.CREDS, "success_indicator": ".dash"}, ctx
        )
        assert result["logged_in"] is True
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.CALLER.value
        contract = effect_named(found, "success_indicator_evaluated")
        assert (contract["held_before"], contract["held_after"]) == (False, True)

    async def test_a_login_that_only_moves_the_url_is_observed_and_inferred(self, at_page):
        ctx = await at_page("/login-ok")
        result = await run_module("browser.login", dict(self.CREDS), ctx)
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value
        assert result["url_after"].endswith("/dashboard")

    async def test_a_dead_submit_with_a_declared_indicator_is_failed(self, at_page):
        ctx = await at_page("/login-nothing")
        result = await run_module(
            "browser.login", {**self.CREDS, "success_indicator": ".dash"}, ctx
        )
        assert result["logged_in"] is False
        assert rung_of(result) == Outcome.FAILED.value

    async def test_a_dead_submit_with_no_indicator_is_indeterminate(self, at_page):
        ctx = await at_page("/login-nothing")
        result = await run_module("browser.login", dict(self.CREDS), ctx)
        assert rung_of(result) == Outcome.INDETERMINATE.value

    async def test_an_indicator_that_was_on_the_page_all_along_is_only_accepted(self, at_page):
        """``logged_in`` is True here and nothing happened. That is the defect.

        The page carries ``.dash`` before anybody types a password, and the
        submit does nothing at all. The old boolean says the login worked; the
        rung says the reading is not evidence of it.
        """
        ctx = await at_page("/login-already")
        result = await run_module(
            "browser.login", {**self.CREDS, "success_indicator": ".dash"}, ctx
        )
        assert result["logged_in"] is True
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert "success_indicator_was_already_present" in effect_kinds(envelope_of(result))

    async def test_the_form_really_was_filled(self, at_page):
        """The rung is about the login; the credentials still have to land."""
        ctx = await at_page("/login-nothing")
        await run_module("browser.login", dict(self.CREDS), ctx)
        assert await ctx["browser"].real_page.input_value("#user") == "someone"


# ===========================================================================
# browser.dialog -- listening is a read, accepting is an unmeasured effect
# ===========================================================================

class TestRungDialog:
    def test_listening_and_seeing_a_dialog_is_observed(self):
        found = dialog_module._dialog_outcome(
            action="listen", appeared=True, dialog_type="confirm", handle_error=None
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "dialog_observed")["dialog_type"] == "confirm"

    def test_listening_and_seeing_none_is_the_empty_read(self):
        found = dialog_module._dialog_outcome(
            action="listen", appeared=False, dialog_type=None, handle_error=None
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "no_dialog_in_window")["measured_by"] is None

    @pytest.mark.parametrize("action", ["accept", "dismiss"])
    def test_handling_a_dialog_is_accepted_and_no_higher(self, action):
        """A dismissed confirm and an accepted one leave an identical page."""
        found = dialog_module._dialog_outcome(
            action=action, appeared=True, dialog_type="confirm", handle_error=None
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "dialog_handled")["measured_by"] is None

    def test_a_handler_that_raised_is_failed(self):
        found = dialog_module._dialog_outcome(
            action="accept", appeared=True, dialog_type="alert",
            handle_error="Error: Cannot accept dialog which is already handled!",
        )
        assert found["rung"] == Outcome.FAILED.value
        assert "already handled" in effect_named(found, "dialog_handling_raised")["reason"]

    def test_no_dialog_to_accept_is_indeterminate_not_failed(self):
        """It is a timeout. We know we stopped waiting, not that nothing was coming."""
        found = dialog_module._dialog_outcome(
            action="accept", appeared=False, dialog_type=None, handle_error=None
        )
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "dialog_not_handled" in effect_kinds(found)


@pytest.mark.browser
class TestDialogAgainstARealPage:
    async def test_accepting_a_real_confirm_is_accepted(self, at_page):
        ctx = await at_page("/dialog")
        page = ctx["browser"].real_page

        task = asyncio.create_task(
            run_module("browser.dialog", {"action": "accept", "timeout": 5000}, ctx)
        )
        await asyncio.sleep(0.3)  # let the module attach its listener first
        asked = asyncio.create_task(
            page.evaluate("() => { window.__answer = confirm('shall we?'); }")
        )
        result = await task
        await asked

        assert result["type"] == "confirm"
        assert result["message"] == "shall we?"
        assert rung_of(result) == Outcome.ACCEPTED.value
        # Independent: the page itself saw the accept.
        assert await page.evaluate("() => window.__answer") is True

    async def test_dismissing_a_real_confirm_is_accepted(self, at_page):
        ctx = await at_page("/dialog")
        page = ctx["browser"].real_page

        task = asyncio.create_task(
            run_module("browser.dialog", {"action": "dismiss", "timeout": 5000}, ctx)
        )
        await asyncio.sleep(0.3)
        asked = asyncio.create_task(
            page.evaluate("() => { window.__answer = confirm('shall we?'); }")
        )
        result = await task
        await asked

        assert rung_of(result) == Outcome.ACCEPTED.value
        assert await page.evaluate("() => window.__answer") is False

    async def test_no_dialog_inside_the_window_is_indeterminate(self, at_page):
        ctx = await at_page("/dialog")
        result = await run_module("browser.dialog", {"action": "accept", "timeout": 400}, ctx)
        assert result["note"] == "No dialog appeared within timeout"
        assert rung_of(result) == Outcome.INDETERMINATE.value


# ===========================================================================
# browser.challenge -- the page is read twice and the readings disagree
# ===========================================================================

class TestRungChallenge:
    def test_a_page_that_cleared_is_observed_and_inferred(self):
        found = challenge_module._challenge_outcome(
            challenge_type="cloudflare", resolved=True, route="auto_wait", wait_seconds=3.0
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value
        assert "challenge_detected" in effect_kinds(found)
        assert effect_named(found, "challenge_page_cleared")["route"] == "auto_wait"

    def test_a_page_that_did_not_clear_is_indeterminate(self):
        found = challenge_module._challenge_outcome(
            challenge_type="hcaptcha", resolved=False, route="human", wait_seconds=120.0
        )
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "challenge_page_did_not_clear" in effect_kinds(found)

    def test_no_challenge_detected_is_an_empty_read_not_a_clean_page(self):
        found = challenge_module._no_challenge_outcome("An Ordinary Page")
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "no_challenge_pattern_matched")["measured_by"] is None

    def test_every_route_has_a_sentence(self):
        """A route with no entry would render as a bare slug inside the detail."""
        for route in ("auto_wait", "api_solver", "human", "no_human_fallback"):
            assert route in challenge_module._ROUTE_DETAIL


@pytest.mark.browser
class TestChallengeAgainstARealPage:
    async def test_a_page_that_clears_itself_is_observed(self, at_page):
        ctx = await at_page("/challenge-clears")
        result = await run_module(
            "browser.challenge", {"auto_wait_seconds": 5, "human_fallback": False}, ctx
        )
        assert result["status"] == "auto_resolved"
        assert result["page_changed"] is True
        assert rung_of(result) == Outcome.OBSERVED.value

    async def test_a_page_that_never_clears_is_indeterminate(self, at_page):
        ctx = await at_page("/challenge-stuck")
        result = await run_module(
            "browser.challenge", {"auto_wait_seconds": 1, "human_fallback": False}, ctx
        )
        assert result["status"] == "timeout"
        assert rung_of(result) == Outcome.INDETERMINATE.value

    async def test_an_ordinary_page_is_accepted_and_not_declared_clean(self, at_page):
        ctx = await at_page("/plain")
        result = await run_module("browser.challenge", {"auto_wait_seconds": 0}, ctx)
        assert result["status"] == "no_challenge"
        assert rung_of(result) == Outcome.ACCEPTED.value


# ===========================================================================
# browser.drag -- from/to is arithmetic; the source and the target are the page
# ===========================================================================

BOX = {"x": 10.0, "y": 10.0, "width": 40.0, "height": 40.0}


class TestRungDrag:
    def _outcome(self, **rest):
        rest.setdefault("source_box_before", BOX)
        rest.setdefault("source_box_after", BOX)
        rest.setdefault("source_read_error", None)
        rest.setdefault("target_children_before", 0)
        rest.setdefault("target_children_after", 0)
        rest.setdefault("target_read_error", None)
        return drag_module._drag_outcome(**rest)

    def test_a_source_that_moved_is_observed(self):
        found = self._outcome(source_box_after={**BOX, "x": 240.0, "y": 50.0})
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value
        assert effect_named(found, "source_box_observed")["moved"] is True

    def test_a_source_that_left_the_layout_is_observed(self):
        found = self._outcome(source_box_after=None)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "source_box_observed")["left_layout"] is True

    def test_a_target_that_gained_a_child_is_observed(self):
        found = self._outcome(target_children_after=1)
        assert found["rung"] == Outcome.OBSERVED.value

    def test_sub_pixel_drift_is_not_a_drop(self):
        found = self._outcome(source_box_after={**BOX, "x": 10.2})
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_a_page_that_did_not_move_is_indeterminate_not_failed(self):
        """HTML5 drag-and-drop cannot be driven by synthetic mouse events at all."""
        found = self._outcome()
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "page_unchanged_by_the_drag" in effect_kinds(found)

    def test_nothing_readable_at_all_is_only_accepted(self):
        found = self._outcome(
            source_box_after=None, source_read_error="TimeoutError: exceeded",
            target_children_after=None, target_read_error="TimeoutError: exceeded",
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert "nothing_could_be_read_back" in effect_kinds(found)

    def test_the_pointer_path_says_it_is_not_evidence(self):
        found = self._outcome()
        assert "arithmetic" in effect_named(found, "pointer_path_offered")["measured_by"]


@pytest.mark.browser
class TestDragAgainstARealPage:
    async def test_a_drag_a_page_responds_to_is_observed(self, at_page):
        ctx = await at_page("/drag-live")
        page = ctx["browser"].real_page
        before = await page.locator("#src").bounding_box()

        result = await run_module("browser.drag", {"source": "#src", "target": "#dst"}, ctx)

        assert rung_of(result) == Outcome.OBSERVED.value
        # Independent of anything the module reported.
        after = await page.locator("#src").bounding_box()
        assert abs(after["x"] - before["x"]) > 0.5
        assert await page.locator("#dst").evaluate("el => el.childElementCount") == 1

    async def test_a_drag_a_page_ignores_is_indeterminate(self, at_page):
        """The same four mouse calls, the same 'success', a page that did nothing."""
        ctx = await at_page("/drag-dead")
        page = ctx["browser"].real_page
        before = await page.locator("#src").bounding_box()

        result = await run_module("browser.drag", {"source": "#src", "target": "#dst"}, ctx)

        assert result["status"] == "success"
        assert rung_of(result) == Outcome.INDETERMINATE.value
        assert await page.locator("#src").bounding_box() == before

    async def test_a_dead_drag_on_a_scrollable_page_is_still_indeterminate(self, at_page):
        """The one the short fixture above could not catch.

        A synthetic mouse-down drag makes Chromium autoscroll, and
        `bounding_box()` is viewport-relative -- Playwright says so in its own
        docstring. On a page tall enough to scroll, the box therefore moved
        whether or not the drag did, and the module reported OBSERVED on a page
        with NO drag handler, NO drop handler and no javascript at all.

        The test above passes because its body cannot scroll: it was pinning the
        fixture, not the predicate. This one scrolls, and the assertion below
        that the document position is unchanged is what makes the INDETERMINATE
        meaningful rather than incidental.
        """
        ctx = await at_page("/drag-dead-tall")
        page = ctx["browser"].real_page
        before_doc = await page.evaluate(
            "() => { const r = document.querySelector(\"#src\").getBoundingClientRect();"
            "  return {x: r.x + scrollX, y: r.y + scrollY}; }"
        )

        result = await run_module("browser.drag", {"source": "#src", "target": "#dst"}, ctx)

        after_doc = await page.evaluate(
            "() => { const r = document.querySelector(\"#src\").getBoundingClientRect();"
            "  return {x: r.x + scrollX, y: r.y + scrollY}; }"
        )
        assert after_doc == before_doc, "the element moved in the document; fixture is wrong"
        assert result["status"] == "success"
        assert rung_of(result) == Outcome.INDETERMINATE.value


    async def test_a_source_the_page_deleted_is_observed(self, at_page):
        """The clearest effect a drag can have, previously reported as nothing.

        `bounding_box()` on a node the page has removed does not return None --
        it RAISES, because the locator no longer resolves -- and a raise reads
        as "we could not look", which is not evidence. So a drag-to-trash that
        demonstrably destroyed the source came back `indeterminate`, carrying an
        effect named `page_unchanged_by_the_drag` on a page that had just
        deleted the element. Counting the nodes is what separates gone from
        unreadable.
        """
        ctx = await at_page("/drag-trash")
        page = ctx["browser"].real_page
        assert await page.locator("#src").count() == 1

        result = await run_module("browser.drag", {"source": "#src", "target": "#trash"}, ctx)

        assert await page.locator("#src").count() == 0, "the page did not delete it"
        assert rung_of(result) == Outcome.OBSERVED.value
        effect = effect_named(envelope_of(result), "source_box_observed")
        assert effect["left_layout"] is True
        assert effect["source_nodes_after"] == 0
        assert effect["reason"] is None, "a deleted node is not an unreadable one"

    async def test_a_scrolling_pane_is_not_a_drag(self, at_page):
        """The ordinary app shell, and the case window.scrollY cannot see.

        html and body are `overflow:hidden`; the content pane scrolls instead.
        Chromium's drag autoscroll moves the pane ~3900px while window.scrollY
        stays 0 for the whole run, so correcting by the window scroll adds
        exactly nothing and the pane's travel reads as movement. Measured on
        this page, which has no script in it at all, the rung was `observed`.
        """
        ctx = await at_page("/drag-dead-shell")
        page = ctx["browser"].real_page
        before = await page.evaluate(
            "() => ({top: document.querySelector('#src').offsetTop,"
            "        pane: document.querySelector('#pane').scrollTop,"
            "        win: scrollY, scripts: document.scripts.length})"
        )
        assert before["scripts"] == 0

        result = await run_module("browser.drag", {"source": "#src", "target": "#dst"}, ctx)

        after = await page.evaluate(
            "() => ({top: document.querySelector('#src').offsetTop,"
            "        pane: document.querySelector('#pane').scrollTop,"
            "        win: scrollY})"
        )
        assert after["pane"] > 1000, "the pane did not scroll; the fixture is inert"
        assert after["win"] == 0, "the window scrolled; this is no longer the pane case"
        assert after["top"] == before["top"], "the element moved; the fixture is wrong"
        assert rung_of(result) == Outcome.INDETERMINATE.value

    async def test_a_fixed_source_does_not_move_when_the_page_scrolls(self, at_page):
        """A reading that was right before a fix, and wrong after it.

        A `position:fixed` element is anchored to the viewport, so its rect is
        already scroll-invariant and the raw reading correctly said "did not
        move". Adding the window scroll to it manufactured a displacement of
        several thousand pixels on a page with no script. A correction that
        invents movement is worse than the reading it replaced.
        """
        ctx = await at_page("/drag-dead-fixed")
        page = ctx["browser"].real_page

        result = await run_module("browser.drag", {"source": "#src", "target": "#dst"}, ctx)

        assert await page.evaluate("() => scrollY") > 1000, "the page did not scroll"
        assert rung_of(result) == Outcome.INDETERMINATE.value

    async def test_a_drag_that_really_moves_the_element_is_still_observed(self, at_page):
        """The positive control the other three exist to protect.

        Every fixture above is a page where nothing happened, so a reading that
        simply never reported movement would satisfy all of them. This one
        moves the element for real, on a page that scrolls while it does, and
        the rung has to notice.
        """
        ctx = await at_page("/drag-moves")
        page = ctx["browser"].real_page
        before = await page.evaluate("() => document.querySelector('#src').offsetTop")

        result = await run_module("browser.drag", {"source": "#src", "target": "#dst"}, ctx)

        after = await page.evaluate("() => document.querySelector('#src').offsetTop")
        assert after != before, "the page did not move the element; fixture is broken"
        assert rung_of(result) == Outcome.OBSERVED.value



# ===========================================================================
# browser.interact -- the declined paths dispatched nothing at all
# ===========================================================================

class TestRungInteract:
    def test_a_declined_breakpoint_dispatched_nothing(self):
        """The engine's default stamped these `dispatched`, which is the one lie."""
        for resolution in ("rejected", "timeout"):
            found = interact_module._interact_outcome(resolution=resolution)
            assert found["rung"] == Outcome.INDETERMINATE.value
            assert effect_named(found, "no_action_dispatched")["resolution"] == resolution

    def test_a_typed_value_that_changed_is_observed(self):
        found = interact_module._interact_outcome(
            resolution="approved", action="type", value_before="", value_after="hello"
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value
        assert effect_named(found, "field_value_observed")["characters_after"] == 5

    def test_a_typed_value_that_did_not_change_is_indeterminate(self):
        found = interact_module._interact_outcome(
            resolution="approved", action="type", value_before="x", value_after="x"
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_an_unreadable_control_is_only_accepted(self):
        found = interact_module._interact_outcome(
            resolution="approved", action="select", value_before=None, value_after=None,
            read_error="Error: not an <input> element",
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "field_value_not_observed")["measured_by"] is None

    @pytest.mark.parametrize("action", ["click", "toggle"])
    def test_a_click_is_accepted_and_no_higher(self, action):
        found = interact_module._interact_outcome(resolution="approved", action=action)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "input_event_acknowledged")["measured_by"] is None

    def test_an_action_that_raised_is_failed(self):
        found = interact_module._interact_outcome(
            resolution="approved", action="click", action_error="Error: strict mode violation",
        )
        assert found["rung"] == Outcome.FAILED.value

    def test_an_action_that_timed_out_is_indeterminate(self):
        found = interact_module._interact_outcome(
            resolution="approved", action="click",
            action_error="TimeoutError: exceeded", action_timed_out=True,
        )
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "action_timed_out" in effect_kinds(found)

    def test_the_chosen_action_is_never_the_evidence(self):
        found = interact_module._interact_outcome(resolution="approved", action="click")
        assert "says what was asked for" in effect_named(found, "action_chosen_by_a_person")["detail"]


class _FakeRequest:
    breakpoint_id = "bp-under-test"


class _FakeResult:
    def __init__(self, status, final_inputs=None):
        self.status = status
        self.final_inputs = final_inputs or {}


class _FakeManager:
    """The smallest thing `browser.interact` will talk to."""

    def __init__(self, result):
        self._result = result

    async def create_breakpoint(self, **kwargs):
        return _FakeRequest()

    async def wait_for_resolution(self, breakpoint_id, check_timeout=False):
        return self._result


@pytest.fixture
def answered_by(monkeypatch):
    """``answered_by(status, inputs)`` -> the breakpoint resolves that way."""
    import core.engine.breakpoints as breakpoints

    def _install(status, final_inputs=None):
        manager = _FakeManager(_FakeResult(status, final_inputs))
        monkeypatch.setattr(breakpoints, "get_breakpoint_manager", lambda: manager)

    return _install


@pytest.mark.browser
class TestInteractAgainstARealPage:
    async def test_a_typed_action_a_human_chose_is_observed(self, at_page, answered_by):
        from core.engine.breakpoints import BreakpointStatus

        ctx = await at_page("/form")
        answered_by(
            BreakpointStatus.APPROVED,
            {"action": "type", "selector": "#email", "value": "a@b.test"},
        )
        result = await run_module("browser.interact", {}, ctx)

        assert rung_of(result) == Outcome.OBSERVED.value
        assert await ctx["browser"].real_page.input_value("#email") == "a@b.test"

    async def test_a_typed_action_the_page_throws_away_is_indeterminate(self, at_page, answered_by):
        from core.engine.breakpoints import BreakpointStatus

        ctx = await at_page("/form")
        answered_by(
            BreakpointStatus.APPROVED,
            {"action": "type", "selector": "#resetme", "value": "hello"},
        )
        result = await run_module("browser.interact", {}, ctx)

        assert result["action_status"] == "typed"
        assert rung_of(result) == Outcome.INDETERMINATE.value

    async def test_a_click_a_human_chose_is_accepted(self, at_page, answered_by):
        from core.engine.breakpoints import BreakpointStatus

        ctx = await at_page("/form")
        answered_by(BreakpointStatus.APPROVED, {"action": "click", "selector": "#go"})
        result = await run_module("browser.interact", {}, ctx)

        assert rung_of(result) == Outcome.ACCEPTED.value
        # The click really did reach the page. The rung still does not say so.
        assert await ctx["browser"].real_page.text_content("#submitted") == "yes"

    async def test_a_declined_breakpoint_reports_indeterminate_not_dispatched(
        self, at_page, answered_by
    ):
        from core.engine.breakpoints import BreakpointStatus

        ctx = await at_page("/form")
        answered_by(BreakpointStatus.REJECTED)
        result = await run_module("browser.interact", {}, ctx)

        assert result["__event__"] == "rejected"
        assert rung_of(result) == Outcome.INDETERMINATE.value
        assert "no_action_dispatched" in effect_kinds(envelope_of(result))


# ===========================================================================
# The two refusals, kept as measurements
# ===========================================================================

@pytest.mark.browser
class TestPressHasNothingToRead:
    """`browser.press` stays undeclared, and this is the measurement that decided it.

    ``document.activeElement`` is the one candidate here that is a reading of
    the page rather than a restatement of the ``key`` parameter. It moves for
    `Tab` and it does not move for `Enter` or `Escape` -- this module's own two
    documented examples -- not even when the `Enter` fires a handler that
    rewrites the document.

    If the last assertion here ever starts failing, that is the good news: the
    signal has become usable and `browser.press` can be given a rung.
    """

    async def _active(self, page):
        return await page.evaluate(
            "() => { const e = document.activeElement;"
            " return e ? e.tagName + '#' + (e.id || '') : null; }"
        )

    async def test_tab_moves_the_focus(self, at_page):
        ctx = await at_page("/press")
        page = ctx["browser"].real_page
        before = await self._active(page)
        await run_module("browser.press", {"key": "Tab"}, ctx)
        assert before == "BODY#"
        assert await self._active(page) == "INPUT#a"

    @pytest.mark.parametrize("key", ["Enter", "Escape"])
    async def test_the_two_documented_keys_move_nothing(self, at_page, key):
        ctx = await at_page("/press")
        page = ctx["browser"].real_page
        await page.focus("#a")
        before = await self._active(page)
        await run_module("browser.press", {"key": key}, ctx)
        assert await self._active(page) == before == "INPUT#a"

    async def test_an_enter_that_rewrote_the_page_still_moved_no_focus(self, at_page):
        """The press did the most consequential thing a press can do."""
        ctx = await at_page("/press")
        page = ctx["browser"].real_page
        await page.focus("#go")
        result = await run_module("browser.press", {"key": "Enter"}, ctx)

        assert await page.text_content("#log") == "clicked"
        assert await self._active(page) == "BUTTON#go"
        # ...and so this module reports no envelope of its own.
        assert result["status"] == "success"
        assert envelope_of(result) is None


@pytest.mark.browser
class TestHoverIsStillUndeclared:
    """Re-asserted from the first pass so that removing it takes a deliberate act."""

    async def test_the_css_hover_state_never_arrives(self, at_page):
        ctx = await at_page("/press")
        page = ctx["browser"].real_page
        await page.hover("#a")
        assert await page.evaluate("() => document.querySelectorAll(':hover').length") == 0

    async def test_and_so_hover_reports_no_envelope_of_its_own(self, at_page):
        ctx = await at_page("/press")
        result = await run_module("browser.hover", {"selector": "#a"}, ctx)
        assert result["status"] == "success"
        assert envelope_of(result) is None


# ===========================================================================
# What none of these modules may claim
# ===========================================================================

class TestNobodyReachedForVerified:
    """VERIFIED means a postcondition was evaluated and held. None was declared.

    `browser.login` is the interesting one: it is the only module in this group
    that evaluates a predicate the CALLER supplied, which is the shape VERIFIED
    is for. It still does not declare one, because "an element matching
    `.dashboard` exists" is satisfied by a login page that renders its shell
    before authenticating, and ``logged_in`` is the field a person reads before
    letting an automation spend money.
    """

    DECLARED = [
        "browser.form", "browser.login", "browser.dialog",
        "browser.challenge", "browser.drag", "browser.interact",
    ]

    @pytest.mark.parametrize("module_id", DECLARED)
    def test_none_of_them_declares_a_postcondition(self, module_id):
        metadata = ModuleRegistry.get_metadata(module_id) or {}
        assert not metadata.get("postcondition")
        assert ceiling_for(metadata.get("postcondition")) == Outcome.OBSERVED

    @pytest.mark.parametrize("module_id", DECLARED)
    def test_none_of_them_writes_the_word(self, module_id):
        source = Path(ModuleRegistry.get(module_id).__module__.replace(".", "/"))
        path = Path(__file__).parent.parent.parent / "src" / f"{source}.py"
        assert "Outcome.VERIFIED" not in path.read_text(encoding="utf-8")

    @pytest.mark.parametrize("module_id", ["browser.press", "browser.hover"])
    def test_the_two_refusals_are_still_refusals(self, module_id):
        """They stay on the UNDECLARED list, and the list is what says so."""
        from tests.core.test_outcome_declaration_coverage import UNDECLARED

        assert module_id in UNDECLARED


# ===========================================================================
# browser.wait -- against a real page, where a typo used to count as evidence
# ===========================================================================

class TestWaitAgainstARealPage:
    """`hidden` and `detached` are true of a selector that matches nothing.

    These run the module through the real driver against real Chromium, so they
    pin the wiring as well as the predicate: the count has to be read on the
    correct side of the wait, from the same page the wait ran against.
    """

    async def test_a_typo_does_not_count_as_a_hidden_element(self, at_page):
        """Measured before the fix: returned in 7.3ms, reported OBSERVED."""
        ctx = await at_page("/wait-states")

        result = await run_module(
            "browser.wait",
            {"selector": "#nosuchthign", "state": "hidden", "timeout_ms": 3000},
            ctx,
        )

        assert result["status"] == "success"
        assert rung_of(result) == Outcome.INDETERMINATE.value
        assert effect_named(envelope_of(result), "element_state_observed")["matching_nodes"] == 0

    async def test_an_element_that_is_really_hidden_is_observed(self, at_page):
        """The other half: the fix must not make every hidden wait amber."""
        ctx = await at_page("/wait-states")

        result = await run_module(
            "browser.wait",
            {"selector": "#gone", "state": "hidden", "timeout_ms": 3000},
            ctx,
        )

        assert rung_of(result) == Outcome.OBSERVED.value
        assert effect_named(envelope_of(result), "element_state_observed")["matching_nodes"] == 1

    async def test_a_node_the_page_removed_while_we_watched_is_observed(self, at_page):
        """The count that earns this is read BEFORE the wait -- afterwards the
        node is gone and reads 0, exactly like a selector that never matched."""
        ctx = await at_page("/wait-states")
        await ctx["browser"].real_page.evaluate("doomLater()")

        result = await run_module(
            "browser.wait",
            {"selector": "#doomed", "state": "detached", "timeout_ms": 5000},
            ctx,
        )

        assert rung_of(result) == Outcome.OBSERVED.value
        effect = effect_named(envelope_of(result), "element_state_observed")
        assert effect["matching_nodes"] == 1
        assert effect["counted"] == "before"
        assert await ctx["browser"].real_page.locator("#doomed").count() == 0

    async def test_a_selector_that_never_matched_is_not_a_detachment(self, at_page):
        """Measured before the fix: returned in 0.6ms, reported OBSERVED."""
        ctx = await at_page("/wait-states")

        result = await run_module(
            "browser.wait",
            {"selector": "#nosuchthign", "state": "detached", "timeout_ms": 3000},
            ctx,
        )

        assert rung_of(result) == Outcome.INDETERMINATE.value
        assert effect_named(envelope_of(result), "element_state_observed")["matching_nodes"] == 0

    async def test_a_hidden_wait_satisfied_by_removal_is_observed(self, at_page):
        """Five real nodes, deleted while we watch. The page did change.

        Counting only after the wait read 0 here and called it INDETERMINATE --
        the same answer a misspelled selector gets, for a run that was entirely
        correct. The before-count is what separates them, and without the page
        removing anything the wait would have timed out instead of returning.
        """
        ctx = await at_page("/wait-states")
        page = ctx["browser"].real_page
        assert await page.locator(".crowd").count() == 5
        await page.evaluate("clearCrowdLater()")

        result = await run_module(
            "browser.wait",
            {"selector": ".crowd", "state": "hidden", "timeout_ms": 5000},
            ctx,
        )

        assert rung_of(result) == Outcome.OBSERVED.value
        effect = effect_named(envelope_of(result), "element_state_observed")
        assert effect["matching_nodes"] == 5
        assert effect["counts"] == {"before": 5, "after": 0}
        assert await page.locator(".crowd").count() == 0

    async def test_a_present_element_still_observes_normally(self, at_page):
        """`visible` needs no count and must not have acquired one."""
        ctx = await at_page("/wait-states")

        result = await run_module(
            "browser.wait",
            {"selector": "#real", "state": "visible", "timeout_ms": 3000},
            ctx,
        )

        assert rung_of(result) == Outcome.OBSERVED.value
        assert "matching_nodes" not in effect_named(envelope_of(result), "element_state_observed")

