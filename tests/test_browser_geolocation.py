"""
Tests for Browser Geolocation Module
"""
import pytest
import pytest_asyncio
from core.modules.atomic.browser.geolocation import BrowserGeolocationModule


@pytest.mark.asyncio
async def test_geolocation_set(browser):
    """Test setting geolocation"""
    await browser.goto("https://example.com")

    module = BrowserGeolocationModule(
        params={'latitude': 37.7749, 'longitude': -122.4194},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert result['location']['latitude'] == 37.7749
    assert result['location']['longitude'] == -122.4194


def test_geolocation_missing_latitude():
    """Test validation without latitude"""
    module = BrowserGeolocationModule(
        params={'longitude': -122.4194},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: latitude"):
        module.validate_params()


def test_geolocation_missing_longitude():
    """Test validation without longitude"""
    module = BrowserGeolocationModule(
        params={'latitude': 37.7749},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: longitude"):
        module.validate_params()


def test_geolocation_invalid_latitude():
    """Test validation with invalid latitude"""
    module = BrowserGeolocationModule(
        params={'latitude': 100, 'longitude': 0},
        context={}
    )
    with pytest.raises(ValueError, match="Latitude must be between"):
        module.validate_params()


def test_geolocation_invalid_longitude():
    """Test validation with invalid longitude"""
    module = BrowserGeolocationModule(
        params={'latitude': 0, 'longitude': 200},
        context={}
    )
    with pytest.raises(ValueError, match="Longitude must be between"):
        module.validate_params()


@pytest.mark.asyncio
async def test_geolocation_no_browser():
    """Test error when browser not launched"""
    module = BrowserGeolocationModule(
        params={'latitude': 37.7749, 'longitude': -122.4194},
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
