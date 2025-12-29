"""
Tests for Browser Evaluate Module
"""
import pytest
import pytest_asyncio
from core.modules.atomic.browser.evaluate import BrowserEvaluateModule


@pytest.mark.asyncio
async def test_evaluate_simple_script(browser):
    """Test executing simple JavaScript"""
    await browser.goto("https://example.com")

    module = BrowserEvaluateModule(
        params={'script': 'return document.title'},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert result['result'] is not None


@pytest.mark.asyncio
async def test_evaluate_return_value(browser):
    """Test JavaScript return value"""
    await browser.goto("https://example.com")

    module = BrowserEvaluateModule(
        params={'script': 'return 1 + 1'},
        context={'browser': browser}
    )
    module.validate_params()
    result = await module.execute()

    assert result['status'] == 'success'
    assert result['result'] == 2


def test_evaluate_missing_script():
    """Test validation without script"""
    module = BrowserEvaluateModule(
        params={},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: script"):
        module.validate_params()


@pytest.mark.asyncio
async def test_evaluate_no_browser():
    """Test error when browser not launched"""
    module = BrowserEvaluateModule(
        params={'script': 'return true'},
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
