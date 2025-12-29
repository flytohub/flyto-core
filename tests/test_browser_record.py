"""
Tests for Browser Record Module
"""
import pytest
import pytest_asyncio
from core.modules.atomic.browser.record import BrowserRecordModule


@pytest.mark.asyncio
async def test_record_start(browser):
    """Test starting recording"""
    await browser.goto("https://example.com")

    module = BrowserRecordModule(
        params={'action': 'start'},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert result['message'] == 'Recording started'


@pytest.mark.asyncio
async def test_record_get(browser):
    """Test getting current recording"""
    await browser.goto("https://example.com")

    module = BrowserRecordModule(
        params={'action': 'get'},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert 'recording' in result
    assert 'workflow' in result


def test_record_missing_action():
    """Test validation without action"""
    module = BrowserRecordModule(
        params={},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: action"):
        module.validate_params()


def test_record_invalid_action():
    """Test validation with invalid action"""
    module = BrowserRecordModule(
        params={'action': 'invalid'},
        context={}
    )
    with pytest.raises(ValueError, match="Invalid action"):
        module.validate_params()


@pytest.mark.asyncio
async def test_record_no_browser():
    """Test error when browser not launched"""
    module = BrowserRecordModule(
        params={'action': 'start'},
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
