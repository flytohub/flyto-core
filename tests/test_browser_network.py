"""
Tests for Browser Network Module
"""
import pytest
import pytest_asyncio
from core.modules.atomic.browser.network import BrowserNetworkModule


@pytest.mark.asyncio
async def test_network_monitor(browser):
    """Test monitoring network requests"""
    await browser.goto("https://example.com")

    module = BrowserNetworkModule(
        params={'action': 'monitor', 'timeout': 2000},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert 'requests' in result


def test_network_missing_action():
    """Test validation without action"""
    module = BrowserNetworkModule(
        params={},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: action"):
        module.validate_params()


def test_network_invalid_action():
    """Test validation with invalid action"""
    module = BrowserNetworkModule(
        params={'action': 'invalid'},
        context={}
    )
    with pytest.raises(ValueError, match="Invalid action"):
        module.validate_params()


def test_network_intercept_missing_response():
    """Test intercept action without mock_response"""
    module = BrowserNetworkModule(
        params={'action': 'intercept'},
        context={}
    )
    with pytest.raises(ValueError, match="intercept action requires mock_response"):
        module.validate_params()


@pytest.mark.asyncio
async def test_network_no_browser():
    """Test error when browser not launched"""
    module = BrowserNetworkModule(
        params={'action': 'monitor'},
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
