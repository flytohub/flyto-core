"""
Tests for Browser Dialog Module
"""
import pytest
import pytest_asyncio
from core.modules.atomic.browser.dialog import BrowserDialogModule


@pytest.mark.asyncio
async def test_dialog_listen(browser):
    """Test listening for dialogs"""
    await browser.goto("https://example.com")

    module = BrowserDialogModule(
        params={'action': 'listen', 'timeout': 1000},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert result['action'] == 'listen'


def test_dialog_missing_action():
    """Test validation without action"""
    module = BrowserDialogModule(
        params={},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: action"):
        module.validate_params()


def test_dialog_invalid_action():
    """Test validation with invalid action"""
    module = BrowserDialogModule(
        params={'action': 'invalid'},
        context={}
    )
    with pytest.raises(ValueError, match="Invalid action"):
        module.validate_params()


@pytest.mark.asyncio
async def test_dialog_no_browser():
    """Test error when browser not launched"""
    module = BrowserDialogModule(
        params={'action': 'accept'},
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
