"""
Tests for Browser Select Module
"""
import pytest
import pytest_asyncio
from core.modules.atomic.browser.select import BrowserSelectModule


def test_select_missing_selector():
    """Test validation without selector"""
    module = BrowserSelectModule(
        params={'value': 'test'},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: selector"):
        module.validate_params()


def test_select_missing_selection_method():
    """Test validation without value/label/index"""
    module = BrowserSelectModule(
        params={'selector': 'select'},
        context={}
    )
    with pytest.raises(ValueError, match="Must provide at least one of"):
        module.validate_params()


def test_select_valid_params():
    """Test valid parameters"""
    module = BrowserSelectModule(
        params={'selector': 'select', 'value': 'us'},
        context={}
    )
    module.validate_params()
    assert module.selector == 'select'
    assert module.value == 'us'


@pytest.mark.asyncio
async def test_select_no_browser():
    """Test error when browser not launched"""
    module = BrowserSelectModule(
        params={'selector': 'select', 'value': 'test'},
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
