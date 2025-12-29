"""
Tests for Browser Drag Module
"""
import pytest
import pytest_asyncio
from core.modules.atomic.browser.drag import BrowserDragModule


def test_drag_missing_source():
    """Test validation without source"""
    module = BrowserDragModule(
        params={'target': '#dropzone'},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: source"):
        module.validate_params()


def test_drag_missing_target():
    """Test validation without target"""
    module = BrowserDragModule(
        params={'source': '#draggable'},
        context={}
    )
    with pytest.raises(ValueError, match="Missing required parameter: target"):
        module.validate_params()


def test_drag_valid_params():
    """Test valid parameters"""
    module = BrowserDragModule(
        params={'source': '#draggable', 'target': '#dropzone'},
        context={}
    )
    module.validate_params()
    assert module.source == '#draggable'
    assert module.target == '#dropzone'


@pytest.mark.asyncio
async def test_drag_no_browser():
    """Test error when browser not launched"""
    module = BrowserDragModule(
        params={'source': '#draggable', 'target': '#dropzone'},
        context={}
    )
    module.validate_params()

    with pytest.raises(RuntimeError, match="Browser not launched"):
        await module.execute()
