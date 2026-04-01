# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Automation Modules

Provides browser automation capabilities using Playwright.
All modules use i18n keys for multi-language support.

Example of schema presets usage - compare before/after:
    BEFORE (36 lines for params_schema):
        params_schema={
            'url': {'type': 'string', 'label': 'URL', ...,
            'placeholder': 'https://example.com',
            'description': 'Url',
        },
            'wait_until': {'type': 'select', 'options': [...], ...,
            'description': 'Wait Until option',
            'label': 'Wait Until',
        }
        }

    AFTER (4 lines with presets):
        params_schema=compose(
            presets.URL(required=True),
            presets.WAIT_CONDITION(),
            presets.TIMEOUT_MS(),
        )
"""
import logging
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_url_with_env_config, SSRFError

logger = logging.getLogger(__name__)


@register_module(
    module_id='browser.goto',
    version='1.0.0',
    category='browser',
    tags=['browser', 'navigation', 'url', 'ssrf_protected'],
    label='Go to URL',
    label_key='modules.browser.goto.label',
    description='Navigate to a specific URL',
    description_key='modules.browser.goto.description',
    icon='Globe',
    color='#5CB85C',

    # Connection types
    input_types=['browser', 'page'],
    output_types=['browser', 'page'],

    # Connection rules
    can_receive_from=['browser.launch', 'browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'data.*', 'flow.*', 'file.*', 'string.*', 'array.*', 'object.*'],

    # Execution settings
    timeout_ms=30000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.read', 'browser.write'],

    # Schema-driven params
    params_schema=compose(
        presets.URL(required=True, placeholder='https://example.com'),
        presets.WAIT_CONDITION(default='domcontentloaded'),
        presets.TIMEOUT_MS(key='timeout_ms', default=30000),
        presets.SSRF_PROTECTION(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.goto.output.status.description'},
        'url': {'type': 'string', 'description': 'URL address',
                'description_key': 'modules.browser.goto.output.url.description'}
    },
    examples=[
        {
            'name': 'Navigate to Google',
            'params': {
                'url': 'https://www.google.com',
                'wait_until': 'domcontentloaded'
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
class BrowserGotoModule(BaseModule):
    """Navigate to URL Module"""

    module_name = "Go to URL"
    module_description = "Navigate to a specific URL"
    required_permission = "browser.navigate"

    def validate_params(self) -> None:
        if 'url' not in self.params:
            raise ValueError("Missing required parameter: url")
        self.url = self.params['url']

        # SECURITY: Validate URL against SSRF attacks (toggleable per-node)
        if self.params.get('ssrf_protection', True):
            try:
                validate_url_with_env_config(self.url)
            except SSRFError as e:
                raise ValueError(f"SSRF protection: {e}")
        else:
            logger.warning("SSRF protection disabled by user for URL: %s", self.url[:80])

        # Default to 'domcontentloaded' for faster page loads (was 'networkidle' which hangs on many sites)
        self.wait_until = self.params.get('wait_until', 'domcontentloaded')
        self.timeout_ms = self.params.get('timeout_ms', 30000)

    # Error patterns where www/non-www toggle is likely to help
    _WWW_TOGGLE_PATTERNS = (
        "ERR_HTTP_RESPONSE_CODE_FAILURE",
        "ERR_FAILED",
        "ERR_ABORTED",
        "ERR_CONNECTION_REFUSED",
        "ERR_CONNECTION_RESET",
        "ERR_TIMED_OUT",
        "403",
    )

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        try:
            result = await browser.goto(self.url, wait_until=self.wait_until, timeout_ms=self.timeout_ms)

            # driver.goto() returns success even for HTTP errors (403 etc.)
            # when the page URL isn't chrome-error://.  Detect and try www toggle.
            if result.get('warning') and 'HTTP error' in str(result.get('warning', '')):
                logger.info("goto: HTTP error warning detected, trying www toggle for %s", self.url)
                alt = await self._try_www_toggle(browser)
                if alt is not None:
                    return alt

            out = {"status": "success", "url": result.get('url', self.url)}
            # Capture interactive elements for Element Picker UI
            browser._snapshot_since_nav = True
            hints = await browser.get_hints(force=True)
            for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects'):
                if hints.get(key):
                    out[key] = hints[key]
            return out

        except (RuntimeError, Exception) as e:
            err_str = str(e)
            if any(p in err_str for p in self._WWW_TOGGLE_PATTERNS):
                logger.info("goto: error matched toggle pattern, trying www toggle for %s: %s", self.url, err_str[:100])
                alt = await self._try_www_toggle(browser)
                if alt is not None:
                    return alt
            raise

    async def _try_www_toggle(self, browser) -> Any:
        """Try navigating with toggled www prefix. Returns result dict or None."""
        alt_url = self._toggle_www(self.url)
        if not alt_url:
            return None
        logger.info("goto: www toggle %s → %s", self.url, alt_url)
        # Replace page to clear chrome-error:// state
        try:
            old_page = browser._page
            browser._page = await browser._context.new_page()
            await old_page.close()
        except Exception:
            pass
        try:
            result = await browser.goto(alt_url, wait_until=self.wait_until, timeout_ms=self.timeout_ms)
            # Only accept if the toggle actually fixed it
            if not result.get('warning'):
                logger.info("goto: www toggle succeeded → %s", result.get('url', alt_url))
                out = {"status": "success", "url": result.get('url', alt_url)}
                hints = await browser.get_hints(force=True)
                for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects'):
                    if hints.get(key):
                        out[key] = hints[key]
                return out
            logger.info("goto: www toggle also got warning, giving up")
        except Exception as e2:
            logger.info("goto: www toggle also failed: %s", str(e2)[:100])
        return None

    @staticmethod
    def _toggle_www(url: str):
        """Toggle www prefix."""
        if '://www.' in url:
            return url.replace('://www.', '://', 1)
        if '://' in url:
            return url.replace('://', '://www.', 1)
        return None


