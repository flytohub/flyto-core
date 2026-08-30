"""Focused contract tests for semantic browser.click resolution."""

from unittest.mock import AsyncMock

import pytest

from core.browser.driver import BrowserDriver
from core.modules.atomic.browser.click import BrowserClickModule
from core.modules.atomic.browser.tab import BrowserTabModule


class _Locator:
    def __init__(self, count=0, attributes=None, click_hook=None):
        self._count = count
        self._attributes = attributes or {}
        self.click = AsyncMock(side_effect=click_hook)
        self.visible_filter_calls = []

    def filter(self, **kwargs):
        self.visible_filter_calls.append(kwargs)
        return self

    async def count(self):
        return self._count

    async def get_attribute(self, name):
        return self._attributes.get(name)

    @property
    def first(self):
        return self


class _Page:
    def __init__(self, matches, url='https://example.test/', hint='source page'):
        self.matches = matches
        self.calls = []
        self.url = url
        self.hint = hint
        self.wait_for_load_state = AsyncMock()
        self.wait_for_function = AsyncMock()
        self.wait_for_timeout = AsyncMock()
        self.bring_to_front = AsyncMock()

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
        self.wait = AsyncMock()

    @property
    def page(self):
        return self._page

    async def get_hints(self, force=False):
        return {'text': self._page.hint}


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
    page = _Page({})
    module = BrowserClickModule(
        {
            'click_method': 'button',
            'target': 'Missing',
            'timeout_ms': 5,
        },
        {},
    )

    with pytest.raises(RuntimeError, match='within 5ms'):
        await module._resolve_button_or_link(page)


@pytest.mark.asyncio
async def test_click_adopts_new_tab_for_following_steps_and_preview():
    source = _Page({}, url='https://example.test/portal', hint='portal')
    popup = _Page({}, url='https://example.test/attendance', hint='attendance')
    context = _Context(source)

    async def open_popup(**_kwargs):
        context.open_page(popup)

    link = _Locator(
        count=1,
        attributes={'target': '_blank'},
        click_hook=open_popup,
    )
    source.matches[('link', True)] = link
    browser = _Browser(source, context)
    module = BrowserClickModule(
        {'click_method': 'button', 'target': 'Attendance'},
        {'browser': browser},
    )

    result = await module.execute()

    assert browser.page is popup
    assert context.pages == [source, popup]
    assert context.listeners['page'] == []
    assert result['opened_new_tab'] is True
    assert result['effect_observed'] is True
    assert result['effects'] == ['new_tab', 'url_change', 'page_content_change']
    assert result['verification_status'] == 'verified'
    assert result['expected_outcome'] == 'new_tab'
    assert result['tab_count'] == 2
    assert result['current_index'] == 1
    assert result['url'] == 'https://example.test/attendance'
    assert result['_page_hint'] == 'attendance'

    # Regression for the production failure: the immediately following tab
    # node must see index 1 instead of reporting a 0-0 valid range.
    tab_result = await BrowserTabModule(
        {'action': 'switch', 'index': 1},
        {'browser': browser},
    ).execute()

    assert tab_result['tab_count'] == 2
    assert tab_result['current_index'] == 1
    popup.bring_to_front.assert_awaited_once()


@pytest.mark.asyncio
async def test_click_fails_when_explicit_new_tab_intent_is_not_fulfilled():
    source = _Page({}, url='https://example.test/portal', hint='portal')
    context = _Context(source)
    link = _Locator(count=1, attributes={'target': '_blank'})
    source.matches[('link', True)] = link
    browser = _Browser(source, context)
    module = BrowserClickModule(
        {
            'click_method': 'button',
            'target': 'Attendance',
            'verification_timeout_ms': 5,
        },
        {'browser': browser},
    )

    with pytest.raises(RuntimeError, match='expected a new tab'):
        await module.execute()

    assert context.listeners['page'] == []


@pytest.mark.asyncio
async def test_click_can_require_a_new_tab_for_script_driven_actions():
    source = _Page({}, url='https://example.test/portal', hint='portal')
    popup = _Page({}, url='https://example.test/attendance', hint='attendance')
    context = _Context(source)

    async def open_popup(**_kwargs):
        context.open_page(popup)

    link = _Locator(count=1, click_hook=open_popup)
    source.matches[('link', True)] = link
    browser = _Browser(source, context)
    module = BrowserClickModule(
        {
            'click_method': 'button',
            'target': 'Attendance',
            'expected_outcome': 'new_tab',
        },
        {'browser': browser},
    )

    result = await module.execute()

    assert result['verification_status'] == 'verified'
    assert result['expected_outcome'] == 'new_tab'
    assert result['opened_new_tab'] is True


@pytest.mark.asyncio
async def test_click_reports_unverified_when_no_outcome_was_requested_or_inferred():
    source = _Page({}, url='https://example.test/form', hint='unchanged')
    context = _Context(source)
    button = _Locator(count=1)
    source.matches[('button', True)] = button
    browser = _Browser(source, context)
    module = BrowserClickModule(
        {'click_method': 'button', 'target': 'Toggle'},
        {'browser': browser},
    )

    result = await module.execute()

    assert result['status'] == 'success'
    assert result['effect_observed'] is False
    assert result['effects'] == []
    assert result['verification_status'] == 'not_requested'
    assert result['expected_outcome'] == 'auto'


@pytest.mark.asyncio
async def test_click_only_confirms_dispatch_without_claiming_a_visible_effect():
    source = _Page({}, url='https://example.test/form', hint='unchanged')
    context = _Context(source)
    button = _Locator(count=1)
    source.matches[('button', True)] = button
    browser = _Browser(source, context)
    module = BrowserClickModule(
        {
            'click_method': 'button',
            'target': 'Submit',
            'expected_outcome': 'click_only',
        },
        {'browser': browser},
    )

    result = await module.execute()

    assert result['verification_status'] == 'verified'
    assert result['effect_observed'] is False
    button.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_click_can_verify_a_same_tab_url_change():
    source = _Page({}, url='https://example.test/form', hint='form')
    context = _Context(source)

    async def navigate(**_kwargs):
        source.url = 'https://example.test/complete'
        source.hint = 'complete'

    source.matches[('button', True)] = _Locator(count=1, click_hook=navigate)
    browser = _Browser(source, context)
    module = BrowserClickModule(
        {
            'click_method': 'button',
            'target': 'Submit',
            'expected_outcome': 'url_change',
        },
        {'browser': browser},
    )

    result = await module.execute()

    assert result['verification_status'] == 'verified'
    assert result['effects'] == ['url_change', 'page_content_change']
    assert result['pre_url'] == 'https://example.test/form'
    assert result['url'] == 'https://example.test/complete'


@pytest.mark.asyncio
async def test_selector_outcome_requires_a_real_state_transition():
    visible_target = _Locator(count=1)
    source = _Page(
        {('button', True): _Locator(count=1), '#result': visible_target},
        url='https://example.test/form',
    )
    context = _Context(source)
    browser = _Browser(source, context)
    module = BrowserClickModule(
        {
            'click_method': 'button',
            'target': 'Submit',
            'expected_outcome': 'selector_visible',
            'outcome_value': '#result',
        },
        {'browser': browser},
    )

    with pytest.raises(RuntimeError, match='already satisfied before the click'):
        await module.execute()

    browser.wait.assert_not_awaited()


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
        module = BrowserClickModule(
            {
                'click_method': 'button',
                'target': 'Attendance',
                'verification_timeout_ms': 100,
            },
            {'browser': driver},
        )

        with pytest.raises(RuntimeError, match='expected a new tab'):
            await module.execute()
    finally:
        await driver.close()
