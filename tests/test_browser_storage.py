"""
Tests for Browser Storage Module
"""
import pytest
import pytest_asyncio
from core.modules.atomic.browser.storage import BrowserStorageModule


@pytest.mark.asyncio
async def test_storage_get(browser):
    """Test getting storage value"""
    await browser.goto("https://example.com")

    module = BrowserStorageModule(
        params={'action': 'get', 'key': 'test_key'},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert 'value' in result


@pytest.mark.asyncio
async def test_storage_keys(browser):
    """Test getting storage keys"""
    await browser.goto("https://example.com")

    module = BrowserStorageModule(
        params={'action': 'keys'},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert 'keys' in result


def test_storage_missing_action():
    """Test validation without action"""
    module = BrowserStorageModule(
        params={},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: action"):
        module.validate_params()


def test_storage_invalid_action():
    """Test validation with invalid action"""
    module = BrowserStorageModule(
        params={'action': 'invalid'},
        context={}
    )
    with pytest.raises(ValueError, match="Invalid action"):
        module.validate_params()


def test_storage_get_missing_key():
    """Test get action without key"""
    module = BrowserStorageModule(
        params={'action': 'get'},
        context={}
    )
    with pytest.raises(ValueError, match="action requires key"):
        module.validate_params()


@pytest.mark.asyncio
async def test_storage_no_browser():
    """Test error when browser not launched"""
    module = BrowserStorageModule(
        params={'action': 'keys'},
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
