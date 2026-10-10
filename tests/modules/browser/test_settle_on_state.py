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

# The login redirects; the MFA page draws its OTP input 300 ms after load,
# the way an async-rendered prompt does. Nothing is in the DOM at load.
LOGIN_TO_MFA_HTML = """
<html><body>%s<script>
document.getElementById('lf').addEventListener('submit', function (e) {
  e.preventDefault();
  location.href = '/mfa';
});
</script></body></html>
""" % LOGIN_FORM

# Same, but through an intermediate JS hop, as SSO logins do.
LOGIN_VIA_HOP_HTML = """
<html><body>%s<script>
document.getElementById('lf').addEventListener('submit', function (e) {
  e.preventDefault();
  location.href = '/hop';
});
</script></body></html>
""" % LOGIN_FORM

HOP_HTML = """
<html><body><p>Signing you in</p><script>
setTimeout(function () { location.replace('/mfa'); }, 100);
</script></body></html>
"""

MFA_LATE_HTML = """
<html><body><p id="msg"></p><script>
window.addEventListener('load', function () {
  setTimeout(function () {
    var i = document.createElement('input');
    i.name = 'otp';
    i.autocomplete = 'one-time-code';
    document.body.appendChild(i);
  }, 300);
});
</script></body></html>
"""

# A click whose handler navigates from a timer, mutating nothing first.
DELAYED_NAV_HTML = """
<html><body>
<button id="go" type="button"
  onclick="setTimeout(function () { location.href = '/home'; }, 150)">Continue</button>
</body></html>
"""

# A click whose handler fetches and then routes in place, as an SPA does.
FETCH_THEN_ROUTE_HTML = """
<html><body>
<button id="save" type="button">Save</button>
<script>
document.getElementById('save').addEventListener('click', function () {
  fetch('/api/slow').then(function (r) { return r.text(); }).then(function () {
    history.pushState({}, '', '/routed');
    var h = document.createElement('h1');
    h.textContent = 'Saved';
    document.body.appendChild(h);
  });
});
</script></body></html>
"""

# Mutates on every animation-like tick, forever.
TICKING_HTML = """
<html><body><p id="clock">0</p><script>
var n = 0;
setInterval(function () { document.getElementById('clock').textContent = String(++n); }, 16);
</script></body></html>
"""

# Clients that captured fetch or XHR at load, as ky, ofetch and Apollo do. An
# in-page wrapper installed at click time never sees their requests.
CAPTURED_CLIENT_HTML = """
<html><body>
<button id="fetch" type="button">Load via fetch</button>
<button id="xhr" type="button">Load via XHR</button>
<script>
const capturedFetch = window.fetch.bind(window);
const capturedSend = XMLHttpRequest.prototype.send;
function render(label) {
  const b = document.createElement('button');
  b.type = 'button';
  b.textContent = label;
  document.body.appendChild(b);
}
document.getElementById('fetch').addEventListener('click', function () {
  capturedFetch('/api/slow3').then(function (r) { return r.text(); })
    .then(function () { render('Next via fetch'); });
});
document.getElementById('xhr').addEventListener('click', function () {
  const x = new XMLHttpRequest();
  x.open('GET', '/api/slow3');
  x.onload = function () { render('Next via XHR'); };
  capturedSend.call(x);
});
</script></body></html>
"""

# An SPA login: the form is hidden the moment it posts, the API answers after
# 900 ms -- longer than any DOM-quiet window -- and only then is the route
# pushed. A password field going away is not the answer here.
SPA_LOGIN_HTML = """
<html><body>%s<p id="busy" hidden>Signing in</p><script>
document.getElementById('lf').addEventListener('submit', function (e) {
  e.preventDefault();
  document.getElementById('lf').style.display = 'none';
  document.getElementById('busy').hidden = false;
  fetch('/api/login').then(function (r) { return r.text(); }).then(function () {
    history.pushState({}, '', '/dashboard');
    document.body.innerHTML = '<h1>Dashboard</h1>';
  });
});
</script></body></html>
""" % LOGIN_FORM

# A rejected SPA login whose message matches no known error selector.
SPA_LOGIN_REJECTED_HTML = """
<html><body>%s<div id="note"></div><script>
document.getElementById('lf').addEventListener('submit', function (e) {
  e.preventDefault();
  fetch('/api/slow3').then(function (r) { return r.text(); }).then(function () {
    document.getElementById('note').textContent = 'Those details did not match';
  });
});
</script></body></html>
""" % LOGIN_FORM

# A login that navigates while its own request is still in flight; the
# replaced document aborts it, and the abort must not hold the settle.
LOGIN_ABORTS_REQUEST_HTML = """
<html><body>%s<script>
document.getElementById('lf').addEventListener('submit', function (e) {
  e.preventDefault();
  fetch('/api/hang').catch(function () {});
  setTimeout(function () { location.href = '/home'; }, 50);
});
</script></body></html>
""" % LOGIN_FORM

# A custom dropdown that confirms the pick only by showing it on the trigger:
# the list stays visible and no ARIA state changes.
SELECT_SHOWS_CHOICE_HTML = """
<html><body>
<div id="trigger" tabindex="0">Choose</div>
<ul id="list">
  <li role="option">Basic</li>
  <li role="option">Team</li>
</ul>
<script>
document.getElementById('list').addEventListener('click', function (e) {
  document.getElementById('trigger').textContent = e.target.textContent;
});
</script></body></html>
"""

# A link that opens a new tab, so the click never settles the opener.
NEW_TAB_HTML = """
<html><body><a id="pop" href="/home" target="_blank">Open help</a></body></html>
"""

PAGES = {
    '/static': STATIC_HTML,
    '/captured-client': CAPTURED_CLIENT_HTML,
    '/spa-login': SPA_LOGIN_HTML,
    '/spa-login-rejected': SPA_LOGIN_REJECTED_HTML,
    '/login-aborts': LOGIN_ABORTS_REQUEST_HTML,
    '/select-shows-choice': SELECT_SHOWS_CHOICE_HTML,
    '/new-tab': NEW_TAB_HTML,
    '/login-redirect': LOGIN_REDIRECT_HTML,
    '/login-never-idle': LOGIN_NEVER_IDLE_HTML,
    '/ghost-tab': GHOST_TAB_SAME_TAB_NAV_HTML,
    '/home': HOME_HTML,
    '/detect-late': DETECT_LATE_HTML,
    '/login-mfa': LOGIN_TO_MFA_HTML,
    '/login-hop': LOGIN_VIA_HOP_HTML,
    '/hop': HOP_HTML,
    '/mfa': MFA_LATE_HTML,
    '/delayed-nav': DELAYED_NAV_HTML,
    '/fetch-then-route': FETCH_THEN_ROUTE_HTML,
    '/ticking': TICKING_HTML,
}

# Answered after this delay, so a click that fetches is still waiting on it.
SLOW_PATHS = {'/api/slow': 0.2, '/api/slow3': 0.3, '/api/login': 0.9, '/api/hang': 3.0}


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        delay = SLOW_PATHS.get(self.path.split('?')[0])
        if delay:
            time.sleep(delay)
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
async def test_select_returns_when_the_trigger_shows_the_choice(at, no_fixed_waits):
    ctx = await at('/select-shows-choice')
    started = time.monotonic()
    await _run(
        'browser.select',
        {'selector': '#trigger', 'select_method': 'label', 'target': 'Team'},
        ctx,
    )
    elapsed = time.monotonic() - started

    page = ctx['browser'].real_page
    assert await page.text_content('#trigger') == 'Team'
    # The list never closes; the trigger showing the pick ended the wait,
    # not the 1 s cap.
    assert elapsed < 0.8, f'select took {elapsed:.3f}s'


async def test_request_tracker_goes_idle_on_the_finishing_event_not_a_timer():
    from core.modules.atomic.browser._settle import RequestTracker

    class _Request:
        def __init__(self, resource_type='fetch', navigation=False, frame='main'):
            self.resource_type = resource_type
            self._navigation = navigation
            self.frame = frame

        def is_navigation_request(self):
            return self._navigation

    class _Page:
        def __init__(self):
            self.listeners = {}

        def on(self, name, fn):
            self.listeners.setdefault(name, []).append(fn)

        def remove_listener(self, name, fn):
            self.listeners[name].remove(fn)

        def emit(self, name, request):
            for fn in list(self.listeners.get(name, [])):
                fn(request)

    page = _Page()
    tracker = RequestTracker(page, frame_filter=lambda frame: frame == 'main').attach()
    api, follow_up = _Request(), _Request('xhr')
    for ignored in (
        _Request('image'), _Request('document', navigation=True), _Request(frame='ad'),
    ):
        page.emit('request', ignored)
    assert not tracker.busy and tracker.seen == 0

    page.emit('request', api)
    page.emit('request', follow_up)
    waiter = asyncio.ensure_future(tracker.wait_idle(60_000))
    await asyncio.sleep(0)
    page.emit('requestfinished', api)
    await asyncio.sleep(0)
    assert not waiter.done()  # one request is still the action's work
    page.emit('requestfailed', follow_up)
    # Resolved by the event itself: no clock advanced in between.
    assert await asyncio.wait_for(waiter, timeout=0.05) is True
    assert tracker.seen == 2 and not tracker.busy

    tracker.detach()
    assert all(not fns for fns in page.listeners.values())


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
    at, no_fixed_waits, monkeypatch,
):
    import core.modules.atomic.browser.click as click_module

    answers = []
    real_settle_dom = click_module.settle_dom

    async def _spy(page, **kwargs):
        answers.append(await real_settle_dom(page, **kwargs))
        return answers[-1]

    monkeypatch.setattr(click_module, 'settle_dom', _spy)
    ctx = await at('/static')
    # Warm up so the measurement is the click, not the first hint harvest.
    await _run('browser.click', {'click_method': 'button', 'target': 'Noop'}, ctx)

    started = time.monotonic()
    result = await _run('browser.click', {'click_method': 'button', 'target': 'Noop'}, ctx)
    elapsed = time.monotonic() - started

    assert result['effects'] == []
    # The page itself said nothing changed; that answer is what ended it.
    assert answers == ['unchanged', 'unchanged']
    # The old path added a fixed 0.5 s (0.3 s after a navigation). The whole
    # click, hint harvests included, fits well inside even the shorter one.
    assert elapsed < 0.25, f'click took {elapsed:.3f}s'


@pytest.mark.browser
async def test_click_waits_for_the_navigation_its_own_timer_starts(at, no_fixed_waits):
    ctx = await at('/delayed-nav')
    result = await _run(
        'browser.click', {'click_method': 'button', 'target': 'Continue'}, ctx,
    )

    # The handler only scheduled the navigation; the pending timer was the
    # state that kept the click open, and the navigation it made is reported.
    assert result['url'].endswith('/home')
    assert 'url_change' in result['effects']
    assert any(link.get('text') == 'Back' for link in result.get('links', []))


@pytest.mark.browser
async def test_click_waits_for_the_request_it_started_and_the_route_after_it(
    at, no_fixed_waits,
):
    ctx = await at('/fetch-then-route')
    started = time.monotonic()
    result = await _run('browser.click', {'click_method': 'button', 'target': 'Save'}, ctx)
    elapsed = time.monotonic() - started

    assert result['url'].endswith('/routed')
    assert 'url_change' in result['effects']
    assert 'Saved' in result.get('_page_hint', '')
    # The response lands at 200 ms; the 1 s settle cap was not what ended it.
    assert elapsed < 0.9, f'click took {elapsed:.3f}s'
    # The page's own functions are back once the click has settled.
    page = ctx['browser'].real_page
    assert await page.evaluate(
        "() => window.setTimeout.toString().includes('[native code]')"
        " && window.fetch.toString().includes('[native code]')"
        " && XMLHttpRequest.prototype.send.toString().includes('[native code]')"
    )


_NATIVE_PROBE = """() => ({
  fetch: window.fetch.toString().includes('[native code]'),
  send: XMLHttpRequest.prototype.send.toString().includes('[native code]'),
})"""


@pytest.mark.browser
@pytest.mark.parametrize('label', ['Load via fetch', 'Load via XHR'])
async def test_click_waits_for_a_request_from_a_client_that_captured_it_at_load(
    at, no_fixed_waits, monkeypatch, label,
):
    import core.modules.atomic.browser.click as click_module

    ctx = await at('/captured-client')
    page = ctx['browser'].real_page
    natives_during_click = []
    real_settle_dom = click_module.settle_dom

    async def _spy(target, **kwargs):
        # Requests are read from network events; nothing in the page is
        # replaced to see them, so fingerprinting scripts see natives.
        natives_during_click.append(await page.evaluate(_NATIVE_PROBE))
        return await real_settle_dom(target, **kwargs)

    monkeypatch.setattr(click_module, 'settle_dom', _spy)
    started = time.monotonic()
    result = await _run('browser.click', {'click_method': 'button', 'target': label}, ctx)
    elapsed = time.monotonic() - started

    rendered = label.replace('Load', 'Next')
    assert 'page_content_change' in result['effects']
    assert any(b.get('text') == rendered for b in result.get('buttons', []))
    assert natives_during_click == [{'fetch': True, 'send': True}]
    # The response lands at 300 ms; the settle ended on it, not at a cap.
    assert 0.3 <= elapsed < 0.95, f'click took {elapsed:.3f}s'


@pytest.mark.browser
async def test_click_that_adopts_a_new_tab_leaves_no_watch_on_the_opener(
    at, no_fixed_waits,
):
    ctx = await at('/new-tab')
    opener = ctx['browser'].real_page
    result = await _run('browser.click', {'click_method': 'button', 'target': 'Open help'}, ctx)

    assert result['opened_new_tab'] is True
    assert await opener.evaluate(
        "() => window.__flytoSettle === undefined"
        " && window.setTimeout.toString().includes('[native code]')"
    )


@pytest.mark.browser
async def test_click_that_raises_leaves_no_watch_on_the_page(at, no_fixed_waits):
    ctx = await at('/static')
    with pytest.raises(RuntimeError):
        await _run(
            'browser.click',
            {
                'click_method': 'button', 'target': 'Noop',
                'expected_outcome': 'url_change', 'verification_timeout_ms': 300,
            },
            ctx,
        )

    page = ctx['browser'].real_page
    assert await page.evaluate(
        "() => window.__flytoSettle === undefined"
        " && window.setTimeout.toString().includes('[native code]')"
    )


async def test_resolver_waits_again_when_the_match_rerenders_before_it_is_counted():
    from core.modules.atomic.browser.click import BrowserClickModule

    # The union matches, then the element re-renders: the first preference
    # pass counts nothing, the next union wait sees the new node.
    state = {'union_waits': 0, 'rendered': False}

    class _Locator:
        def __init__(self, exact):
            self.exact = exact

        def filter(self, **_):
            return self

        def or_(self, _other):
            return _Union()

        async def count(self):
            return 1 if state['rendered'] and self.exact else 0

        @property
        def first(self):
            return self

    class _Union(_Locator):
        def __init__(self):
            super().__init__(True)

        async def wait_for(self, **_):
            state['union_waits'] += 1
            # Detached during the first pass, attached again by the second.
            state['rendered'] = state['union_waits'] > 1

    class _Page:
        def get_by_role(self, role, name, exact, include_hidden):
            return _Locator(exact)

    module = BrowserClickModule.__new__(BrowserClickModule)
    module.target = 'Save'
    module.force = False
    module.timeout = 2000

    locator, selector = await module._resolve_button_or_link(_Page())

    assert state['union_waits'] == 2
    assert selector == "role=button[name='Save']"


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
async def test_login_waits_for_the_spa_api_behind_a_hidden_form(at, no_fixed_waits):
    ctx = await at('/spa-login')
    started = time.monotonic()
    result = await _run(
        'browser.login',
        {'username': 'someone', 'password': 'secret', 'wait_ms': 5000},
        ctx,
    )
    elapsed = time.monotonic() - started

    # The password field vanished at once; the API answering and the route
    # it pushed are what the module read.
    assert result['logged_in'] is True
    assert result['url_after'].endswith('/dashboard')
    # 900 ms of API plus one 500 ms quiet window, far short of wait_ms.
    assert 0.9 <= elapsed < 2.5, f'login took {elapsed:.3f}s'


@pytest.mark.browser
async def test_login_rejected_with_unknown_wording_returns_when_its_request_settles(
    at, no_fixed_waits,
):
    ctx = await at('/spa-login-rejected')
    started = time.monotonic()
    result = await _run(
        'browser.login',
        {'username': 'someone', 'password': 'wrong', 'wait_ms': 5000},
        ctx,
    )
    elapsed = time.monotonic() - started

    assert result['logged_in'] is False
    assert result['url_changed'] is False
    # The request finished at 300 ms and the page went quiet; wait_ms (5 s)
    # was not what ended it.
    assert elapsed < 2.0, f'login took {elapsed:.3f}s'


@pytest.mark.browser
async def test_login_settle_is_not_held_by_a_request_the_navigation_aborted(
    at, no_fixed_waits,
):
    ctx = await at('/login-aborts')
    started = time.monotonic()
    result = await _run(
        'browser.login',
        {'username': 'someone', 'password': 'secret', 'wait_ms': 5000},
        ctx,
    )
    elapsed = time.monotonic() - started

    assert result['url_after'].endswith('/home')
    # /api/hang answers after 3 s; the navigation aborted it.
    assert elapsed < 2.0, f'login took {elapsed:.3f}s'


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


@pytest.mark.browser
@pytest.mark.parametrize('path', ['/login-mfa', '/login-hop'])
async def test_login_sees_an_mfa_prompt_drawn_after_the_redirect_loads(
    at, no_fixed_waits, monkeypatch, path,
):
    import core.engine.breakpoints as breakpoints
    from core.engine.breakpoints import BreakpointStatus

    raised = []

    class _Manager:
        async def create_breakpoint(self, **kwargs):
            raised.append(kwargs['context_snapshot']['url'])

            class _Request:
                breakpoint_id = 'bp'
            return _Request()

        async def wait_for_resolution(self, breakpoint_id, check_timeout=False):
            class _Answer:
                status = BreakpointStatus.REJECTED
            return _Answer()

    monkeypatch.setattr(breakpoints, 'get_breakpoint_manager', lambda: _Manager())
    ctx = await at(path)
    started = time.monotonic()
    result = await _run(
        'browser.login',
        {'username': 'someone', 'password': 'secret', 'wait_ms': 5000},
        ctx,
    )
    elapsed = time.monotonic() - started

    # The prompt is rendered after the MFA document loaded (and, for the hop,
    # after a second JS navigation). It must still reach the human approval.
    assert result['mfa_detected'] is True
    assert result['logged_in'] is False
    assert raised and raised[0].endswith('/mfa')
    # Ended by the prompt appearing, not by the 5 s cap.
    assert elapsed < 2.5, f'login took {elapsed:.3f}s'


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


@pytest.mark.browser
async def test_detect_on_a_constantly_mutating_page_coalesces_its_wakes(
    at, no_fixed_waits, monkeypatch,
):
    from core.modules.atomic.browser.detect import BrowserDetectModule

    passes = []
    real_run = BrowserDetectModule._run_detection

    async def _counted(self, *args, **kwargs):
        passes.append(time.monotonic())
        return await real_run(self, *args, **kwargs)

    monkeypatch.setattr(BrowserDetectModule, '_run_detection', _counted)
    ctx = await at('/ticking')
    result = await _run(
        'browser.detect',
        {'text': 'Nowhere to be found', 'role': 'button', 'timeout': 1500},
        ctx,
    )

    assert result['found'] is False
    # The clock mutates every 16 ms (~90 times here). Wakes are batched to at
    # most one per 250 ms, so the pass count stays near timeout / 250.
    assert len(passes) <= 10, f'{len(passes)} detection passes'


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
