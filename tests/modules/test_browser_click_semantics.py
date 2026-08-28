"""Focused contract tests for semantic browser.click resolution."""

from unittest.mock import AsyncMock

import pytest

from core.modules.atomic.browser.click import BrowserClickModule


class _Locator:
    def __init__(self, count=0):
        self._count = count
        self.click = AsyncMock()
        self.visible_filter_calls = []

    def filter(self, **kwargs):
        self.visible_filter_calls.append(kwargs)
        return self

    async def count(self):
        return self._count

    @property
    def first(self):
        return self


class _Page:
    def __init__(self, matches):
        self.matches = matches
        self.calls = []

    def get_by_role(self, role, **kwargs):
        self.calls.append((role, kwargs))
        return self.matches.get((role, kwargs['exact']), _Locator())


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
