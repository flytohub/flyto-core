"""Focused contract tests for semantic browser.click resolution."""

from unittest.mock import AsyncMock

import pytest

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
