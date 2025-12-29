"""
Tests for Browser Frame Module
"""
import pytest
import pytest_asyncio
from core.modules.atomic.browser.frame import BrowserFrameModule


@pytest.mark.asyncio
async def test_frame_list(browser):
    """Test listing frames"""
    await browser.goto("https://example.com")

    module = BrowserFrameModule(
        params={'action': 'list'},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert 'frames' in result
    assert isinstance(result['frames'], list)


def test_frame_enter_missing_selector():
    """Test enter action without selector"""
    module = BrowserFrameModule(
        params={'action': 'enter'},
        context={}
    )
    with pytest.raises(ValueError, match="enter action requires"):
        module.validate_params()


def test_frame_valid_list():
    """Test valid list action"""
    module = BrowserFrameModule(
        params={'action': 'list'},
        context={}
    )
    module.validate_params()
    assert module.action == 'list'


@pytest.mark.asyncio
async def test_frame_no_browser():
    """Test error when browser not launched"""
    module = BrowserFrameModule(
        params={'action': 'list'},
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
