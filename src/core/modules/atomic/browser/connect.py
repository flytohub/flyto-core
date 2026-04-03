# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Connect Module — Connect to remote browser services

Connect to cloud browser providers for:
- Real browser fingerprints (bypass Cloudflare, Akamai)
- Residential IP + real Chrome = undetectable
- Scale to hundreds of concurrent sessions

Supported services:
- Browserless.io (ws://...)
- BrowserBase (wss://connect.browserbase.com)
- Any Playwright-compatible CDP endpoint
- Self-hosted (Docker browserless)
"""
import logging
from typing import Any, Dict, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field

logger = logging.getLogger(__name__)


@register_module(
    module_id='browser.connect',
    version='1.0.0',
    category='browser',
    tags=['browser', 'remote', 'cloud', 'browserless', 'anti-detection'],
    label='Connect Remote',
    label_key='modules.browser.connect.label',
    description='Connect to a remote browser service (Browserless, BrowserBase, CDP). Real fingerprints, residential IPs.',
    description_key='modules.browser.connect.description',
    icon='Cloud',
    color='#7C3AED',
    input_types=[],
    output_types=['browser', 'page'],
    can_receive_from=['start', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'ai.*', 'llm.*'],
    params_schema=compose(
        field('ws_endpoint', type='string', label='WebSocket endpoint',
              description='CDP WebSocket URL (e.g., wss://chrome.browserless.io?token=xxx).',
              required=True, format='url',
              placeholder='wss://chrome.browserless.io?token=YOUR_TOKEN',
              group='basic'),
        field('viewport_width', type='number', label='Viewport width',
              default=1280, min=320, max=3840,
              group='basic'),
        field('viewport_height', type='number', label='Viewport height',
              default=720, min=240, max=2160,
              group='basic'),
        field('locale', type='string', label='Locale',
              default='en-US', required=False,
              group='advanced'),
        field('timeout_ms', type='number', label='Connection timeout (ms)',
              default=30000, min=5000, max=120000, step=5000,
              group='advanced'),
    ),
    output_schema={
        'connected':    {'type': 'boolean', 'description': 'Whether connection succeeded'},
        'browser_type': {'type': 'string',  'description': 'Browser type (chromium)'},
        'endpoint':     {'type': 'string',  'description': 'Connected endpoint (redacted)'},
    },
    examples=[
        {'name': 'Connect to Browserless', 'params': {'ws_endpoint': 'wss://chrome.browserless.io?token=TOKEN'}},
        {'name': 'Connect to BrowserBase', 'params': {'ws_endpoint': 'wss://connect.browserbase.com?apiKey=KEY'}},
        {'name': 'Self-hosted', 'params': {'ws_endpoint': 'ws://localhost:3000'}},
    ],
    author='Flyto Team', license='MIT', timeout_ms=35000,
    required_permissions=["browser.read", "browser.write"],
)
class BrowserConnectModule(BaseModule):
    module_name = "Connect Remote"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.ws_endpoint = self.params.get('ws_endpoint', '')
        if not self.ws_endpoint:
            raise ValueError("ws_endpoint is required")
        self.viewport = {
            'width': self.params.get('viewport_width', 1280),
            'height': self.params.get('viewport_height', 720),
        }
        self.locale = self.params.get('locale', 'en-US')
        self.conn_timeout = self.params.get('timeout_ms', 30000)

    async def execute(self) -> Any:
        from playwright.async_api import async_playwright
        from core.browser.driver import BrowserDriver

        # Close existing browser
        existing = self.context.get('browser')
        if existing:
            try:
                await existing.close()
            except Exception:
                pass

        # Connect to remote CDP endpoint
        pw = await async_playwright().start()

        try:
            remote_browser = await pw.chromium.connect_over_cdp(
                self.ws_endpoint,
                timeout=self.conn_timeout,
            )
        except Exception as e:
            await pw.stop()
            raise RuntimeError(f"Failed to connect to remote browser: {e}") from e

        # Get or create context + page
        contexts = remote_browser.contexts
        if contexts:
            context = contexts[0]
        else:
            context = await remote_browser.new_context(
                viewport=self.viewport,
                locale=self.locale,
            )

        pages = context.pages
        page = pages[0] if pages else await context.new_page()

        # Wrap in BrowserDriver for compatibility with other browser.* modules
        driver = BrowserDriver(
            headless=True,
            viewport=self.viewport,
            browser_type='chromium',
        )
        driver._playwright = pw
        driver._browser = remote_browser
        driver._context = context
        driver._page = page

        self.context['browser'] = driver
        self.context['browser_remote'] = True

        # Redact token from endpoint for output
        endpoint_display = self.ws_endpoint.split('?')[0] + '?...'

        logger.info("Connected to remote browser: %s", endpoint_display)

        return {
            "status": "success",
            "connected": True,
            "browser_type": "chromium",
            "endpoint": endpoint_display,
        }
