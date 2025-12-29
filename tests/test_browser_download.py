"""
Tests for Browser Download Module
"""
import pytest
import pytest_asyncio
from core.modules.atomic.browser.download import BrowserDownloadModule


def test_download_missing_save_path():
    """Test validation without save_path"""
    module = BrowserDownloadModule(
        params={'selector': '#download-btn'},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: save_path"):
        module.validate_params()


def test_download_valid_params(tmp_path):
    """Test valid parameters"""
    save_path = tmp_path / "download.pdf"

    module = BrowserDownloadModule(
        params={
            'selector': '#download-btn',
            'save_path': str(save_path)
        },
        context={}
    )
    module.validate_params()
    assert module.save_path == str(save_path)


@pytest.mark.asyncio
async def test_download_no_browser(tmp_path):
    """Test error when browser not launched"""
    save_path = tmp_path / "download.pdf"

    module = BrowserDownloadModule(
        params={
            'selector': '#download-btn',
            'save_path': str(save_path)
        },
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
