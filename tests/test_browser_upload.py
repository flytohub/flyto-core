"""
Tests for Browser Upload Module
"""
import pytest
import pytest_asyncio
from pathlib import Path
from core.modules.atomic.browser.upload import BrowserUploadModule


def test_upload_missing_selector():
    """Test validation without selector"""
    module = BrowserUploadModule(
        params={'file_path': '/tmp/test.txt'},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: selector"):
        module.validate_params()


def test_upload_missing_file_path():
    """Test validation without file_path"""
    module = BrowserUploadModule(
        params={'selector': 'input[type="file"]'},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: file_path"):
        module.validate_params()


def test_upload_file_not_found():
    """Test validation with non-existent file"""
    module = BrowserUploadModule(
        params={
            'selector': 'input[type="file"]',
            'file_path': '/nonexistent/file.txt'
        },
        context={}
    )
    with pytest.raises(ValueError, match="File not found"):
        module.validate_params()


def test_upload_valid_params(tmp_path):
    """Test valid parameters"""
    # Create a temporary file
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")

    module = BrowserUploadModule(
        params={
            'selector': 'input[type="file"]',
            'file_path': str(test_file)
        },
        context={}
    )
    module.validate_params()
    assert module.selector == 'input[type="file"]'


@pytest.mark.asyncio
async def test_upload_no_browser(tmp_path):
    """Test error when browser not launched"""
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")

    module = BrowserUploadModule(
        params={
            'selector': 'input[type="file"]',
            'file_path': str(test_file)
        },
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
