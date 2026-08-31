"""Focused contract tests for semantic browser.click resolution."""

import time
from unittest.mock import AsyncMock

import pytest

from core.browser.driver import BrowserDriver
from core.engine.step_executor.executor import StepExecutor
from core.engine.trace import TraceCollector
from core.engine.variable_resolver import VariableResolver
from core.engine.workflow.engine import WorkflowEngine
from core.mcp_handler import _build_recipe_result
from core.modules.atomic.browser.click import BrowserClickModule
from core.modules.registry import ModuleRegistry


class _Locator:
    """A match set of ``count`` visible nodes plus ``hidden`` invisible ones."""

    def __init__(self, count=0, hidden=0, attributes=None, click_hook=None):
        self.visible_count = count
        self.hidden_count = hidden
        self._attributes = attributes or {}
        self.click = AsyncMock(side_effect=click_hook)
        self.visible_filter_calls = []

    def filter(self, **kwargs):
        self.visible_filter_calls.append(kwargs)
        return _VisibleOnly(self)

    async def count(self):
        return self.visible_count + self.hidden_count

    async def get_attribute(self, name):
        return self._attributes.get(name)

    @property
    def first(self):
        return self


class _VisibleOnly:
    """What ``locator.filter(visible=True)`` narrows a match set down to."""

    def __init__(self, locator):
        self._locator = locator

    async def count(self):
        return self._locator.visible_count

    @property
    def first(self):
        return self._locator


class _Page:
    def __init__(self, matches, url='https://example.test/', hint='source page'):
        self.matches = matches
        self.calls = []
        self.url = url
        self.hint = hint
        self.rect = [0, 0]
        self.wait_for_load_state = AsyncMock()
        self.wait_for_function = AsyncMock()
        self.wait_for_timeout = AsyncMock()

    def get_by_role(self, role, **kwargs):
        self.calls.append((role, kwargs))
        return self.matches.get((role, kwargs['exact']), _Locator())

    def locator(self, selector):
        return self.matches.get(selector, _Locator())


class _Context:
    def __init__(self, page):
        self.pages = [page]
        self.listeners = {}

    def on(self, event, callback):
        self.listeners.setdefault(event, []).append(callback)

    def remove_listener(self, event, callback):
        self.listeners[event].remove(callback)

    def open_page(self, page):
        self.pages.append(page)
        for callback in list(self.listeners.get('page', [])):
            callback(page)


class _Browser:
    def __init__(self, page, context):
        self._page = page
        self._context = context
        self._snapshot_since_nav = False
        self.invalidate_hints = AsyncMock()
        self.wait_calls = []

    @property
    def page(self):
        return self._page

    async def wait(self, selector, state='visible', timeout_ms=0):
        """Mirror BrowserDriver.wait instead of stubbing it.

        A stubbed wait accepts every selector contract, which would leave the
        whole verification path green even when its body is deleted.
        """
        self.wait_calls.append((selector, state))
        visible = await self._page.locator(selector).filter(visible=True).count()
        if (visible > 0) is not (state == 'visible'):
            raise TimeoutError(f'{selector!r} never became {state}')

    async def get_hints(self, force=False):
        # 'rect' rides along so effect reporting has geometry to ignore.
        return {'text': self._page.hint, 'buttons': [{'name': 'Go', 'rect': self._page.rect}]}


def _wire(params, *, url='https://example.test/form', hint='form', role='button',
          locator=None, matches=None):
    """Build a click module over a fake page whose ``role`` match is ``locator``."""
    page = _Page(dict(matches or {}), url=url, hint=hint)
    page.matches[(role, True)] = locator if locator is not None else _Locator(count=1)
    browser = _Browser(page, _Context(page))
    module = BrowserClickModule(
        {'click_method': 'button', 'target': 'Submit', **params},
        {'browser': browser},
    )
    return module, browser, page, page.matches[(role, True)]


@pytest.mark.asyncio
async def test_button_mode_resolves_visible_link_by_accessible_name():
    link = _Locator(count=1)
    page = _Page({('link', True): link})
    module = BrowserClickModule(
        {'click_method': 'button', 'target': 'kintone'},
        {},
    )

    resolved, selector = await module._resolve_button_or_link(page)

    assert resolved is link
    assert selector == "role=link[name='kintone']"
    assert link.visible_filter_calls == [{'visible': True}]
    assert page.calls[0][0] == 'button'
    assert page.calls[1][0] == 'link'


@pytest.mark.asyncio
async def test_button_mode_honours_the_configured_timeout():
    # The published key and the key __init__ reads must be the same one, or a
    # caller-set timeout is accepted by the editor and then discarded.
    assert 'timeout_ms' in ModuleRegistry.get_metadata('browser.click')['params_schema']

    module, _browser, page, _locator = _wire(
        {'target': 'Missing', 'timeout_ms': 5},
        locator=_Locator(),
    )

    started = time.monotonic()
    with pytest.raises(RuntimeError, match='within 5ms'):
        await module._resolve_button_or_link(page)

    # The deadline must be the configured one, not just the quoted one.
    assert time.monotonic() - started < 1


@pytest.mark.asyncio
@pytest.mark.parametrize('attributes,expected', [
    ({'target': '_blank'}, True),
    ({'formtarget': '_BLANK'}, True),
    ({'onclick': "window.open('/report')"}, True),
    ({'target': '_self', 'onclick': 'form.submit()'}, False),
])
async def test_new_tab_inference_reads_only_explicit_tab_markup(attributes, expected):
    module, _browser, _page, _locator = _wire({})

    assert await module._expects_new_page(_Locator(attributes=attributes)) is expected


@pytest.mark.asyncio
async def test_click_adopts_new_tab_for_following_steps_and_preview():
    popup = _Page({}, url='https://example.test/attendance', hint='attendance')

    async def open_popup(**_kwargs):
        browser._context.open_page(popup)

    module, browser, source, _link = _wire(
        {'target': 'Attendance'},
        url='https://example.test/portal',
        hint='portal',
        role='link',
        locator=_Locator(count=1, attributes={'target': '_blank'}, click_hook=open_popup),
    )

    result = await module.execute()

    # Adoption: the following browser.* step must operate on the popup, and
    # the reported index must be the popup's, not the opener's.
    assert browser.page is popup
    assert browser._context.pages == [source, popup]
    assert browser._context.listeners['page'] == []
    assert result['opened_new_tab'] is True
    assert result['effect_observed'] is True
    # The opener never navigated and its content never changed: an adopted
    # popup is reported as 'new_tab' alone, never as an effect on the clicked
    # document.  ``popup``'s hints differ from the opener's by construction.
    assert result['effects'] == ['new_tab']
    assert result['verification_status'] == 'inferred'
    assert result['expected_outcome'] == 'new_tab'
    assert result['tab_count'] == 2
    assert result['current_index'] == 1
    assert result['url'] == 'https://example.test/attendance'
    assert result['_page_hint'] == 'attendance'


@pytest.mark.asyncio
async def test_auto_records_an_unfulfilled_tab_inference_instead_of_failing():
    link = _Locator(count=1, attributes={'target': '_blank'})
    module, browser, _page, _locator = _wire(
        {'target': 'Attendance', 'verification_timeout_ms': 60000},
        url='https://example.test/portal',
        hint='portal',
        role='link',
        locator=link,
    )

    started = time.monotonic()
    result = await module.execute()
    elapsed = time.monotonic() - started

    # 'auto' infers a tab from markup and records that it never arrived; only
    # an explicit contract may fail the click.
    assert result['status'] == 'success'
    assert result['expected_outcome'] == 'new_tab'
    assert result['verification_status'] == 'unverified'
    assert result['opened_new_tab'] is False
    assert browser._context.listeners['page'] == []
    link.click.assert_awaited_once()
    # An inference gets a short best-effort re-scan, never the caller's budget.
    assert elapsed < 5


@pytest.mark.asyncio
async def test_explicit_new_tab_contract_fails_when_no_tab_opens():
    module, browser, _page, _locator = _wire(
        {
            'target': 'Attendance',
            'expected_outcome': 'new_tab',
            'verification_timeout_ms': 5,
        },
        role='link',
        locator=_Locator(count=1, attributes={'target': '_blank'}),
    )

    with pytest.raises(RuntimeError, match='expected a new tab'):
        await module.execute()

    assert browser._context.listeners['page'] == []


@pytest.mark.asyncio
async def test_click_can_require_a_new_tab_for_script_driven_actions():
    popup = _Page({}, url='https://example.test/attendance', hint='attendance')

    async def open_popup(**_kwargs):
        browser._context.open_page(popup)

    module, browser, _page, _locator = _wire(
        {'target': 'Attendance', 'expected_outcome': 'new_tab'},
        role='link',
        locator=_Locator(count=1, click_hook=open_popup),
    )

    result = await module.execute()

    assert result['verification_status'] == 'verified'
    assert result['expected_outcome'] == 'new_tab'
    assert result['opened_new_tab'] is True


@pytest.mark.asyncio
async def test_click_reports_no_outcome_and_ignores_pure_geometry_movement():
    async def shift_layout(**_kwargs):
        page.rect = [40, 90]

    module, _browser, page, _button = _wire(
        {'target': 'Toggle'},
        hint='unchanged',
        locator=_Locator(count=1, click_hook=shift_layout),
    )

    result = await module.execute()

    assert result['status'] == 'success'
    assert result['verification_status'] == 'not_requested'
    assert result['expected_outcome'] == 'auto'
    # Responsive layout may move an unchanged control; that is not evidence.
    assert result['effects'] == []
    assert result['effect_observed'] is False


@pytest.mark.asyncio
async def test_click_only_confirms_dispatch_without_claiming_a_visible_effect():
    module, _browser, _page, button = _wire(
        {'expected_outcome': 'click_only'},
        hint='unchanged',
    )

    result = await module.execute()

    assert result['verification_status'] == 'dispatched'
    assert result['effect_observed'] is False
    button.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_click_can_verify_a_same_tab_url_change():
    async def navigate(**_kwargs):
        page.url = 'https://example.test/complete'
        page.hint = 'complete'

    module, _browser, page, _button = _wire(
        {'expected_outcome': 'url_change'},
        locator=_Locator(count=1, click_hook=navigate),
    )

    result = await module.execute()

    assert result['verification_status'] == 'verified'
    assert result['effects'] == ['url_change', 'page_content_change']
    assert result['pre_url'] == 'https://example.test/form'
    assert result['url'] == 'https://example.test/complete'


@pytest.mark.asyncio
async def test_url_change_is_judged_on_the_clicked_page_not_an_adopted_popup():
    popup = _Page({}, url='https://example.test/popup', hint='popup')

    async def open_popup(**_kwargs):
        browser._context.open_page(popup)

    module, browser, _page, _locator = _wire(
        {
            'target': 'Attendance',
            'expected_outcome': 'url_change',
            'verification_timeout_ms': 5,
        },
        url='https://example.test/opener',
        role='link',
        locator=_Locator(count=1, attributes={'target': '_blank'}, click_hook=open_popup),
    )

    with pytest.raises(RuntimeError) as failure:
        await module.execute()

    # The popup's URL must not be able to satisfy the opener's contract.
    assert 'expected the page URL to change' in str(failure.value)
    assert 'https://example.test/opener' in str(failure.value)


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome,value,matches', [
    ('selector_visible', '#result', {'#result': _Locator(count=1)}),
    # A display:none duplicate is already hidden, so the state is satisfied.
    ('selector_hidden', '#banner', {'#banner': _Locator(hidden=1)}),
    ('url_contains', 'form', {}),
])
async def test_outcome_already_true_is_rejected_but_the_click_still_fires(outcome, value, matches):
    module, browser, _page, button = _wire(
        {'expected_outcome': outcome, 'outcome_value': value},
        matches=matches,
    )

    with pytest.raises(RuntimeError, match='already satisfied before the click'):
        await module.execute()

    # A verdict on the evidence, not a refusal to act.
    button.click.assert_awaited_once()
    assert browser.wait_calls == []


@pytest.mark.asyncio
async def test_selector_outcome_fails_when_the_element_never_appears():
    module, browser, _page, button = _wire(
        {
            'expected_outcome': 'selector_visible',
            'outcome_value': '#result',
            'verification_timeout_ms': 5,
        },
    )

    with pytest.raises(RuntimeError, match="expected '#result' to become visible within 5ms"):
        await module.execute()

    button.click.assert_awaited_once()
    assert browser.wait_calls == [('#result', 'visible')]


@pytest.mark.asyncio
async def test_selector_outcome_is_verified_once_the_element_appears():
    revealed = _Locator(count=0)

    async def reveal(**_kwargs):
        revealed.visible_count = 1

    module, browser, _page, _button = _wire(
        {'expected_outcome': 'selector_visible', 'outcome_value': '#result'},
        matches={'#result': revealed},
        locator=_Locator(count=1, click_hook=reveal),
    )

    result = await module.execute()

    assert result['verification_status'] == 'verified'
    assert result['effects'] == ['selector_visible']
    assert browser.wait_calls == [('#result', 'visible')]


def test_outcome_contract_validation_rejects_ambiguous_values():
    with pytest.raises(ValueError, match='Expected value must be a string'):
        BrowserClickModule(
            {
                'click_method': 'button',
                'target': 'Submit',
                'expected_outcome': 'url_contains',
                'outcome_value': 123,
            },
            {},
        )

    with pytest.raises(ValueError, match='Outcome timeout must be a number'):
        BrowserClickModule(
            {
                'click_method': 'button',
                'target': 'Submit',
                'verification_timeout_ms': True,
            },
            {},
        )


@pytest.mark.browser
@pytest.mark.asyncio
async def test_real_browser_enforces_outcome_contracts():
    driver = BrowserDriver(headless=True)
    await driver.launch()
    try:
        await driver.page.set_content(
            '<button onclick="document.querySelector(\'#result\').hidden=false">'
            'Submit</button><p id="result" hidden>Saved</p>'
        )
        result = await BrowserClickModule(
            {
                'click_method': 'button',
                'target': 'Submit',
                'expected_outcome': 'selector_visible',
                'outcome_value': '#result',
                'verification_timeout_ms': 500,
            },
            {'browser': driver},
        ).execute()

        assert result['verification_status'] == 'verified'
        assert 'selector_visible' in result['effects']

        await driver.page.set_content(
            '<a href="about:blank" target="_blank" '
            'onclick="event.preventDefault()">Attendance</a>'
        )
        inferred = await BrowserClickModule(
            {
                'click_method': 'button',
                'target': 'Attendance',
                'timeout_ms': 500,
            },
            {'browser': driver},
        ).execute()

        assert inferred['status'] == 'success'
        assert inferred['expected_outcome'] == 'new_tab'
        assert inferred['verification_status'] == 'unverified'

        with pytest.raises(RuntimeError, match='expected a new tab'):
            await BrowserClickModule(
                {
                    'click_method': 'button',
                    'target': 'Attendance',
                    'expected_outcome': 'new_tab',
                    'verification_timeout_ms': 100,
                },
                {'browser': driver},
            ).execute()
    finally:
        await driver.close()


# ---------------------------------------------------------------------------
# The record a consumer of the run actually reads
# ---------------------------------------------------------------------------
#
# A click that reports success while its own payload says the outcome it
# expected was never observed is only honest if something downstream reads
# that payload. These tests pin the signal at the consumer: the execution
# trace the REST /workflows/execute response and the MCP run_recipe response
# are built from.


def _click_step():
    """A fresh single-step config; the engine mutates the dict it is given."""
    return {
        'id': 'attendance',
        'module': 'browser.click',
        'params': {
            'click_method': 'button',
            'target': 'Attendance',
            'timeout_ms': 2000,
        },
    }


async def _run_click_through_step_executor(browser):
    """Drive the real browser.click through the real StepExecutor.

    Returns the finished ExecutionTrace plus the workflow context, so a test
    can compare what the module returned against what the run recorded.
    """
    collector = TraceCollector('wf-click', 'Attendance click', {})
    collector.start()
    context = {'browser': browser}
    executor = StepExecutor(
        workflow_id='wf-click',
        workflow_name='Attendance click',
        total_steps=1,
    )
    await executor.execute_step(
        step_config=_click_step(),
        step_index=0,
        context=context,
        resolver=VariableResolver({}, context),
        trace_collector=collector,
    )
    return collector.complete({}), context


@pytest.mark.asyncio
async def test_step_record_separates_an_unconfirmed_tab_from_a_real_one():
    """An inferred-but-absent tab must not look like a verified success."""
    # (a) The symptom: the markup promises a tab, the click opens none.
    stuck_page = _Page({}, url='https://example.test/portal', hint='portal')
    stuck_page.matches[('link', True)] = _Locator(
        count=1, attributes={'target': '_blank'},
    )
    unconfirmed, stuck_context = await _run_click_through_step_executor(
        _Browser(stuck_page, _Context(stuck_page)),
    )

    # (b) The control: identical markup, and the tab really opens.
    popup = _Page({}, url='https://example.test/attendance', hint='attendance')
    opener_page = _Page({}, url='https://example.test/portal', hint='portal')
    opener_context = _Context(opener_page)

    async def open_popup(**_kwargs):
        opener_context.open_page(popup)

    opener_page.matches[('link', True)] = _Locator(
        count=1, attributes={'target': '_blank'}, click_hook=open_popup,
    )
    confirmed, opened_context = await _run_click_through_step_executor(
        _Browser(opener_page, opener_context),
    )

    # The module result is untouched in both runs — still a success, still
    # stored under the step id for downstream steps, still no raise.
    assert stuck_context['attendance']['status'] == 'success'
    assert opened_context['attendance']['status'] == 'success'
    assert stuck_context['attendance']['opened_new_tab'] is False
    assert opened_context['attendance']['opened_new_tab'] is True

    unconfirmed_run = unconfirmed.to_dict()
    confirmed_run = confirmed.to_dict()
    unconfirmed_step = unconfirmed_run['steps'][0]
    confirmed_step = confirmed_run['steps'][0]

    # At the consumer the two runs are no longer the same record.
    assert confirmed_step['status'] == 'success'
    assert 'error' not in confirmed_step
    assert unconfirmed_step['status'] == 'partial'
    assert unconfirmed_step['statusLegacy'] == 'partial'
    assert unconfirmed_step['error']['code'] == 'UNVERIFIED_OUTCOME'
    assert "never observed 'new_tab'" in unconfirmed_step['error']['message']

    # Recorded honestly is not recorded as failed: the run still succeeded.
    assert unconfirmed_run['failedSteps'] == 0
    assert unconfirmed_run['completedSteps'] == 0
    assert confirmed_run['completedSteps'] == 1

    # The MCP run_recipe payload is built from these step statuses.
    unconfirmed_reply = _build_recipe_result('portal', unconfirmed)
    confirmed_reply = _build_recipe_result('portal', confirmed)
    assert unconfirmed_reply['ok'] is True
    assert unconfirmed_reply['steps'][0]['status'] == 'partial'
    assert unconfirmed_reply['passedSteps'] == 0
    assert confirmed_reply['steps'][0]['status'] == 'success'
    assert confirmed_reply['passedSteps'] == 1


@pytest.mark.asyncio
async def test_step_record_stays_a_clean_success_when_nothing_is_inferred():
    """Only an unconfirmed claim is downgraded; an ordinary click is not.

    Without this, every click on a button that declares no tab would start
    reporting 'partial' and the status would stop meaning anything.
    """
    page = _Page({}, url='https://example.test/form', hint='form')
    page.matches[('button', True)] = _Locator(count=1)

    trace, context = await _run_click_through_step_executor(
        _Browser(page, _Context(page)),
    )

    assert context['attendance']['verification_status'] == 'not_requested'
    assert trace.to_dict()['steps'][0]['status'] == 'success'
    assert 'error' not in trace.to_dict()['steps'][0]


async def _run_click_through_workflow_engine(driver):
    """Run the click as a one-step workflow, the way a recipe run does."""
    engine = WorkflowEngine(
        {
            'id': 'attendance-click',
            'name': 'Attendance click',
            'evolution': False,
            'steps': [_click_step()],
        },
        # The engine auto-closes a headless browser it owns; this run borrows
        # the caller's session the way a keep-alive recipe does.
        initial_context={'browser': driver, 'keep_browser_alive': True},
        enable_trace=True,
    )
    await engine.execute()
    return engine


@pytest.mark.browser
@pytest.mark.asyncio
async def test_real_browser_run_record_distinguishes_a_tab_that_never_opened():
    """The original symptom, end to end, on real Chromium.

    Same link markup, same step, same engine. The only difference is whether
    the declared tab actually opens — and that difference must be visible in
    the record the run hands its consumers.
    """
    driver = BrowserDriver(headless=True)
    await driver.launch()
    try:
        await driver.page.set_content(
            '<a href="about:blank" target="_blank" '
            'onclick="event.preventDefault()">Attendance</a>'
        )
        stuck = await _run_click_through_workflow_engine(driver)

        await driver.page.set_content(
            '<a href="about:blank" target="_blank">Attendance</a>'
        )
        opened = await _run_click_through_workflow_engine(driver)
    finally:
        await driver.close()

    # Both clicks succeeded and both results still flow downstream.
    assert stuck.context['attendance']['status'] == 'success'
    assert opened.context['attendance']['status'] == 'success'
    assert stuck.context['attendance']['opened_new_tab'] is False
    assert opened.context['attendance']['opened_new_tab'] is True

    stuck_step = stuck.get_execution_trace_dict()['steps'][0]
    opened_step = opened.get_execution_trace_dict()['steps'][0]

    assert opened_step['status'] == 'success'
    assert 'error' not in opened_step
    assert stuck_step['status'] == 'partial'
    assert stuck_step['error']['code'] == 'UNVERIFIED_OUTCOME'
    assert "never observed 'new_tab'" in stuck_step['error']['message']

    assert _build_recipe_result('a', stuck.get_execution_trace())['passedSteps'] == 0
    assert _build_recipe_result('a', opened.get_execution_trace())['passedSteps'] == 1


# ---------------------------------------------------------------------------
# Elements whose new tab is declared somewhere other than the clicked node
# ---------------------------------------------------------------------------
#
# A browser resolves a click's target from more than the element under the
# cursor. Three shapes carry the decision elsewhere, and reading only the
# element left every one of them looking exactly like a click that promised
# nothing: the tab that never opened was indistinguishable, at the consumer,
# from the tab that did.

# (markup that really opens a tab, markup that declares the same and opens none)
_TAB_DECLARED_ELSEWHERE = {
    # The owning <form> carries the target; the submit button carries nothing.
    'form_target': (
        '<form action="about:blank" target="_blank">'
        '<button type="submit">Attendance</button></form>',
        '<form action="about:blank" target="_blank" onsubmit="event.preventDefault()">'
        '<button type="submit">Attendance</button></form>',
    ),
    # The document's <base> carries it; the anchor is entirely plain.
    'base_target': (
        '<html><head><base target="_blank"></head><body>'
        '<a href="about:blank">Attendance</a></body></html>',
        '<html><head><base target="_blank"></head><body>'
        '<a href="about:blank" onclick="event.preventDefault()">Attendance</a>'
        '</body></html>',
    ),
    # The handler names a function; the window.open lives in its body.
    'onclick_function': (
        '<script>var ready = true;'
        'function go() { if (!ready) { return; } window.open("about:blank"); }'
        '</script><button onclick="go()">Attendance</button>',
        '<script>var ready = false;'
        'function go() { if (!ready) { return; } window.open("about:blank"); }'
        '</script><button onclick="go()">Attendance</button>',
    ),
}

# Nothing here declares a tab, and nothing here may start reporting one.
_DECLARES_NO_TAB = [
    '<button onclick="document.title = \'clicked\'">Attendance</button>',
    '<a href="#attendance">Attendance</a>',
]


async def _run_click_on_markup(markup):
    """Run the one-step click workflow against ``markup`` on real Chromium.

    Each variant gets its own session: an adopted popup would otherwise still
    be the controlled page when the next variant sets its content.
    """
    driver = BrowserDriver(headless=True)
    await driver.launch()
    try:
        await driver.page.set_content(markup)
        engine = await _run_click_through_workflow_engine(driver)
    finally:
        await driver.close()
    return (
        engine.context['attendance'],
        engine.get_execution_trace_dict()['steps'][0],
        _build_recipe_result('portal', engine.get_execution_trace()),
    )


@pytest.mark.browser
@pytest.mark.asyncio
@pytest.mark.parametrize('element_class', sorted(_TAB_DECLARED_ELSEWHERE))
async def test_real_browser_run_record_separates_a_ghost_tab_for_every_element_class(
    element_class,
):
    """The original symptom, end to end, for each class that declares a tab.

    Same markup, same step, same engine; the only difference is whether the
    declared tab actually opens. That difference has to reach the record.
    """
    real_markup, ghost_markup = _TAB_DECLARED_ELSEWHERE[element_class]

    opened_result, opened_step, opened_reply = await _run_click_on_markup(real_markup)
    stuck_result, stuck_step, stuck_reply = await _run_click_on_markup(ghost_markup)

    # Ground truth: Chromium really opens one and really opens none.
    assert opened_result['opened_new_tab'] is True
    assert stuck_result['opened_new_tab'] is False

    # Both clicks still succeed and both results still flow downstream.
    assert opened_result['status'] == 'success'
    assert stuck_result['status'] == 'success'
    assert opened_result['expected_outcome'] == 'new_tab'
    assert stuck_result['expected_outcome'] == 'new_tab'
    assert opened_result['verification_status'] == 'inferred'
    assert stuck_result['verification_status'] == 'unverified'

    # At the consumer the two runs are no longer the same record.
    assert opened_step['status'] == 'success'
    assert 'error' not in opened_step
    assert opened_reply['passedSteps'] == 1

    assert stuck_step['status'] == 'partial'
    assert stuck_step['error']['code'] == 'UNVERIFIED_OUTCOME'
    assert "never observed 'new_tab'" in stuck_step['error']['message']
    assert stuck_reply['ok'] is True
    assert stuck_reply['passedSteps'] == 0


@pytest.mark.browser
@pytest.mark.asyncio
@pytest.mark.parametrize('markup', _DECLARES_NO_TAB)
async def test_real_browser_keeps_a_click_that_declares_no_tab_a_clean_success(markup):
    """Resolving the effective target must not start inferring tabs.

    A plain in-page button and an ordinary same-tab link promise nothing, so
    'partial' must stay the exception rather than become the default.
    """
    result, step, reply = await _run_click_on_markup(markup)

    assert result['status'] == 'success'
    assert result['expected_outcome'] == 'auto'
    assert result['verification_status'] == 'not_requested'
    assert result['opened_new_tab'] is False
    assert step['status'] == 'success'
    assert 'error' not in step
    assert reply['passedSteps'] == 1


@pytest.mark.browser
@pytest.mark.asyncio
@pytest.mark.parametrize('markup,selector,declares', [
    # A submit control's own formtarget overrides the form it submits, in
    # both directions — otherwise 'any _blank anywhere' would pass too.
    ('<form action="about:blank" target="_blank">'
     '<button type="submit" formtarget="_self">Go</button></form>', 'button', False),
    ('<form action="about:blank" target="_self">'
     '<button type="submit" formtarget="_blank">Go</button></form>', 'button', True),
    # Only a control that submits inherits its form's target.
    ('<form action="about:blank" target="_blank">'
     '<button type="button" onclick="void 0">Go</button></form>', 'button', False),
    ('<form action="about:blank" target="_blank">'
     '<input type="submit" value="Go"></form>', 'input', True),
    # <base target> is the fallback, not an override, and it reaches only
    # what navigates.
    ('<html><head><base target="_blank"></head><body>'
     '<form action="about:blank"><button type="submit">Go</button></form>'
     '</body></html>', 'button', True),
    ('<html><head><base target="_blank"></head><body>'
     '<form action="about:blank" target="_self"><button type="submit">Go</button>'
     '</form></body></html>', 'button', False),
    ('<html><head><base target="_blank"></head><body>'
     '<a href="about:blank" target="_self">Go</a></body></html>', 'a', False),
    ('<html><head><base target="_blank"></head><body>'
     '<button onclick="void 0">Go</button></body></html>', 'button', False),
    ('<html><head><base target="_blank"></head><body><a>Go</a></body></html>', 'a', False),
    # A named handler is read for what its body does, not what it is called.
    ('<script>var ns = { go: function () { window.open("about:blank"); } };</script>'
     '<button onclick="ns.go()">Go</button>', 'button', True),
    ('<script>function go() { document.title = "x"; }</script>'
     '<button onclick="go()">Go</button>', 'button', False),
    ('<script>function go() { new XMLHttpRequest().open("GET", "/a"); }</script>'
     '<button onclick="go()">Go</button>', 'button', False),
    ('<button onclick="nope()">Go</button>', 'button', False),
])
async def test_effective_tab_declaration_follows_browser_target_resolution(
    markup, selector, declares,
):
    """Resolve the effective target the way the browser does, both ways."""
    driver = BrowserDriver(headless=True)
    await driver.launch()
    try:
        await driver.page.set_content(markup)
        module = BrowserClickModule(
            {'click_method': 'selector', 'selector': selector},
            {'browser': driver},
        )
        assert await module._expects_new_page(
            driver.page.locator(selector).first,
        ) is declares
    finally:
        await driver.close()


# ---------------------------------------------------------------------------
# The declared output contract against what execute() really returns
# ---------------------------------------------------------------------------

# Every kind of control the post-click hint harvest reports, on one page, so
# a single run produces every key browser.click is able to produce.
_EVERY_CONTROL = """
<button id="go">Go</button>
<form>
  <input type="text" name="user" aria-label="User">
  <input type="file" name="doc" aria-label="Doc">
  <input type="checkbox" id="agree"><label for="agree">Agree</label>
  <input type="radio" name="pick" id="one"><label for="one">One</label>
  <input type="radio" name="pick" id="two"><label for="two">Two</label>
  <select name="choice" aria-label="Choice"><option>a</option><option>b</option></select>
  <div role="switch" aria-checked="false" tabindex="0" aria-label="Notify">Notify</div>
</form>
<a href="#elsewhere">Somewhere</a>
<p>Body text</p>
"""


@pytest.mark.browser
@pytest.mark.asyncio
async def test_output_schema_declares_exactly_the_keys_execute_produces():
    """The declaration and the result must be the same set of keys.

    A declared key nothing produces is a promise the module cannot keep, and
    a produced key nothing declares is invisible to every consumer that maps
    outputs from metadata. Pinned in both directions so neither can drift.
    """
    driver = BrowserDriver(headless=True)
    await driver.launch()
    try:
        await driver.page.set_content(_EVERY_CONTROL)
        result = await BrowserClickModule(
            {'click_method': 'id', 'target': 'go', 'timeout_ms': 2000},
            {'browser': driver},
        ).execute()
    finally:
        await driver.close()

    metadata = ModuleRegistry.get_metadata('browser.click')
    declared = set(metadata['output_schema'])

    assert declared == {
        'status', 'selector', 'method', 'opened_new_tab', 'tab_count',
        'current_index', 'url', 'expected_outcome', 'verification_status',
        'effect_observed', 'effects', 'pre_url', '_page_hint', 'inputs',
        'checkboxes', 'radios', 'switches', 'selects', 'buttons', 'links',
        'file_inputs',
    }
    assert set(result) == declared

    # The browser session is a context pass-through: chaining is declared by
    # output_types, and no code path ever puts it in the result.
    assert 'browser' not in result
    assert 'browser' in metadata['output_types']


# ---------------------------------------------------------------------------
# The two result shapes the ledger has to read besides a plain dict
# ---------------------------------------------------------------------------


class _LegacyOkModule:
    """A module reporting the old ``{'ok': True, ...}`` contract.

    ``_execute_single_mode`` hands any such result to ``wrap_legacy_result``,
    which moves every non-meta key into a ``data`` sub-dict — so the payload
    the ledger has to read is no longer at the top level of the step result.
    """

    def __init__(self, params, context):
        self.params = params
        self.context = context

    async def run(self):
        return {
            'ok': True,
            'status': 'success',
            'expected_outcome': 'new_tab',
            'verification_status': 'unverified',
            'effect_observed': False,
            'opened_new_tab': False,
        }


@pytest.mark.asyncio
async def test_step_record_reads_an_unconfirmed_outcome_out_of_a_legacy_data_dict(
    monkeypatch,
):
    """A legacy-shaped result hides the payload one level down.

    Without reading it, a module that reports the old ``ok`` contract is
    always recorded as a clean success no matter what it says it never saw.
    """
    from core.modules.registry import ModuleRegistry as Registry

    monkeypatch.setattr(
        Registry, 'get', classmethod(lambda cls, module_id: _LegacyOkModule),
    )

    collector = TraceCollector('wf-legacy', 'Legacy ok module', {})
    collector.start()
    context = {}
    executor = StepExecutor(
        workflow_id='wf-legacy',
        workflow_name='Legacy ok module',
        total_steps=1,
    )
    result = await executor.execute_step(
        step_config={'id': 'legacy', 'module': 'browser.click', 'params': {}},
        step_index=0,
        context=context,
        resolver=VariableResolver({}, context),
        trace_collector=collector,
    )

    # The payload really is nested: nothing at the top level says a word
    # about verification.
    assert result['ok'] is True
    assert 'verification_status' not in result
    assert result['data']['verification_status'] == 'unverified'

    step = collector.complete({}).to_dict()['steps'][0]
    assert step['status'] == 'partial'
    assert step['error']['code'] == 'UNVERIFIED_OUTCOME'
    assert "never observed 'new_tab'" in step['error']['message']


_FOREACH_TARGETS = """
<button onclick="document.title = 'clicked'">First</button>
<script>var ready = false;
function go() { if (!ready) { return; } window.open("about:blank"); }</script>
<button onclick="go()">Second</button>
"""


@pytest.mark.browser
@pytest.mark.asyncio
async def test_step_record_reads_an_unconfirmed_outcome_out_of_a_foreach_iteration():
    """A foreach step's result is a list, and iteration 2 is the unconfirmed one.

    Reading only a dict-shaped result makes every foreach step a clean
    success, however many of its iterations never saw what they expected.
    """
    driver = BrowserDriver(headless=True)
    await driver.launch()
    try:
        await driver.page.set_content(_FOREACH_TARGETS)

        collector = TraceCollector('wf-foreach', 'Two clicks', {})
        collector.start()
        context = {'browser': driver, 'targets': ['First', 'Second']}
        executor = StepExecutor(
            workflow_id='wf-foreach',
            workflow_name='Two clicks',
            total_steps=1,
        )
        results = await executor.execute_step(
            step_config={
                'id': 'each',
                'module': 'browser.click',
                'params': {
                    'click_method': 'button',
                    'target': '${item}',
                    'timeout_ms': 2000,
                },
                'foreach': '${targets}',
                'as': 'item',
            },
            step_index=0,
            context=context,
            resolver=VariableResolver({}, context),
            trace_collector=collector,
        )
    finally:
        await driver.close()

    # One result per iteration, and only the second one went unconfirmed.
    assert len(results) == 2
    assert results[0]['verification_status'] == 'not_requested'
    assert results[0]['expected_outcome'] == 'auto'
    assert results[1]['verification_status'] == 'unverified'
    assert results[1]['expected_outcome'] == 'new_tab'
    assert results[1]['opened_new_tab'] is False

    step = collector.complete({}).to_dict()['steps'][0]
    assert step['status'] == 'partial'
    assert step['error']['code'] == 'UNVERIFIED_OUTCOME'
    assert "never observed 'new_tab'" in step['error']['message']


# ---------------------------------------------------------------------------
# Both verification branches must measure the same document.
#
# `_verify_page_outcome` used to take a `page` argument that only the URL
# branch honoured: the selector branch delegates to `browser.wait`, which
# resolves the document from `browser._page` and cannot be pointed elsewhere.
# That was correct only because execute() called it before tab adoption. Had
# the call ever moved after adoption, the URL branch would have judged the
# opener while the selector branch silently followed the popup. The parameter
# is gone and the method names the document it measures; these pin that both
# branches read `browser.page`.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_url_branch_measures_the_browsers_current_page():
    module, browser, opener, _ = _wire(
        {'expected_outcome': 'url_change', 'verification_timeout_ms': 50},
        url='https://opener.test',
    )
    adopted = _Page({}, url='https://adopted.test')
    browser._page = adopted

    # Measured against the opener's pre-click URL, the adopted page has changed.
    await module._verify_current_page_outcome(
        browser, 'url_change', 'https://opener.test'
    )


@pytest.mark.asyncio
async def test_selector_branch_measures_the_same_page_as_the_url_branch():
    module, browser, opener, _ = _wire(
        {'expected_outcome': 'selector_visible', 'outcome_value': '#done',
         'verification_timeout_ms': 50},
        url='https://opener.test',
        matches={'#done': _Locator(count=1)},
    )
    # The opener satisfies '#done'; the adopted page does not.
    adopted = _Page({'#done': _Locator(count=0)}, url='https://adopted.test')
    browser._page = adopted

    with pytest.raises(RuntimeError, match="expected '#done' to become visible"):
        await module._verify_current_page_outcome(
            browser, 'selector_visible', 'https://opener.test'
        )

    # It consulted the browser's page, not the one the opener held.
    assert browser.wait_calls == [('#done', 'visible')]
