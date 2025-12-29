"""
Pytest Configuration and Fixtures

Provides shared fixtures for browser testing.
"""
import pytest
import pytest_asyncio
import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


@pytest_asyncio.fixture
async def browser():
    """
    Fixture that provides a launched browser driver.
    Automatically closes browser after test.
    """
    from core.browser.driver import BrowserDriver

    driver = BrowserDriver(headless=True)
    await driver.launch()
    yield driver
    await driver.close()


@pytest_asyncio.fixture
async def browser_with_page(browser):
    """
    Fixture that provides a browser navigated to a test page.
    """
    await browser.goto("https://example.com")
    yield browser


@pytest.fixture
def context():
    """
    Fixture that provides an empty context dict.
    """
    return {}


@pytest.fixture
def context_with_browser(browser):
    """
    Fixture that provides a context with browser.
    """
    return {'browser': browser}


@pytest.fixture
def temp_dir(tmp_path):
    """
    Fixture that provides a temporary directory.
    """
    return tmp_path


@pytest.fixture
def sample_html_page():
    """
    Returns HTML content for testing.
    """
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Test Page</title></head>
    <body>
        <h1 id="header">Test Header</h1>
        <button id="submit-btn">Submit</button>
        <input type="text" id="name-input" name="name" />
        <select id="country-select">
            <option value="us">United States</option>
            <option value="uk">United Kingdom</option>
            <option value="ca">Canada</option>
        </select>
        <a href="https://example.com/link">Link</a>
        <div class="content">
            <p>Paragraph 1</p>
            <p>Paragraph 2</p>
        </div>
        <iframe id="test-frame" src="about:blank"></iframe>
        <input type="file" id="file-input" />
        <div id="dropzone" style="width: 200px; height: 200px;"></div>
        <div id="draggable" draggable="true">Drag me</div>
    </body>
    </html>
    """
