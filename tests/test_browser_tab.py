"""
Tests for Browser Tab Module
"""
import pytest
import pytest_asyncio
from core.modules.atomic.browser.tab import BrowserTabModule


@pytest.mark.asyncio
async def test_tab_list(browser):
    """Test listing tabs"""
    await browser.goto("https://example.com")

    module = BrowserTabModule(
        params={'action': 'list'},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert 'tabs' in result
    assert result['tab_count'] >= 1


def test_tab_missing_action():
    """Test validation without action"""
    module = BrowserTabModule(
        params={},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: action"):
        module.validate_params()


def test_tab_invalid_action():
    """Test validation with invalid action"""
    module = BrowserTabModule(
        params={'action': 'invalid'},
        context={}
    )
    with pytest.raises(ValueError, match="Invalid action"):
        module.validate_params()


def test_tab_switch_missing_index():
    """Test switch action without index"""
    module = BrowserTabModule(
        params={'action': 'switch'},
        context={}
    )
    with pytest.raises(ValueError, match="switch action requires index"):
        module.validate_params()


@pytest.mark.asyncio
async def test_tab_no_browser():
    """Test error when browser not launched"""
    module = BrowserTabModule(
        params={'action': 'list'},
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
