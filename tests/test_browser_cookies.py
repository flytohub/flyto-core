"""
Tests for Browser Cookies Module
"""
import pytest
import pytest_asyncio
from core.modules.atomic.browser.cookies import BrowserCookiesModule


@pytest.mark.asyncio
async def test_cookies_get_all(browser):
    """Test getting all cookies"""
    await browser.goto("https://example.com")

    module = BrowserCookiesModule(
        params={'action': 'get'},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert 'cookies' in result
    assert isinstance(result['cookies'], list)


@pytest.mark.asyncio
async def test_cookies_clear(browser):
    """Test clearing cookies"""
    await browser.goto("https://example.com")

    module = BrowserCookiesModule(
        params={'action': 'clear'},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert result['count'] == 0


def test_cookies_missing_action():
    """Test validation without action"""
    module = BrowserCookiesModule(
        params={},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: action"):
        module.validate_params()


def test_cookies_invalid_action():
    """Test validation with invalid action"""
    module = BrowserCookiesModule(
        params={'action': 'invalid'},
        context={}
    )
    with pytest.raises(ValueError, match="Invalid action"):
        module.validate_params()


def test_cookies_set_missing_params():
    """Test set action without required params"""
    module = BrowserCookiesModule(
        params={'action': 'set', 'name': 'test'},
        context={}
    )
    with pytest.raises(ValueError, match="set action requires"):
        module.validate_params()


@pytest.mark.asyncio
async def test_cookies_no_browser():
    """Test error when browser not launched"""
    module = BrowserCookiesModule(
        params={'action': 'get'},
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
