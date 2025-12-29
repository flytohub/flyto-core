"""
Tests for Browser Console Module
"""
import pytest
import pytest_asyncio
from core.modules.atomic.browser.console import BrowserConsoleModule


@pytest.mark.asyncio
async def test_console_capture_all(browser):
    """Test capturing all console messages"""
    await browser.goto("https://example.com")

    module = BrowserConsoleModule(
        params={'level': 'all', 'timeout': 2000},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert 'messages' in result
    assert 'count' in result
    assert isinstance(result['messages'], list)


@pytest.mark.asyncio
async def test_console_capture_errors_only(browser):
    """Test capturing only error messages"""
    await browser.goto("https://example.com")

    module = BrowserConsoleModule(
        params={'level': 'error', 'timeout': 1000},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'


def test_console_validate_invalid_level():
    """Test validation with invalid level"""
    module = BrowserConsoleModule(
        params={'level': 'invalid'},
        context={}
    )
    with pytest.raises(ValueError, match="Invalid level"):
        module.validate_params()


@pytest.mark.asyncio
async def test_console_no_browser():
    """Test error when browser not launched"""
    module = BrowserConsoleModule(
        params={'timeout': 1000},
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
