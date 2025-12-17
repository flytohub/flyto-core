"""
Composite Modules (Level 3)

High-level workflow templates combining multiple atomic and third-party modules.
Designed for normal users, similar to n8n nodes (3-10 atomic steps).

Categories:
- browser: Web automation workflows
- developer: Developer tool integrations
- notification: Multi-channel notification workflows
- data: Data transformation pipelines

Usage:
    from core.modules.composite import CompositeRegistry, CompositeExecutor

    # List all composites
    composites = CompositeRegistry.list_all()

    # Execute a composite
    executor = CompositeExecutor()
    result = await executor.execute(
        'composite.browser.search_and_notify',
        {'query': 'python tutorial', 'webhook_url': '...'}
    )
"""

from .base import (
    CompositeModule,
    CompositeRegistry,
    CompositeExecutor,
    register_composite,
    UIVisibility,
)

# Browser composites
from .browser.search_and_notify import WebSearchAndNotify
from .browser.scrape_to_json import WebScrapeToJson
from .browser.screenshot_and_save import ScreenshotAndSave

# Developer composites
from .developer.github_daily_digest import GithubDailyDigest
from .developer.api_to_notification import ApiToNotification

# Notification composites
from .notification.multi_channel_alert import MultiChannelAlert
from .notification.scheduled_report import ScheduledReport

# Data composites
from .data.csv_to_json import CsvToJson
from .data.json_transform_notify import JsonTransformNotify


__all__ = [
    # Base classes
    'CompositeModule',
    'CompositeRegistry',
    'CompositeExecutor',
    'register_composite',
    'UIVisibility',

    # Browser composites
    'WebSearchAndNotify',
    'WebScrapeToJson',
    'ScreenshotAndSave',

    # Developer composites
    'GithubDailyDigest',
    'ApiToNotification',

    # Notification composites
    'MultiChannelAlert',
    'ScheduledReport',

    # Data composites
    'CsvToJson',
    'JsonTransformNotify',
]


def get_composite_statistics():
    """Get statistics about registered composite modules"""
    return CompositeRegistry.get_statistics()


def list_composites_by_category(category: str):
    """List all composites in a category"""
    return CompositeRegistry.get_all_metadata(category=category)
