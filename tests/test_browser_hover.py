"""
Tests for Browser Hover Module
"""
import pytest
import pytest_asyncio
from core.modules.atomic.browser.hover import BrowserHoverModule


@pytest.mark.asyncio
async def test_hover_element(browser):
    """Test hovering over element"""
    await browser.goto("https://example.com")

    module = BrowserHoverModule(
        params={'selector': 'a'},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert result['selector'] == 'a'


def test_hover_missing_selector():
    """Test validation without selector"""
    module = BrowserHoverModule(
        params={},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: selector"):
        module.validate_params()


@pytest.mark.asyncio
async def test_hover_no_browser():
    """Test error when browser not launched"""
    module = BrowserHoverModule(
        params={'selector': 'div'},
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
