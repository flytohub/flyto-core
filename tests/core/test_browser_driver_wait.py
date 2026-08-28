"""Browser wait selector-state regressions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.browser.driver import BrowserDriver


@pytest.mark.asyncio
async def test_wait_visible_ignores_hidden_duplicate_matches() -> None:
    driver = BrowserDriver()
    visible_wait = AsyncMock()
    visible_matches = SimpleNamespace(
        first=SimpleNamespace(wait_for=visible_wait),
    )
    all_matches = MagicMock()
    all_matches.filter.return_value = visible_matches
    page = MagicMock()
    page.locator.return_value = all_matches
    page.wait_for_selector = AsyncMock()
    driver._page = page

    result = await driver.wait('text=Notices', state='visible', timeout_ms=4321)

    page.locator.assert_called_once_with('text=Notices')
    all_matches.filter.assert_called_once_with(visible=True)
    visible_wait.assert_awaited_once_with(state='visible', timeout=4321)
    page.wait_for_selector.assert_not_awaited()
    assert result == {
        'status': 'success',
        'selector': 'text=Notices',
        'state': 'visible',
    }


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['attached', 'detached', 'hidden'])
async def test_wait_preserves_non_visible_state_semantics(state: str) -> None:
    driver = BrowserDriver()
    page = MagicMock()
    page.wait_for_selector = AsyncMock()
    driver._page = page

    await driver.wait('.status', state=state, timeout_ms=987)

    page.locator.assert_not_called()
    page.wait_for_selector.assert_awaited_once_with(
        '.status',
        state=state,
        timeout=987,
    )
