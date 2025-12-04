"""
Browser Composite Modules

High-level browser automation workflows combining multiple atomic modules.
"""
from .search_and_notify import WebSearchAndNotify
from .scrape_to_json import WebScrapeToJson
from .screenshot_and_save import ScreenshotAndSave

__all__ = [
    'WebSearchAndNotify',
    'WebScrapeToJson',
    'ScreenshotAndSave',
]
