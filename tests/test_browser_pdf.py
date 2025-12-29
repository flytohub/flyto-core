"""
Tests for Browser PDF Module
"""
import pytest
import pytest_asyncio
from pathlib import Path
from core.modules.atomic.browser.pdf import BrowserPdfModule


def test_pdf_missing_path():
    """Test validation without path"""
    module = BrowserPdfModule(
        params={},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: path"):
        module.validate_params()


def test_pdf_invalid_scale():
    """Test validation with invalid scale"""
    module = BrowserPdfModule(
        params={'path': '/tmp/test.pdf', 'scale': 5},
        context={}
    )
    with pytest.raises(ValueError, match="Scale must be between"):
        module.validate_params()


def test_pdf_valid_params(tmp_path):
    """Test valid parameters"""
    pdf_path = tmp_path / "test.pdf"

    module = BrowserPdfModule(
        params={'path': str(pdf_path)},
        context={}
    )
    module.validate_params()
    assert module.path == str(pdf_path)
    assert module.format == 'A4'


@pytest.mark.asyncio
async def test_pdf_no_browser(tmp_path):
    """Test error when browser not launched"""
    pdf_path = tmp_path / "test.pdf"

    module = BrowserPdfModule(
        params={'path': str(pdf_path)},
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
