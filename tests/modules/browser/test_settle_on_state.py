"""Browser modules settle on page state, never on fixed sleeps.

Every test here either forbids fixed waits outright -- ``page.wait_for_timeout``
and any non-zero ``asyncio.sleep`` issued from a browser module raise -- or
shows that the step ends as a direct consequence of the page changing: a
navigation, a dialog event, an element appearing. Timings are asserted
against the fixed pauses the modules used to take, with generous margins for
a loaded CI runner.
"""

import asyncio
import http.server
import socketserver
import sys
import threading
import time

import pytest

from core.modules.atomic.browser._settle import first_state
from core.modules.registry import ModuleRegistry
from core.validation import validate_workflow
from core.validation.errors import ErrorCode

_BROWSER_MODULES = 'core.modules.atomic.browser'


# ---------------------------------------------------------------------------
# Fixtures: a real origin, a real browser, and a ban on fixed waits
# ---------------------------------------------------------------------------

STATIC_HTML = """
<html><body>
<button id="noop" type="button">Noop</button>
<form id="f">
  <input name="email" id="email">
  <input name="city" id="city">
  <input name="zip" id="zip">
</form>
<div id="trigger" role="combobox" aria-expanded="false" tabindex="0">Plan</div>
<ul id="list" role="listbox" hidden>
  <li role="option" id="opt-free">Free</li>
  <li role="option" id="opt-pro">Pro</li>
</ul>
<p id="picked"></p>
<script>
  const trigger = document.getElementById('trigger');
  const list = document.getElementById('list');
  trigger.addEventListener('click', () => {
    list.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
  });
  list.addEventListener('click', (e) => {
    document.getElementById('picked').textContent = e.target.textContent;
    list.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
  });
</script>
</body></html>
"""

LOGIN_FORM = """
<form id="lf">
  <input name="username" id="user">
  <input name="password" id="pass" type="password">
  <button type="submit">Sign in</button>
</form>
"""

# Navigates away 200 ms after the submit, the way a server-side login does.
LOGIN_REDIRECT_HTML = """
<html><body>%s<script>
document.getElementById('lf').addEventListener('submit', function (e) {
  e.preventDefault();
  setTimeout(function () { location.href = '/home'; }, 200);
});
</script></body></html>
""" % LOGIN_FORM

# Never reaches networkidle: a request is in flight every 100 ms, forever.
# The login itself succeeds 200 ms after the submit.
LOGIN_NEVER_IDLE_HTML = """
<html><body>%s<script>
setInterval(function () { fetch('/ping?' + Date.now()); }, 100);
document.getElementById('lf').addEventListener('submit', function (e) {
  e.preventDefault();
  setTimeout(function () {
    var d = document.createElement('div');
    d.className = 'dash';
    d.textContent = 'welcome';
    document.body.appendChild(d);
  }, 200);
});
</script></body></html>
""" % LOGIN_FORM

# Declares a new tab and then navigates the same tab instead.
GHOST_TAB_SAME_TAB_NAV_HTML = """
<html><body>
<a id="go" href="/home" target="_blank"
   onclick="event.preventDefault(); location.href = '/home';">Report</a>
</body></html>
"""

HOME_HTML = '<html><body><h1>Home</h1><a href="/">Back</a></body></html>'

DETECT_LATE_HTML = """
<html><body><p>loading</p><script>
setTimeout(function () {
  var b = document.createElement('button');
  b.textContent = 'Approve';
  document.body.appendChild(b);
}, 600);
</script></body></html>
"""

PAGES = {
    '/static': STATIC_HTML,
    '/login-redirect': LOGIN_REDIRECT_HTML,
    '/login-never-idle': LOGIN_NEVER_IDLE_HTML,
    '/ghost-tab': GHOST_TAB_SAME_TAB_NAV_HTML,
    '/home': HOME_HTML,
    '/detect-late': DETECT_LATE_HTML,
}


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = PAGES.get(self.path.split('?')[0], '<html><body>ok</body></html>').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True


@pytest.fixture(scope='module')
def site():
    server = _Server(('127.0.0.1', 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_address[1]}'
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
async def driver():
    from core.browser.driver import BrowserDriver

    browser = BrowserDriver(headless=True)
    await browser.launch(stealth=False)
    try:
        yield browser
    finally:
        await browser.close()


@pytest.fixture
def at(driver, site):
    async def _load(path):
        await driver.real_page.goto(site + path)
        return {'browser': driver}
    return _load


@pytest.fixture
def no_fixed_waits(monkeypatch):
    """Fail any fixed wait a browser module issues; record the zero-length yields.

    ``page.wait_for_timeout`` is banned outright. ``asyncio.sleep`` is banned
    for a non-zero delay when the caller is a browser module; Playwright's
    own internals and ``sleep(0)`` (a yield, not a wait) pass through.
    """
    from playwright.async_api import Frame, Page

    def _banned(self, timeout):
        raise AssertionError(f'fixed wait_for_timeout({timeout}) on the success path')

    monkeypatch.setattr(Page, 'wait_for_timeout', _banned)
    monkeypatch.setattr(Frame, 'wait_for_timeout', _banned)

    real_sleep = asyncio.sleep
    calls = []

    async def _sleep(delay, *args, **kwargs):
        caller = sys._getframe(1).f_globals.get('__name__', '')
        if caller.startswith(_BROWSER_MODULES):
            calls.append(delay)
            if delay and delay > 0:
                raise AssertionError(f'{caller} slept a fixed {delay}s')
        return await real_sleep(delay, *args, **kwargs)

    monkeypatch.setattr(asyncio, 'sleep', _sleep)
    return calls


async def _run(module_id, params, context):
    return await ModuleRegistry.get(module_id)(params, context).execute()


# ---------------------------------------------------------------------------
# (a) No fixed wait on the success path of click, select, interact and form
# ---------------------------------------------------------------------------

@pytest.mark.browser
async def test_click_select_form_and_interact_complete_without_fixed_waits(
    at, no_fixed_waits, monkeypatch,
):
    ctx = await at('/static')

    clicked = await _run('browser.click', {'click_method': 'button', 'target': 'Noop'}, ctx)
    assert clicked['status'] == 'success'

    selected = await _run(
        'browser.select',
        {'selector': '#trigger', 'select_method': 'label', 'target': 'Pro'},
        ctx,
    )
    assert selected['kind'] == 'custom'
    assert await ctx['browser'].real_page.text_content('#picked') == 'Pro'

    filled = await _run(
        'browser.form',
        {'data': {'email': 'a@b.test', 'city': 'Taipei', 'zip': '100'}},
        ctx,
    )
    assert len(filled['filled_fields']) == 3
    assert await ctx['browser'].real_page.input_value('#zip') == '100'

    import core.engine.breakpoints as breakpoints
    from core.engine.breakpoints import BreakpointStatus

    class _Answer:
        status = BreakpointStatus.APPROVED
        final_inputs = {'action': 'select', 'selector': '#trigger', 'value': '#opt-free'}

    class _Manager:
        async def create_breakpoint(self, **kwargs):
            class _Request:
                breakpoint_id = 'bp'
            return _Request()

        async def wait_for_resolution(self, breakpoint_id, check_timeout=False):
            return _Answer()

    monkeypatch.setattr(breakpoints, 'get_breakpoint_manager', lambda: _Manager())
    interacted = await _run('browser.interact', {}, ctx)
    assert interacted['action_status'] == 'selected'
    assert await ctx['browser'].real_page.text_content('#picked') == 'Free'

    assert all(delay == 0 for delay in no_fixed_waits)


@pytest.mark.browser
async def test_select_returns_when_the_dropdown_closes_not_after_a_pause(at):
    ctx = await at('/static')
    started = time.monotonic()
    await _run(
        'browser.select',
        {'selector': '#trigger', 'select_method': 'label', 'target': 'Pro'},
        ctx,
    )
    # The close is what ended the wait: the listbox is hidden and the
    # trigger collapsed by the time the module returned.
    page = ctx['browser'].real_page
    assert await page.is_hidden('#list')
    assert await page.get_attribute('#trigger', 'aria-expanded') == 'false'
    # Well under the 1 s cap a list that never closes would cost.
    assert time.monotonic() - started < 0.9


@pytest.mark.browser
async def test_form_throttle_is_opt_in_and_skips_the_last_field(at, monkeypatch):
    ctx = await at('/static')
    real_sleep = asyncio.sleep
    sleeps = []

    async def _sleep(delay, *args, **kwargs):
        if sys._getframe(1).f_globals.get('__name__', '').startswith(_BROWSER_MODULES):
            sleeps.append(delay)
        return await real_sleep(delay, *args, **kwargs)

    monkeypatch.setattr(asyncio, 'sleep', _sleep)
    data = {'email': 'a@b.test', 'city': 'Taipei', 'zip': '100'}

    await _run('browser.form', {'data': data}, ctx)
    assert [d for d in sleeps if d] == []

    await _run('browser.form', {'data': data, 'delay_between_fields_ms': 20}, ctx)
    # Between fields only: three fields, two pauses, none after the last.
    assert [d for d in sleeps if d] == [0.02, 0.02]


# ---------------------------------------------------------------------------
# (b) A click that changes nothing returns at once
# ---------------------------------------------------------------------------

@pytest.mark.browser
async def test_click_with_no_dom_change_returns_without_the_old_settle_pause(
    at, no_fixed_waits,
):
    ctx = await at('/static')
    # Warm up so the measurement is the click, not the first hint harvest.
    await _run('browser.click', {'click_method': 'button', 'target': 'Noop'}, ctx)

    started = time.monotonic()
    result = await _run('browser.click', {'click_method': 'button', 'target': 'Noop'}, ctx)
    elapsed = time.monotonic() - started

    assert result['effects'] == []
    # The old path always added a fixed 0.5 s after an in-place click.
    assert elapsed < 0.4, f'click took {elapsed:.3f}s'


# ---------------------------------------------------------------------------
# (c) Login returns on the page's answer, not on networkidle plus a pause
# ---------------------------------------------------------------------------

@pytest.mark.browser
async def test_login_returns_when_the_redirect_lands(at, no_fixed_waits):
    ctx = await at('/login-redirect')
    started = time.monotonic()
    result = await _run(
        'browser.login',
        {'username': 'someone', 'password': 'secret', 'wait_ms': 5000},
        ctx,
    )
    elapsed = time.monotonic() - started

    assert result['url_changed'] is True
    assert result['url_after'].endswith('/home')
    # The redirect fires at 200 ms; nothing else holds the module back.
    assert elapsed < 1.5, f'login took {elapsed:.3f}s'


@pytest.mark.browser
async def test_login_on_a_never_idle_page_returns_at_the_success_indicator(
    at, no_fixed_waits,
):
    ctx = await at('/login-never-idle')
    started = time.monotonic()
    result = await _run(
        'browser.login',
        {
            'username': 'someone',
            'password': 'secret',
            'success_indicator': '.dash',
            'wait_ms': 5000,
        },
        ctx,
    )
    elapsed = time.monotonic() - started

    assert result['logged_in'] is True
    # Previously networkidle ran out its 5 s and a 3 s fixed sleep followed.
    assert elapsed < 2.0, f'login took {elapsed:.3f}s'


# ---------------------------------------------------------------------------
# (d) A declared tab that navigates the same tab ends on that navigation
# ---------------------------------------------------------------------------

@pytest.mark.browser
async def test_declared_tab_that_navigates_in_place_returns_on_the_navigation(
    at, no_fixed_waits,
):
    ctx = await at('/ghost-tab')
    started = time.monotonic()
    result = await _run('browser.click', {'click_method': 'button', 'target': 'Report'}, ctx)
    elapsed = time.monotonic() - started

    assert result['opened_new_tab'] is False
    assert result['url'].endswith('/home')
    assert 'url_change' in result['effects']
    # The inference used to wait out its full 2 s for a tab that never came.
    assert elapsed < 1.5, f'click took {elapsed:.3f}s'


# ---------------------------------------------------------------------------
# (e) Detect wakes on the element appearing, not on a 0.5 s poll tick
# ---------------------------------------------------------------------------

@pytest.mark.browser
async def test_detect_returns_as_the_element_appears(at, no_fixed_waits):
    ctx = await at('/detect-late')
    started = time.monotonic()
    result = await _run(
        'browser.detect',
        {'text': 'Approve', 'role': 'button', 'timeout': 5000},
        ctx,
    )
    elapsed = time.monotonic() - started

    assert result['found'] is True
    # The element appears at 600 ms. A 500 ms poll found it at 1000 ms at
    # the earliest; the page's own mutation wakes the next pass at once.
    assert 0.55 < elapsed < 0.95, f'detect took {elapsed:.3f}s'


# ---------------------------------------------------------------------------
# Dialog: the dialog event ends the wait
# ---------------------------------------------------------------------------

@pytest.mark.browser
@pytest.mark.parametrize('action', ['accept', 'listen'])
async def test_dialog_wait_ends_on_the_dialog_event(at, no_fixed_waits, action):
    ctx = await at('/static')
    page = ctx['browser'].real_page
    # Raised by the page 200 ms from now; the module is given 10 s.
    await page.evaluate("setTimeout(() => window.__answer = confirm('Proceed?'), 200)")

    started = time.monotonic()
    result = await _run('browser.dialog', {'action': action, 'timeout': 10000}, ctx)
    elapsed = time.monotonic() - started

    assert result['type'] == 'confirm'
    assert elapsed < 1.5, f'dialog took {elapsed:.3f}s'
    if action == 'accept':
        assert await page.evaluate('window.__answer') is True
    else:
        # A listened dialog is left open; answer it so the page can close.
        page.once('dialog', lambda dialog: asyncio.ensure_future(dialog.dismiss()))


# ---------------------------------------------------------------------------
# The race helper and the duration-only wait report
# ---------------------------------------------------------------------------

async def test_first_state_returns_the_first_state_and_cancels_the_rest():
    became_ready = asyncio.Event()
    cancelled = []

    async def _never():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    async def _fails():
        raise TimeoutError('selector never matched')

    loop = asyncio.get_running_loop()
    loop.call_soon(became_ready.set)
    started = time.monotonic()
    answer = await first_state(
        {'never': _never(), 'fails': _fails(), 'ready': became_ready.wait()},
        timeout_ms=5000,
    )

    assert answer == 'ready'
    assert cancelled == [True]
    # Ended by the event, not by the 5 s bound.
    assert time.monotonic() - started < 0.5


async def test_first_state_reports_nothing_observed_at_the_bound():
    async def _fails():
        raise TimeoutError('nope')

    assert await first_state({'fails': _fails()}, timeout_ms=50) is None


def test_workflow_validation_flags_a_duration_only_wait():
    nodes = [
        {'id': 'launch', 'module_id': 'browser.launch', 'params': {}},
        {'id': 'pause', 'module_id': 'browser.wait', 'params': {'duration_ms': 1000}},
        {'id': 'ready', 'module_id': 'browser.wait', 'params': {'selector': '#ok'}},
    ]
    edges = [
        {'id': 'e1', 'source': 'launch', 'target': 'pause'},
        {'id': 'e2', 'source': 'pause', 'target': 'ready'},
    ]

    result = validate_workflow(nodes, edges)

    flagged = [w for w in result.warnings if w.code == ErrorCode.DURATION_ONLY_WAIT]
    assert [w.meta['node_id'] for w in flagged] == ['pause']
    # A warning, never a reason to refuse the workflow.
    assert not [e for e in result.errors if e.code == ErrorCode.DURATION_ONLY_WAIT]


async def test_duration_only_wait_still_sleeps_but_says_how_to_wait_on_state(caplog):
    module = ModuleRegistry.get('browser.wait')({'duration_ms': 10}, {})
    with caplog.at_level('WARNING', logger='core.modules.atomic.browser.wait'):
        result = await module.execute()

    assert result['duration_ms'] == 10
    assert 'selector' in result['advice']
    assert any('without a selector' in record.getMessage() for record in caplog.records)
