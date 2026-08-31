"""Browser wait selector-state regressions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.browser.driver import BrowserDriver


@pytest.mark.asyncio
@pytest.mark.parametrize('selector,state,timeout_ms', [
    ('text=Notices', 'visible', 4321),
    ('.status', 'hidden', 987),
])
async def test_wait_visibility_states_ignore_duplicate_matches(
    selector: str, state: str, timeout_ms: int,
) -> None:
    """Both visibility states are decided over every match, not the first.

    ``page.wait_for_selector`` resolves on the first match, so a hidden
    duplicate both blocks 'visible' and satisfies 'hidden' while a later match
    is still on screen. Filtering to visible matches gives the two states one
    contract and its exact negation.
    """
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

    result = await driver.wait(selector, state=state, timeout_ms=timeout_ms)

    page.locator.assert_called_once_with(selector)
    all_matches.filter.assert_called_once_with(visible=True)
    visible_wait.assert_awaited_once_with(state=state, timeout=timeout_ms)
    page.wait_for_selector.assert_not_awaited()
    assert result == {
        'status': 'success',
        'selector': selector,
        'state': state,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['attached', 'detached'])
async def test_wait_preserves_non_visible_state_semantics(state: str) -> None:
    """Presence states are not visibility states and keep the first-match path."""
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
