"""
Tests for Browser Scroll Module
"""
import pytest
import pytest_asyncio
from core.modules.atomic.browser.scroll import BrowserScrollModule


@pytest.mark.asyncio
async def test_scroll_down(browser):
    """Test scrolling down"""
    await browser.goto("https://example.com")

    module = BrowserScrollModule(
        params={'direction': 'down', 'amount': 200},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert 'scrolled_to' in result


@pytest.mark.asyncio
async def test_scroll_to_element(browser):
    """Test scrolling to element"""
    await browser.goto("https://example.com")

    module = BrowserScrollModule(
        params={'selector': 'h1'},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert result['selector'] == 'h1'


def test_scroll_validate_invalid_direction():
    """Test validation with invalid direction"""
    module = BrowserScrollModule(
        params={'direction': 'diagonal'},
        context={}
    )
    with pytest.raises(ValueError, match="Invalid direction"):
        module.validate_params()


def test_scroll_validate_invalid_behavior():
    """Test validation with invalid behavior"""
    module = BrowserScrollModule(
        params={'behavior': 'fast'},
        context={}
    )
    with pytest.raises(ValueError, match="Invalid behavior"):
        module.validate_params()


@pytest.mark.asyncio
async def test_scroll_no_browser():
    """Test error when browser not launched"""
    module = BrowserScrollModule(
        params={'direction': 'down'},
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
